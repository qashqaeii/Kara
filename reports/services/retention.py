"""Keep only live Kara snapshots so SQLite does not grow unbounded.

Dashboard reads the latest YTD snapshot plus daily metric tables.
Historical KPI rows (DailyBusinessMetric, etc.) are kept; superseded
JSON snapshots and raw API copies are not.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from reports.models import (
    AccountBalanceSnapshot,
    DashboardRefreshLog,
    DistributionReversionSnapshot,
    HeadVisitorSaleSnapshot,
    KaraRawResponse,
    KaraReportSnapshot,
    KaraSyncJob,
    MonthlySaleDetailSnapshot,
    ReceivableAgingSnapshot,
    SaleOrderSnapshot,
    SaleOrderLineSnapshot,
    SaleReversionSnapshot,
    SaleStuffSnapshot,
    StuffGroupSaleSnapshot,
    VisitorSaleSnapshot,
)
from reports.services.dates import parse_business_date

logger = logging.getLogger(__name__)

KIND_FULL = "full"
KIND_DAILY = "daily"

NORMALIZED_RAW_MODELS = (
    VisitorSaleSnapshot,
    HeadVisitorSaleSnapshot,
    StuffGroupSaleSnapshot,
    MonthlySaleDetailSnapshot,
    SaleReversionSnapshot,
    DistributionReversionSnapshot,
    SaleOrderSnapshot,
    SaleOrderLineSnapshot,
    SaleStuffSnapshot,
    AccountBalanceSnapshot,
    ReceivableAgingSnapshot,
)


def snapshot_kind(period_from: str = "", period_to: str = "") -> str:
    """YTD / multi-day windows are 'full'; same-day or empty dates are 'daily'."""
    pf = parse_business_date(period_from)
    pt = parse_business_date(period_to)
    if pf and pt and (pt - pf).days > 0:
        return KIND_FULL
    return KIND_DAILY


def slim_stored_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Drop bulky fields that the dashboard never reads from disk."""
    if not payload:
        return {}
    slim = dict(payload)
    slim.pop("html", None)
    return slim


def find_live_snapshot(
    report_key: str,
    personnel_code: str,
    period_from: str,
    period_to: str,
) -> KaraReportSnapshot | None:
    kind = snapshot_kind(period_from, period_to)
    qs = KaraReportSnapshot.objects.filter(
        report_key=report_key,
        personnel_code=personnel_code or "",
    ).order_by("-fetched_at")
    for snap in qs[:40]:
        if snapshot_kind(snap.period_from, snap.period_to) == kind:
            return snap
    return None


def find_latest_full_snapshot(
    report_key: str,
    personnel_code: str = "",
) -> KaraReportSnapshot | None:
    """Return the newest YTD / multi-day snapshot for a report."""
    qs = KaraReportSnapshot.objects.filter(
        report_key=report_key,
        personnel_code=personnel_code or "",
    ).order_by("-fetched_at")
    for snap in qs[:40]:
        if snapshot_kind(snap.period_from, snap.period_to) == KIND_FULL:
            return snap
    return None


def replace_superseded_snapshots(keep: KaraReportSnapshot) -> int:
    """Delete older snapshots of the same report / person / period-kind.

    CASCADE removes their normalized rows. Daily metric tables use SET_NULL
    and are left intact.
    """
    kind = snapshot_kind(keep.period_from, keep.period_to)
    stale_ids: list[int] = []
    qs = (
        KaraReportSnapshot.objects.filter(
            report_key=keep.report_key,
            personnel_code=keep.personnel_code or "",
        )
        .exclude(pk=keep.pk)
        .only("id", "period_from", "period_to")
    )
    for snap in qs:
        if snapshot_kind(snap.period_from, snap.period_to) == kind:
            stale_ids.append(snap.id)
    if not stale_ids:
        return 0
    deleted, _ = KaraReportSnapshot.objects.filter(id__in=stale_ids).delete()
    logger.info(
        "retention replaced %s stale snapshot(s) for %s kind=%s",
        len(stale_ids),
        keep.report_key,
        kind,
    )
    return deleted


def _keep_counts() -> tuple[int, int]:
    full = max(1, int(getattr(settings, "SNAPSHOT_KEEP_FULL", 1)))
    daily = max(1, int(getattr(settings, "SNAPSHOT_KEEP_DAILY", 1)))
    return full, daily


def prune_superseded_snapshots() -> int:
    keep_full, keep_daily = _keep_counts()
    groups: dict[tuple[str, str, str], list[tuple[Any, int]]] = defaultdict(list)
    for row in KaraReportSnapshot.objects.values(
        "id", "report_key", "personnel_code", "period_from", "period_to", "fetched_at"
    ):
        kind = snapshot_kind(row["period_from"], row["period_to"])
        groups[(row["report_key"], row["personnel_code"] or "", kind)].append(
            (row["fetched_at"], row["id"])
        )

    keep_ids: set[int] = set()
    for (_key, _person, kind), items in groups.items():
        items.sort(key=lambda item: item[0], reverse=True)
        limit = keep_full if kind == KIND_FULL else keep_daily
        for _fetched, sid in items[:limit]:
            keep_ids.add(sid)

    stale = KaraReportSnapshot.objects.exclude(id__in=keep_ids)
    count = stale.count()
    if count:
        stale.delete()
    return count


def prune_raw_responses() -> int:
    count = KaraRawResponse.objects.count()
    if count:
        KaraRawResponse.objects.all().delete()
    return count


def clear_normalized_raw_json() -> int:
    """Normalized columns already store typed fields; row JSON is unused."""
    updated = 0
    for model in NORMALIZED_RAW_MODELS:
        n = model.objects.exclude(raw_data={}).update(raw_data={})
        updated += n
    return updated


def slim_existing_snapshot_payloads() -> int:
    updated = 0
    for snap in KaraReportSnapshot.objects.iterator(chunk_size=20):
        data = snap.raw_data
        if not isinstance(data, dict) or "html" not in data:
            continue
        snap.raw_data = slim_stored_payload(data)
        snap.save(update_fields=["raw_data"])
        updated += 1
    return updated


def prune_sync_jobs() -> int:
    days = max(1, int(getattr(settings, "SYNC_JOB_RETENTION_DAYS", 14)))
    cutoff = timezone.now() - timedelta(days=days)
    live_job_ids = KaraReportSnapshot.objects.exclude(sync_job_id=None).values_list(
        "sync_job_id", flat=True
    )
    qs = KaraSyncJob.objects.filter(started_at__lt=cutoff).exclude(id__in=live_job_ids)
    count = qs.count()
    if count:
        qs.delete()
    return count


def prune_refresh_logs() -> int:
    keep = max(10, int(getattr(settings, "REFRESH_LOG_KEEP", 100)))
    ids = list(
        DashboardRefreshLog.objects.order_by("-started_at").values_list("id", flat=True)[
            :keep
        ]
    )
    qs = DashboardRefreshLog.objects.exclude(id__in=ids)
    count = qs.count()
    if count:
        qs.delete()
    return count


def vacuum_sqlite() -> bool:
    if connection.vendor != "sqlite":
        return False
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA auto_vacuum=INCREMENTAL")
        cursor.execute("VACUUM")
    return True


def prune_database(*, vacuum: bool = False) -> dict[str, int | bool]:
    """One-shot cleanup of accumulated sync JSON. Safe to re-run."""
    with transaction.atomic():
        stats: dict[str, int | bool] = {
            "raw_responses": prune_raw_responses(),
            "snapshots": prune_superseded_snapshots(),
            "normalized_raw_json": clear_normalized_raw_json(),
            "slimmed_payloads": slim_existing_snapshot_payloads(),
            "sync_jobs": prune_sync_jobs(),
            "refresh_logs": prune_refresh_logs(),
            "vacuum": False,
        }
    if vacuum:
        stats["vacuum"] = vacuum_sqlite()
    logger.info("database prune complete: %s", stats)
    return stats
