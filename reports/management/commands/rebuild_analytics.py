"""Rebuild analytics metrics from stored snapshots."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from reports.services.analytics_pipeline import AnalyticsPipeline
from reports.services.dates import parse_business_date


class Command(BaseCommand):
    help = "Rebuild daily analytics metrics from KaraReportSnapshot data."

    def add_arguments(self, parser):
        parser.add_argument("--from-date", dest="from_date", default="")
        parser.add_argument("--to-date", dest="to_date", default="")
        parser.add_argument("--report", dest="report", default="")

    def handle(self, *args, **options):
        from_date = parse_business_date(options["from_date"]) if options["from_date"] else None
        to_date = parse_business_date(options["to_date"]) if options["to_date"] else None
        report = options["report"] or None

        stats = AnalyticsPipeline.rebuild(
            report_key=report,
            from_date=from_date,
            to_date=to_date,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Analytics rebuild: processed={stats['processed']} "
                f"skipped={stats['skipped']} failed={stats['failed']}"
            )
        )
