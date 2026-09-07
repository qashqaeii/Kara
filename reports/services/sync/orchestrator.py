"""Synchronization orchestrator — pulls Kara reports into local DB."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from reports.constants import PRIMARY_KPI_REPORT, ConnectionStatus, SyncStatus
from reports.exceptions import KaraError
from reports.models import (
    AccountBalanceSnapshot,
    DailyBusinessMetric,
    DistributionReversionSnapshot,
    HeadVisitorSaleSnapshot,
    KaraConnection,
    KaraReportSnapshot,
    KaraSyncJob,
    KaraSyncLog,
    MonthlySaleDetailSnapshot,
    ReceivableAgingSnapshot,
    SaleReversionSnapshot,
    SaleOrderSnapshot,
    SaleStuffSnapshot,
    StuffGroupSaleSnapshot,
    VisitorSaleSnapshot,
)
from reports.services.invoices import derive_pre_order_status
from reports.services.retention import (
    find_live_snapshot,
    replace_superseded_snapshots,
    slim_stored_payload,
)
from reports.services.kara_client import KaraClient
from reports.services.kara_tenant import apply_tenant_overrides
from reports.services.monthly_sales import extract_monthly_amounts, jalali_fiscal_year
from reports.services.parsers import flatten_rows, parse_decimal, parse_int
from reports.services.report_filter import ReportFilter
from reports.services.report_registry import ReportRegistry
from reports.services.sync.locks import report_sync_lock

logger = logging.getLogger(__name__)


def _checksum(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _dec(value: Any) -> Decimal:
    return parse_decimal(value) or Decimal("0")


def _int(value: Any) -> int:
    return parse_int(value) or 0


def _is_monthly_partner_column_error(exc: KaraError) -> bool:
    message = str(exc)
    if "Invalid column name" not in message:
        return False
    return any(
        column in message
        for column in (
            "PartnerTelephones",
            "PartnerAddress",
            "PartnerZoneAndRoute",
            "PartnerNationalId",
            "PartnerNationalElevenDigitID",
            "PartnerFinancialCode",
        )
    )


def _is_select_into_race_error(exc: KaraError) -> bool:
    """SQL Server SELECT INTO race: schema changed / rerun the query."""
    lower = str(exc).lower()
    if "schema changed after the target table" in lower:
        return True
    if "select into" in lower and "rerun" in lower:
        return True
    return False


def _is_monthly_partner_temp_error(exc: KaraError) -> bool:
    """Kara monthly sale often fails when partner temp tables race or columns are missing."""
    lower = str(exc).lower()
    if "##partners" in lower:
        return True
    if _is_select_into_race_error(exc):
        return True
    if "invalid object name" in lower and "partner" in lower:
        return True
    return _is_monthly_partner_column_error(exc)


def _monthly_sale_safe_partner_args(arguments: dict | None) -> dict:
    safe = dict(arguments or {})
    safe.update(
        {
            "WithPartnerZoneDetail": "false",
            "WithPartnerGroupDetail": "false",
            "WithPartnerDetail": "false",
        }
    )
    return safe


def _is_uniqueidentifier_error(exc: KaraError) -> bool:
    message = str(exc).lower()
    return "uniqueidentifier" in message or "converting from a character string" in message


# Reports that hit Kara SELECT INTO / temp-table races under concurrent load.
_FLAKY_REPORT_KEYS = frozenset(
    {
        "account_balance",
        "receivables_aging",
        "stuff_group_sale",
        "monthly_sale",
        "lost_benefit_separate",
        "monthly_stuff_group_lost_benefit",
    }
)


class SyncOrchestrator:
    """Idempotent sync of Kara reports into Django DB."""

    def __init__(self, client: KaraClient | None = None) -> None:
        self.client = client or KaraClient()

    def _run_report_with_fallback(
        self,
        report_key: str,
        *,
        arguments: dict | None,
        personnel_code: str,
        job: KaraSyncJob,
    ):
        last_error: KaraError | None = None
        attempts = 3 if report_key in _FLAKY_REPORT_KEYS else 1
        monthly_partner_safe = False

        for attempt in range(1, attempts + 1):
            run_args = arguments
            if report_key == "monthly_sale" and monthly_partner_safe:
                run_args = _monthly_sale_safe_partner_args(arguments)

            try:
                return self.client.run_report(
                    report_key,
                    arguments=run_args or None,
                    personnel_code=personnel_code,
                )
            except KaraError as exc:
                last_error = exc
                if (
                    report_key == "monthly_sale"
                    and not monthly_partner_safe
                    and _is_monthly_partner_temp_error(exc)
                ):
                    # ##Partners / Select Into races and missing partner columns —
                    # drop partner-detail flags and retry.
                    monthly_partner_safe = True
                    self._log(
                        job,
                        "warning",
                        "monthly_sale fallback to reduced partner detail",
                    )
                    continue

                if _is_uniqueidentifier_error(exc) and attempt < attempts:
                    wait_s = 1.5 * attempt
                    self._log(
                        job,
                        "warning",
                        f"خطای uniqueidentifier — تلاش مجدد {attempt + 1}/{attempts} پس از {wait_s:.0f}ث",
                    )
                    time.sleep(wait_s)
                    continue

                # SELECT INTO race (common on receivables_aging / balance under stagger load)
                if (
                    report_key in _FLAKY_REPORT_KEYS
                    and _is_select_into_race_error(exc)
                    and attempt < attempts
                ):
                    wait_s = 2.0 * attempt
                    self._log(
                        job,
                        "warning",
                        f"خطای موقت Schema/Select Into — تلاش مجدد {attempt + 1}/{attempts} پس از {wait_s:.0f}ث",
                    )
                    time.sleep(wait_s)
                    continue

                if (
                    report_key == "monthly_sale"
                    and monthly_partner_safe
                    and _is_monthly_partner_temp_error(exc)
                    and attempt < attempts
                ):
                    wait_s = 2.0 * attempt
                    self._log(
                        job,
                        "warning",
                        f"خطای موقت جدول شریک — تلاش مجدد {attempt + 1}/{attempts}",
                    )
                    time.sleep(wait_s)
                    continue
                raise

        assert last_error is not None
        raise last_error

    def sync_report(
        self,
        report_key: str,
        *,
        triggered_by: str = "manual",
        from_date: str = "",
        to_date: str = "",
        personnel_code: str = "",
        personnel_name: str = "",
        arguments: dict | None = None,
    ) -> KaraSyncJob:
        with report_sync_lock(report_key) as acquired:
            if not acquired:
                job = KaraSyncJob.objects.create(
                    report_key=report_key,
                    status=SyncStatus.CANCELLED,
                    triggered_by=triggered_by,
                    error_message="همگام‌سازی هم‌زمان برای این گزارش در حال اجراست.",
                    finished_at=timezone.now(),
                )
                return job
            return self._sync_report_unlocked(
                report_key,
                triggered_by=triggered_by,
                from_date=from_date,
                to_date=to_date,
                personnel_code=personnel_code,
                personnel_name=personnel_name,
                arguments=arguments,
            )

    def sync_all(
        self,
        *,
        triggered_by: str = "auto",
        from_date: str = "",
        to_date: str = "",
    ) -> list[KaraSyncJob]:
        jobs: list[KaraSyncJob] = []
        for key in ReportRegistry.keys(syncable_only=True):
            jobs.append(
                self.sync_report(
                    key,
                    triggered_by=triggered_by,
                    from_date=from_date,
                    to_date=to_date,
                )
            )
        return jobs

    def _sync_report_unlocked(
        self,
        report_key: str,
        *,
        triggered_by: str,
        from_date: str,
        to_date: str,
        personnel_code: str,
        personnel_name: str,
        arguments: dict | None,
    ) -> KaraSyncJob:
        config = ReportRegistry.get(report_key)
        job = KaraSyncJob.objects.create(
            report_key=report_key,
            status=SyncStatus.RUNNING,
            triggered_by=triggered_by,
            requested_from_date=from_date,
            requested_to_date=to_date,
            metadata={"personnel_code": personnel_code},
        )
        self._log(job, "info", f"شروع همگام‌سازی {config.title}")
        started = time.monotonic()
        self._set_connection_status(ConnectionStatus.SYNCING)

        try:
            overrides = dict(arguments or {})
            if from_date:
                for key in ("BDate", "BOrderDate", "BReversionDate"):
                    if key in config.default_arguments:
                        overrides[key] = from_date
            if to_date:
                for key in ("EDate", "EOrderDate", "EReversionDate"):
                    if key in config.default_arguments:
                        overrides[key] = to_date
            overrides = apply_tenant_overrides(report_key, overrides)
            if report_key == "profit_and_loss":
                overrides = self._ensure_profit_loss_dates(overrides)
            elif report_key == "sale_stuffs":
                overrides = self._ensure_sale_stuffs_dates(overrides)
            elif report_key == "lost_benefit_separate":
                overrides = self._ensure_lost_benefit_separate_dates(overrides)

            dual_daily = (
                report_key
                in (
                    "visitor_sale",
                    "head_visitor_sale",
                    "stuff_group_sale",
                    "sale_orders",
                    "sale_orders_with_stuffs",
                )
                and not from_date
                and not to_date
            )

            if dual_daily:
                # Phase 1: YTD snapshot for «کل داده‌ها» (keep snapshot only).
                ytd_overrides = self._ensure_ytd_report_dates(dict(overrides), report_key)
                try:
                    self._fetch_and_persist(
                        report_key=report_key,
                        config=config,
                        job=job,
                        overrides=ytd_overrides,
                        personnel_code=personnel_code,
                        personnel_name=personnel_name,
                        period_from=str(ytd_overrides.get("BDate") or ""),
                        period_to=str(ytd_overrides.get("EDate") or ""),
                        run_pipeline=False,
                        started=started,
                        finalize_job=False,
                    )
                    self._log(job, "info", "اسنپ‌شات YTD برای کل داده‌ها ذخیره شد")
                except Exception as ytd_exc:
                    self._log(job, "warning", f"YTD snapshot failed: {ytd_exc}")

                # Phase 2: today-only daily metrics for period filters.
                overrides = self._ensure_daily_report_dates(
                    dict(overrides),
                    allowed_keys=config.default_arguments,
                )
                return self._fetch_and_persist(
                    report_key=report_key,
                    config=config,
                    job=job,
                    overrides=overrides,
                    personnel_code=personnel_code,
                    personnel_name=personnel_name,
                    period_from=str(overrides.get("BDate") or ""),
                    period_to=str(overrides.get("EDate") or ""),
                    run_pipeline=True,
                    started=started,
                    finalize_job=True,
                )

            if report_key in (
                "visitor_sale",
                "head_visitor_sale",
                "stuff_group_sale",
                "sale_orders",
                "sale_orders_with_stuffs",
            ) and not from_date and not to_date:
                overrides = self._ensure_ytd_report_dates(overrides, report_key)

            return self._fetch_and_persist(
                report_key=report_key,
                config=config,
                job=job,
                overrides=overrides,
                personnel_code=personnel_code,
                personnel_name=personnel_name,
                period_from=from_date or str(overrides.get("BDate") or ""),
                period_to=to_date or str(overrides.get("EDate") or ""),
                run_pipeline=True,
                started=started,
                finalize_job=True,
            )

        except KaraError as exc:
            job.status = SyncStatus.FAILED
            job.error_message = str(exc)
            job.error_count = 1
            job.duration_ms = int((time.monotonic() - started) * 1000)
            job.finished_at = timezone.now()
            job.save()
            self._log(job, "error", str(exc))
            status = (
                ConnectionStatus.NEEDS_RELOGIN
                if "منقضی" in str(exc) or "ورود" in str(exc)
                else ConnectionStatus.KARA_ERROR
            )
            if "شبکه" in str(exc) or "ارتباط" in str(exc):
                status = ConnectionStatus.NETWORK_ERROR
            self._set_connection_status(status, error=str(exc))
            return job
        except Exception as exc:
            logger.exception("Unexpected sync failure for %s", report_key)
            job.status = SyncStatus.FAILED
            job.error_message = "خطای داخلی همگام‌سازی"
            job.error_count = 1
            job.duration_ms = int((time.monotonic() - started) * 1000)
            job.finished_at = timezone.now()
            job.metadata = {**job.metadata, "internal_error": str(exc)}
            job.save()
            self._log(job, "error", "خطای داخلی همگام‌سازی")
            self._set_connection_status(ConnectionStatus.KARA_ERROR, error=str(exc))
            return job

    def _fetch_and_persist(
        self,
        *,
        report_key: str,
        config,
        job: KaraSyncJob,
        overrides: dict,
        personnel_code: str,
        personnel_name: str,
        period_from: str,
        period_to: str,
        run_pipeline: bool,
        started: float,
        finalize_job: bool,
    ) -> KaraSyncJob:
        inserted = 0
        updated = 0
        if config.is_print_report:
            print_response = self.client.run_print_report(
                report_key,
                arguments=overrides or None,
            )
            payload = print_response.as_dict()
            response_count = 0
            response_page_count = 1
        else:
            grid_response = self._run_report_with_fallback(
                report_key,
                job=job,
                arguments=overrides or None,
                personnel_code=personnel_code,
            )
            payload = grid_response.as_dict()
            response_count = grid_response.count
            response_page_count = grid_response.page_count
        payload["fetched_at"] = timezone.now().isoformat(timespec="seconds")
        if personnel_name:
            payload["personnel_name"] = personnel_name

        checksum = _checksum(
            {
                "Data": payload.get("Data"),
                "SumRowData": payload.get("SumRowData"),
                "total": payload.get("GridViewJSTotal"),
                "parsed": payload.get("parsed"),
            }
        )

        # Skip duplicate identical payload for the same period kind (YTD vs daily).
        if not personnel_code:
            latest = find_live_snapshot(
                report_key, "", period_from, period_to
            )
            if latest and latest.content_checksum == checksum:
                latest.fetched_at = timezone.now()
                update_fields = ["fetched_at"]
                if period_from and (
                    not latest.period_from
                    or (period_from < latest.period_from and period_to)
                ):
                    latest.period_from = period_from
                    latest.period_to = period_to or latest.period_to
                    update_fields.extend(["period_from", "period_to"])
                latest.save(update_fields=update_fields)
                if finalize_job:
                    job.status = SyncStatus.SUCCESS
                    job.received_count = response_count
                    job.page_count = response_page_count
                    job.skipped_count = max(response_count, 1)
                    job.duration_ms = int((time.monotonic() - started) * 1000)
                    job.finished_at = timezone.now()
                    job.metadata = {**job.metadata, "deduplicated": True}
                    job.save()
                    self._log(job, "info", "داده تکراری — اسنپ‌شات تازه شد (بدون درج)")
                    self._set_connection_status(
                        ConnectionStatus.CONNECTED, sync_ok=True
                    )
                return job

        with transaction.atomic():
            title = config.title
            if personnel_code:
                title = f"{config.title} — {personnel_name or personnel_code}"

            snapshot = KaraReportSnapshot.objects.create(
                report_key=config.key,
                report_title=title,
                fetched_at=timezone.now(),
                raw_data=slim_stored_payload(payload),
                rows_count=response_count,
                personnel_code=personnel_code or "",
                personnel_name=personnel_name or "",
                sync_job=job,
                content_checksum=checksum,
                period_from=period_from,
                period_to=period_to,
            )

            inserted, updated = self._persist_normalized(
                report_key, snapshot, job, payload
            )
            replace_superseded_snapshots(snapshot)

            if run_pipeline and not personnel_code:
                from reports.services.analytics_pipeline import AnalyticsPipeline

                AnalyticsPipeline.process_snapshot(snapshot)
                if finalize_job:
                    from reports.services.alert_engine import AlertEngine

                    AlertEngine.evaluate_all()

        if finalize_job:
            job.status = SyncStatus.SUCCESS
            job.received_count = response_count
            job.page_count = response_page_count
            job.inserted_count = inserted
            job.updated_count = updated
            job.duration_ms = int((time.monotonic() - started) * 1000)
            job.finished_at = timezone.now()
            job.save()
            self._log(
                job,
                "info",
                f"موفق — {response_count} رکورد، {inserted} درج، {updated} بروزرسانی",
            )
            self._set_connection_status(ConnectionStatus.CONNECTED, sync_ok=True)
            if not personnel_code and report_key in (
                "sale_orders",
                "receivables_aging",
                "visitor_sale",
            ):
                try:
                    from reports.bot.services.notifications import BotNotificationService

                    BotNotificationService.notify_sync_complete(
                        report_key, inserted + updated
                    )
                except Exception:
                    logger.exception("bot sync notification failed")
        return job

    def _ensure_profit_loss_dates(self, overrides: dict) -> dict:
        """Fill fiscal YTD dates for LostBenefit when caller omitted them."""
        result = dict(overrides)
        today = timezone.localdate()
        try:
            import jdatetime

            jtoday = jdatetime.date.fromgregorian(date=today)
            if not result.get("EDate"):
                result["EDate"] = f"{jtoday.year}/{jtoday.month:02d}/{jtoday.day:02d}"
            if not result.get("BDate"):
                result["BDate"] = f"{jtoday.year}/01/01"
        except Exception:
            if not result.get("EDate"):
                result["EDate"] = today.isoformat().replace("-", "/")
            if not result.get("BDate"):
                result["BDate"] = f"{today.year}/01/01"
        return result

    def _ensure_daily_report_dates(
        self, overrides: dict, *, allowed_keys: dict | None = None
    ) -> dict:
        """
        Fill empty date fields with today (Jalali).

        Only touches keys that already exist in ``allowed_keys`` (report defaults).
        Never invents BDate/EDate for reports that use Order/Reversion date pairs —
        that causes Kara ``Parameter count mismatch``.
        """
        result = dict(overrides)
        allowed = set(allowed_keys or ())
        if not allowed:
            return result

        today = timezone.localdate()
        try:
            import jdatetime

            jtoday = jdatetime.date.fromgregorian(date=today)
            today_j = f"{jtoday.year}/{jtoday.month:02d}/{jtoday.day:02d}"
        except Exception:
            today_j = today.isoformat().replace("-", "/")

        for begin_key, end_key in (
            ("BDate", "EDate"),
            ("BOrderDate", "EOrderDate"),
            ("BReversionDate", "EReversionDate"),
            ("BPreOrderInsertDate", "EPreOrderInsertDate"),
        ):
            if begin_key not in allowed and end_key not in allowed:
                continue
            if begin_key in allowed and not result.get(begin_key):
                result[begin_key] = today_j
            if end_key in allowed and not result.get(end_key):
                result[end_key] = today_j
        return result

    def _ensure_sale_stuffs_dates(self, overrides: dict) -> dict:
        """
        Empty BDate/EDate in Kara returns only today's return-only rows.
        Default to fiscal YTD so پرفروش‌ها reflect actual sales.
        Only sets keys present on the sale_stuffs report definition.
        """
        from reports.services.report_registry import ReportRegistry

        ytd = self._ensure_profit_loss_dates(overrides)
        allowed = set(ReportRegistry.get("sale_stuffs").default_arguments)
        return {k: v for k, v in ytd.items() if k in allowed or k in overrides}

    def _ensure_lost_benefit_separate_dates(self, overrides: dict) -> dict:
        """Fiscal YTD for product-level LostBenefitSeparate (COGS + margin)."""
        from reports.services.report_registry import ReportRegistry

        ytd = self._ensure_profit_loss_dates(overrides)
        allowed = set(ReportRegistry.get("lost_benefit_separate").default_arguments)
        result = dict(overrides)
        for key in ("BDate", "EDate"):
            if key in allowed and not result.get(key):
                result[key] = ytd.get(key, "")
        return result

    def _ensure_ytd_report_dates(self, overrides: dict, report_key: str) -> dict:
        """Fill fiscal YTD BDate/EDate for sales reports that support those keys."""
        from reports.services.report_registry import ReportRegistry

        ytd = self._ensure_profit_loss_dates(overrides)
        allowed = set(ReportRegistry.get(report_key).default_arguments)
        result = dict(overrides)
        for key in ("BDate", "EDate"):
            if key in allowed and not result.get(key):
                result[key] = ytd.get(key, "")
        return result

    def _persist_normalized(
        self,
        report_key: str,
        snapshot: KaraReportSnapshot,
        job: KaraSyncJob,
        payload: dict,
    ) -> tuple[int, int]:
        rows = flatten_rows(payload)
        if report_key == "visitor_sale":
            return self._upsert_visitor_rows(snapshot, job, rows)
        if report_key == "head_visitor_sale":
            return self._upsert_head_rows(snapshot, job, rows)
        if report_key == "stuff_group_sale":
            return self._upsert_stuff_group_rows(snapshot, job, rows)
        if report_key == "sale_reversion":
            return self._upsert_sale_reversion_rows(snapshot, job, rows)
        if report_key == "sale_distribution_reversion":
            return self._upsert_distribution_reversion_rows(snapshot, job, rows)
        if report_key == "sale_orders":
            return self._upsert_sale_order_rows(snapshot, job, rows)
        if report_key == "sale_orders_with_stuffs":
            return self._upsert_sale_order_line_rows(snapshot, job, rows)
        if report_key == "sale_stuffs":
            return self._upsert_sale_stuff_rows(snapshot, job, rows)
        if report_key == "monthly_sale":
            return self._upsert_monthly_sale_rows(snapshot, job, rows)
        if report_key == "account_balance":
            return self._upsert_account_balance_rows(snapshot, job, rows)
        if report_key == "receivables_aging":
            return self._upsert_receivable_aging_rows(snapshot, job, rows)
        if report_key == "profit_and_loss":
            return 0, 0
        return len(rows), 0

    def _upsert_visitor_rows(self, snapshot, job, rows) -> tuple[int, int]:
        objs = []
        for row in rows:
            code = (row.get("VisitorCode") or "").strip()
            if not code:
                continue
            objs.append(
                VisitorSaleSnapshot(
                    sync_job=job,
                    last_sync_job=job,
                    snapshot=snapshot,
                    visitor_code=code,
                    visitor_name=(row.get("VisitorName") or "").strip(),
                    head_visitor_code=(row.get("HeadVisitorCode") or "").strip(),
                    head_visitor_name=(row.get("HeadVisitorName") or "").strip(),
                    total_sale=_dec(row.get("TotalSale")),
                    total_pure_sale=_dec(row.get("TotalPureSale")),
                    order_count=_int(row.get("OrderCountBasedOnFinalOrder")),
                    partner_count=_int(row.get("PartnerNumberBasedOnFinalOrder")),
                    distribution_reversion=_dec(row.get("TotalDistributionReversion")),
                    sale_reversion=_dec(row.get("TotalSaleReversion")),
                    settlement_remainder=_dec(
                        row.get("RemainderBasedOnSettlementWithSaleReversion")
                    ),
                    source_key=str(row.get("_key") or ""),
                )
            )
        VisitorSaleSnapshot.objects.bulk_create(objs, batch_size=200)
        return len(objs), 0

    def _upsert_head_rows(self, snapshot, job, rows) -> tuple[int, int]:
        objs = []
        for row in rows:
            code = (row.get("VisitorCode") or "").strip()
            if not code:
                continue
            objs.append(
                HeadVisitorSaleSnapshot(
                    sync_job=job,
                    snapshot=snapshot,
                    head_visitor_code=code,
                    head_visitor_name=(row.get("VisitorName") or "").strip(),
                    total_sale=_dec(row.get("TotalSale")),
                    total_pure_sale=_dec(row.get("TotalPureSale")),
                    order_count=_int(row.get("OrderCountBasedOnFinalOrder")),
                    distribution_reversion=_dec(row.get("TotalDistributionReversion")),
                    sale_reversion=_dec(row.get("TotalSaleReversion")),
                    settlement_remainder=_dec(
                        row.get("RemainderBasedOnSettlementWithSaleReversion")
                    ),
                )
            )
        HeadVisitorSaleSnapshot.objects.bulk_create(objs, batch_size=200)
        return len(objs), 0

    def _stuff_group_row_key(self, row: dict) -> str:
        key = row.get("_key")
        if key is not None and str(key).strip():
            return str(key)
        parts = (
            row.get("StuffCode"),
            row.get("PartnerCode"),
            row.get("VisitorCode"),
            row.get("Route"),
            row.get("StuffGroupName") or row.get("StuffGroupName1"),
        )
        return "|".join(str(p or "").strip() for p in parts) or "unknown"

    def _upsert_stuff_group_rows(self, snapshot, job, rows) -> tuple[int, int]:
        objs = []
        for row in rows:
            row_key = self._stuff_group_row_key(row)
            objs.append(
                StuffGroupSaleSnapshot(
                    sync_job=job,
                    snapshot=snapshot,
                    row_key=row_key,
                    group_name=(
                        row.get("StuffGroupName") or row.get("StuffGroupName1") or ""
                    ).strip(),
                    sub_group_name=(row.get("StuffSubGroupName") or row.get("StuffGroupName2") or "").strip(),
                    stuff_code=str(row.get("StuffCode") or "").strip(),
                    stuff_name=(row.get("StuffName") or "").strip(),
                    partner_code=str(row.get("PartnerCode") or "").strip(),
                    partner_name=(row.get("PartnerName") or "").strip(),
                    visitor_code=str(row.get("VisitorCode") or "").strip(),
                    visitor_name=(row.get("VisitorName") or "").strip(),
                    city=(row.get("City") or "").strip(),
                    zone=(row.get("Zone") or "").strip(),
                    route=(row.get("Route") or "").strip(),
                    pure_sale=_dec(row.get("PureSalePrice")),
                    not_pure_sale=_dec(row.get("NotPureSalePrice")),
                    pure_sale_quantity=_int(row.get("PureSaleQuantity")),
                    order_count=_int(row.get("OrderCount")),
                    partner_count=_int(row.get("PartnerCount")),
                    distribution_reversion=_dec(row.get("DistributionReversionPrice")),
                    sale_reversion=_dec(row.get("SaleReversionPrice")),
                )
            )
        StuffGroupSaleSnapshot.objects.bulk_create(objs, batch_size=200)
        return len(objs), 0

    def _monthly_row_key(self, row: dict) -> str:
        key = row.get("_key")
        if key is not None and str(key).strip():
            return str(key)
        parts = (
            row.get("PartnerCode"),
            row.get("VisitorCode"),
            row.get("StuffCode"),
            row.get("StuffGroupCode1"),
        )
        return "|".join(str(p or "").strip() for p in parts) or "unknown"

    def _upsert_monthly_sale_rows(self, snapshot, job, rows) -> tuple[int, int]:
        fiscal_year = jalali_fiscal_year(snapshot.fetched_at)
        objs = []
        for row in rows:
            amounts = extract_monthly_amounts(row)
            objs.append(
                MonthlySaleDetailSnapshot(
                    snapshot=snapshot,
                    fiscal_year=fiscal_year,
                    row_key=self._monthly_row_key(row),
                    partner_code=str(row.get("PartnerCode") or "").strip(),
                    partner_name=(row.get("PartnerName") or "").strip(),
                    visitor_code=str(row.get("VisitorCode") or "").strip(),
                    visitor_name=(row.get("VisitorName") or "").strip(),
                    stuff_code=str(row.get("StuffCode") or "").strip(),
                    stuff_name=(row.get("StuffName") or "").strip(),
                    stuff_group_name=(row.get("StuffGroupName1") or row.get("StuffGroupName") or "").strip(),
                    stuff_sub_group_name=(row.get("StuffGroupName2") or "").strip(),
                    partner_zone_route=(row.get("PartnerZoneAndRoute") or "").strip(),
                    monthly_totals={k: str(v) for k, v in amounts.items()},
                )
            )
        MonthlySaleDetailSnapshot.objects.bulk_create(objs, batch_size=200)
        return len(objs), 0

    def _upsert_sale_reversion_rows(self, snapshot, job, rows) -> tuple[int, int]:
        objs = [
            SaleReversionSnapshot(
                sync_job=job,
                snapshot=snapshot,
                reversion_code=str(row.get("ReversionCode") or ""),
                order_code=str(row.get("OrderCode") or ""),
                partner_code=str(row.get("PartnerCode") or ""),
                partner_name=(row.get("PartnerName") or "").strip(),
                reversion_amount=_dec(
                    row.get("ReversionPrice") or row.get("SaleReversionAmount")
                ),
                order_date=str(row.get("OrderDate") or ""),
                reversion_date=str(row.get("ReversionDate") or ""),
            )
            for row in rows
        ]
        SaleReversionSnapshot.objects.bulk_create(objs, batch_size=200)
        return len(objs), 0

    def _upsert_distribution_reversion_rows(self, snapshot, job, rows) -> tuple[int, int]:
        objs = [
            DistributionReversionSnapshot(
                sync_job=job,
                snapshot=snapshot,
                total_code=str(row.get("TotalCode") or ""),
                partner_code=str(row.get("PartnerCode") or ""),
                partner_name=(row.get("PartnerName") or "").strip(),
                driver_name=(row.get("DriverName") or "").strip(),
                amount=_dec(row.get("OrderFinal") or row.get("OrderPrice")),
                order_date=str(row.get("OrderDate") or ""),
            )
            for row in rows
        ]
        DistributionReversionSnapshot.objects.bulk_create(objs, batch_size=200)
        return len(objs), 0

    def _upsert_sale_order_line_rows(self, snapshot, job, rows) -> tuple[int, int]:
        from reports.models import SaleOrderLineSnapshot

        objs = []
        for idx, row in enumerate(rows):
            order_code = str(row.get("OrderCode") or "").strip()
            stuff_code = str(row.get("StuffCode") or "").strip()
            if not order_code or not stuff_code:
                continue
            row_key = str(row.get("_key") or "") or "|".join(
                [
                    order_code,
                    stuff_code,
                    str(row.get("StuffQuantity") or ""),
                    str(row.get("ArticleFinalPrice") or ""),
                    str(idx),
                ]
            )
            objs.append(
                SaleOrderLineSnapshot(
                    sync_job=job,
                    snapshot=snapshot,
                    row_key=row_key,
                    order_code=order_code,
                    order_pre_code=str(row.get("OrderPreCode") or "").strip(),
                    order_date=str(row.get("OrderDate") or "").strip(),
                    partner_code=str(row.get("PartnerCode") or "").strip(),
                    partner_name=(row.get("PartnerName") or "").strip(),
                    visitor_code=str(row.get("VisitorCode") or "").strip(),
                    visitor_name=(row.get("VisitorName") or "").strip(),
                    stuff_code=stuff_code,
                    stuff_name=(row.get("StuffName") or "").strip(),
                    stuff_group_name=(row.get("StuffGroupName") or "").strip(),
                    stuff_sub_group_name=(row.get("StuffSubGroupName") or "").strip(),
                    package_name=(row.get("Package") or "").strip(),
                    unit_name=(row.get("SmallPackage") or "").strip(),
                    package_quantity=_int(row.get("Quantity")),
                    stuff_quantity=_int(row.get("StuffQuantity")),
                    unit_fee=_dec(row.get("Fee")),
                    line_amount=_dec(row.get("ArticleFinalPrice")),
                    order_final_price=_dec(row.get("OrderFinalPrice")),
                    raw_data=dict(row),
                )
            )
        SaleOrderLineSnapshot.objects.bulk_create(objs, batch_size=200)
        return len(objs), 0

    def _upsert_sale_order_rows(self, snapshot, job, rows) -> tuple[int, int]:
        objs = []
        for row in rows:
            code = str(row.get("OrderCode") or "").strip()
            if not code:
                continue
            objs.append(
                SaleOrderSnapshot(
                    sync_job=job,
                    snapshot=snapshot,
                    order_code=code,
                    order_pre_code=str(row.get("OrderPreCode") or "").strip(),
                    order_date=str(row.get("OrderDate") or "").strip(),
                    partner_code=str(row.get("PartnerCode") or "").strip(),
                    partner_name=(row.get("PartnerName") or "").strip(),
                    visitor_code=str(row.get("VisitorCode") or "").strip(),
                    visitor_name=(row.get("VisitorName") or "").strip(),
                    order_final_price=_dec(row.get("OrderFinalPrice")),
                    finalized_cost=_dec(row.get("FinalizedCostForCustomer")),
                    sale_reversion_amount=_dec(row.get("SaleReversionAmount")),
                    stuffs_quantity_sum=_int(row.get("StuffsQuantitySum")),
                    pre_order_status=derive_pre_order_status(row),
                    raw_data=dict(row),
                )
            )
        SaleOrderSnapshot.objects.bulk_create(objs, batch_size=200)
        try:
            from reports.bot.notifications.tracker import InvoiceNotificationTracker

            pending = InvoiceNotificationTracker.process_orders(objs)
            InvoiceNotificationTracker.send_pending(pending)
        except Exception:
            logger.exception("bot invoice notification processing failed")
        return len(objs), 0

    def _upsert_sale_stuff_rows(self, snapshot, job, rows) -> tuple[int, int]:
        objs = []
        for row in rows:
            code = str(row.get("StuffCode") or "").strip()
            if not code:
                continue
            objs.append(
                SaleStuffSnapshot(
                    sync_job=job,
                    snapshot=snapshot,
                    stuff_code=code,
                    stuff_name=(row.get("StuffName") or "").strip(),
                    stuff_group_name=(row.get("StuffGroupName") or "").strip(),
                    stuff_sub_group_name=(row.get("StuffSubGroupName") or "").strip(),
                    sale_quantity=_int(row.get("SaleStuffQuantity")),
                    sale_amount=_dec(row.get("SaleSum")),
                    sale_reversion_quantity=_int(row.get("SaleReversionStuffQuantity")),
                    sale_reversion_amount=_dec(row.get("SaleReversionSum")),
                    pure_sale=_dec(row.get("PureSale")),
                )
            )
        SaleStuffSnapshot.objects.bulk_create(objs, batch_size=200)
        return len(objs), 0

    def _upsert_account_balance_rows(self, snapshot, job, rows) -> tuple[int, int]:
        from reports.constants import MONTH_BALANCE_KEYS

        objs = []
        for row in rows:
            code = str(row.get("PartnerCode") or "").strip()
            if not code:
                continue
            monthly = {
                key: str(_dec(row.get(key)))
                for key in MONTH_BALANCE_KEYS
            }
            total = sum((_dec(row.get(key)) for key in MONTH_BALANCE_KEYS), Decimal("0"))
            objs.append(
                AccountBalanceSnapshot(
                    sync_job=job,
                    snapshot=snapshot,
                    partner_code=code,
                    partner_name=(row.get("PartnerName") or "").strip(),
                    partner_legal_name=(row.get("PartnerLegalName") or "").strip(),
                    monthly_balances=monthly,
                    total_balance=total,
                )
            )
        AccountBalanceSnapshot.objects.bulk_create(objs, batch_size=200)
        return len(objs), 0

    def _upsert_receivable_aging_rows(self, snapshot, job, rows) -> tuple[int, int]:
        from reports.constants import AGING_BUCKET_KEYS

        objs = []
        for row in rows:
            visitor = str(row.get("VisitorCode") or "").strip()
            partner = str(row.get("PartnerCode") or "").strip()
            city = (row.get("CityName") or "").strip()
            zone = (row.get("ZoneName") or "").strip()
            row_key = str(row.get("_key") or "") or "|".join(
                [visitor, partner, city, zone]
            )
            if not row_key.strip():
                continue
            buckets = {key: str(_dec(row.get(key))) for key in AGING_BUCKET_KEYS}
            total = sum((_dec(row.get(key)) for key in AGING_BUCKET_KEYS), Decimal("0"))
            objs.append(
                ReceivableAgingSnapshot(
                    sync_job=job,
                    snapshot=snapshot,
                    row_key=row_key,
                    visitor_code=visitor,
                    visitor_name=(row.get("VisitorName") or "").strip(),
                    partner_code=partner,
                    partner_name=(row.get("PartnerName") or "").strip(),
                    city_name=city,
                    zone_name=zone,
                    route_name=(row.get("RouteName") or "").strip(),
                    bucket_amounts=buckets,
                    total_outstanding=total,
                )
            )
        ReceivableAgingSnapshot.objects.bulk_create(objs, batch_size=200)
        return len(objs), 0

    def _upsert_daily_metric(self, snapshot: KaraReportSnapshot) -> None:
        from reports.services.parsers import ReportParser
        from reports.services.report_registry import get_report_config

        config = get_report_config(PRIMARY_KPI_REPORT)
        kpis = ReportParser.extract_kpis(snapshot.sum_row_data, config)
        rows = flatten_rows(snapshot.raw_data)
        active = sum(
            1
            for r in rows
            if (_dec(r.get("TotalSale")) > 0 or _int(r.get("OrderCountBasedOnFinalOrder")) > 0)
        )
        metric_date = timezone.localdate().isoformat()
        DailyBusinessMetric.objects.update_or_create(
            metric_date=metric_date,
            source_report=PRIMARY_KPI_REPORT,
            defaults={
                "total_sale": _dec(kpis.get("total_sale", {}).get("raw")),
                "total_pure_sale": _dec(kpis.get("total_pure_sale", {}).get("raw")),
                "order_count": _int(kpis.get("final_order_count", {}).get("raw")),
                "distribution_reversion": _dec(
                    kpis.get("distribution_reversion", {}).get("raw")
                ),
                "sale_reversion": _dec(kpis.get("sale_reversion", {}).get("raw")),
                "settlement_remainder": _dec(
                    kpis.get("settlement_remainder", {}).get("raw")
                ),
                "active_visitors": active,
                "snapshot": snapshot,
            },
        )

    def _log(self, job: KaraSyncJob, level: str, message: str, **context) -> None:
        KaraSyncLog.objects.create(
            job=job, level=level, message=message, context=context or {}
        )

    def _set_connection_status(
        self,
        status: str,
        *,
        sync_ok: bool = False,
        error: str = "",
    ) -> None:
        conn = KaraConnection.get_active()
        if conn is None:
            from django.conf import settings

            conn = KaraConnection.objects.create(
                title="اتصال اصلی کارا",
                base_url=settings.KARA_BASE_URL,
                username=getattr(settings, "KARA_USERNAME", "") or "",
                is_active=True,
            )
        conn.connection_status = status
        if sync_ok:
            conn.last_successful_sync_at = timezone.now()
            conn.last_error_message = ""
        if error:
            conn.last_error_at = timezone.now()
            conn.last_error_message = error[:2000]
        info = self.client.get_session_info()
        if info.get("last_login_at"):
            try:
                conn.last_login_at = timezone.datetime.fromisoformat(info["last_login_at"])
                if timezone.is_naive(conn.last_login_at):
                    conn.last_login_at = timezone.make_aware(conn.last_login_at)
            except Exception:
                pass
        conn.save()
