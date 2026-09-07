"""Sync Kara reports into the local database.

Examples:
  python manage.py kara_sync --report visitor_sale
  python manage.py kara_sync --all
  python manage.py kara_sync --all --from-date=1405/01/01 --to-date=1405/01/31
  python manage.py kara_sync --test-connection
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from reports.constants import SyncStatus
from reports.services.analytics import AnalyticsService
from reports.services.kara_client import KaraClient
from reports.services.report_registry import ReportRegistry
from reports.services.sync import SyncOrchestrator
from reports.services.tenant_id_loader import tenant_ids_status

TENANT_SENSITIVE_REPORTS = frozenset(
    {"stuff_group_sale", "monthly_sale", "sale_orders", "sale_orders_with_stuffs"}
)


class Command(BaseCommand):
    help = "همگام‌سازی گزارش‌های کارا با دیتابیس محلی"

    def add_arguments(self, parser):
        parser.add_argument("--report", type=str, help="کلید گزارش (مثلاً visitor_sale)")
        parser.add_argument("--all", action="store_true", help="همگام‌سازی همه گزارش‌های فعال")
        parser.add_argument("--from-date", type=str, default="", help="از تاریخ شمسی")
        parser.add_argument("--to-date", type=str, default="", help="تا تاریخ شمسی")
        parser.add_argument("--test-connection", action="store_true", help="تست اتصال کارا")
        parser.add_argument("--evaluate-alerts", action="store_true", help="اجرای قوانین هشدار")

    def handle(self, *args, **options):
        if options["test_connection"]:
            result = KaraClient().test_connection()
            if result["ok"]:
                self.stdout.write(self.style.SUCCESS(f"OK connection ({result['duration_ms']}ms)"))
            else:
                raise CommandError(result.get("error") or "connection failed")
            return

        if options["evaluate_alerts"]:
            alerts = AnalyticsService.evaluate_alerts()
            self.stdout.write(self.style.SUCCESS(f"alerts checked: {len(alerts)}"))
            return

        orchestrator = SyncOrchestrator()
        from_date = options["from_date"] or ""
        to_date = options["to_date"] or ""

        if options["all"]:
            jobs = orchestrator.sync_all(
                triggered_by="command",
                from_date=from_date,
                to_date=to_date,
            )
            ok = sum(1 for j in jobs if j.status == SyncStatus.SUCCESS)
            fail = sum(1 for j in jobs if j.status == SyncStatus.FAILED)
            self.stdout.write(
                self.style.SUCCESS(f"done — ok: {ok} | failed: {fail}")
            )
            for job in jobs:
                mark = "OK" if job.status == SyncStatus.SUCCESS else "FAIL"
                self.stdout.write(
                    f"  [{mark}] {job.report_key}: {job.status} "
                    f"(received={job.received_count}, skipped={job.skipped_count})"
                )
                if (
                    job.report_key in TENANT_SENSITIVE_REPORTS
                    and job.received_count == 0
                    and job.skipped_count == 0
                ):
                    self.stdout.write(
                        self.style.WARNING(
                            f"      0 rows — check tenant IDs / date range for {job.report_key}"
                        )
                    )
                if job.friendly_error:
                    # Avoid Windows cp1252 crash on Persian messages
                    try:
                        self.stdout.write(self.style.ERROR(f"      {job.friendly_error}"))
                    except UnicodeEncodeError:
                        self.stderr.write(f"      error_status={job.status}")
            return

        report = options.get("report")
        if not report:
            raise CommandError("Specify --report or --all or --test-connection.")

        try:
            ReportRegistry.get(report)
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        job = orchestrator.sync_report(
            report,
            triggered_by="command",
            from_date=from_date,
            to_date=to_date,
        )
        if job.status == SyncStatus.SUCCESS:
            self.stdout.write(
                self.style.SUCCESS(
                    f"{report}: ok — {job.received_count} rows "
                    f"(insert={job.inserted_count}, skip={job.skipped_count})"
                )
            )
        else:
            msg = job.friendly_error or job.error_message or job.status
            raise CommandError(f"{report}: {job.status} — {msg}")
