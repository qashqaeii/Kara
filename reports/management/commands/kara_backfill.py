"""Backfill historical Kara report data day by day."""

from __future__ import annotations

import time

from django.core.management.base import BaseCommand

from reports.constants import SyncStatus
from reports.models import BackfillRun, KaraSyncJob
from reports.services.analytics_pipeline import AnalyticsPipeline
from reports.services.dates import date_range_days, gregorian_to_jalali, parse_business_date
from reports.services.sync import SyncOrchestrator


class Command(BaseCommand):
    help = "Backfill Kara reports for a date range (day by day)."

    def add_arguments(self, parser):
        parser.add_argument("--from-date", required=True)
        parser.add_argument("--to-date", required=True)
        parser.add_argument(
            "--reports",
            default="visitor_sale,head_visitor_sale,stuff_group_sale,sale_orders,sale_orders_with_stuffs,sale_stuffs,monthly_sale",
        )
        parser.add_argument("--delay", type=float, default=2.0)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--resume-id", type=int, default=None)

    def handle(self, *args, **options):
        from_date = parse_business_date(options["from_date"])
        to_date = parse_business_date(options["to_date"])
        if not from_date or not to_date:
            self.stderr.write("Invalid from-date or to-date")
            return

        reports = [r.strip() for r in options["reports"].split(",") if r.strip()]
        delay = options["delay"]
        dry_run = options["dry_run"]

        if options["resume_id"]:
            run = BackfillRun.objects.get(pk=options["resume_id"])
        else:
            run = BackfillRun.objects.create(
                from_date=from_date,
                to_date=to_date,
                reports=reports,
                status=SyncStatus.RUNNING,
                dry_run=dry_run,
                delay_seconds=int(delay),
            )

        completed = set(run.completed_dates or [])
        days = date_range_days(from_date, to_date)
        orchestrator = SyncOrchestrator()
        failed_days: list[str] = []

        def sync_with_retry(report_key: str, *, jalali: str) -> KaraSyncJob:
            last_job: KaraSyncJob | None = None
            for attempt in range(5):
                last_job = orchestrator.sync_report(
                    report_key,
                    triggered_by="backfill",
                    from_date=jalali,
                    to_date=jalali,
                )
                if last_job.status == SyncStatus.SUCCESS:
                    return last_job
                if (
                    last_job.status == SyncStatus.CANCELLED
                    and "هم‌زمان" in (last_job.error_message or "")
                    and attempt < 4
                ):
                    wait = 3 * (attempt + 1)
                    self.stdout.write(
                        self.style.WARNING(
                            f"  Lock busy for {report_key}, retry in {wait}s"
                        )
                    )
                    time.sleep(wait)
                    continue
                return last_job
            return last_job  # type: ignore[return-value]

        for day in days:
            day_key = day.isoformat()
            if day_key in completed:
                self.stdout.write(f"Skip {day_key} (done)")
                continue

            jalali = gregorian_to_jalali(day)
            self.stdout.write(f"Backfill {jalali} ({day_key})")
            run.current_date = day
            run.save(update_fields=["current_date", "updated_at"])

            if dry_run:
                completed.add(day_key)
                continue

            day_ok = True
            for report_key in reports:
                job = sync_with_retry(report_key, jalali=jalali)
                if job.status not in (SyncStatus.SUCCESS,):
                    day_ok = False
                    self.stderr.write(f"  Failed {report_key}: {job.friendly_error}")

            if day_ok:
                AnalyticsPipeline.rebuild(report_key=None, from_date=day, to_date=day)
                completed.add(day_key)
                run.completed_dates = sorted(completed)
                run.save(update_fields=["completed_dates", "updated_at"])
            else:
                failed_days.append(day_key)

            if delay > 0:
                time.sleep(delay)

        if failed_days:
            run.status = SyncStatus.PARTIAL
            run.save(update_fields=["status", "updated_at"])
            self.stdout.write(
                self.style.WARNING(
                    f"Backfill run {run.id} partial — failed days: {len(failed_days)} "
                    f"({', '.join(failed_days)})"
                )
            )
            return

        run.status = SyncStatus.SUCCESS
        run.save(update_fields=["status", "updated_at"])
        self.stdout.write(self.style.SUCCESS(f"Backfill run {run.id} completed"))
