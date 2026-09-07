"""
Management command to import existing JSON report files into the database.
Useful for MVP testing without calling Kara API.
"""

import json
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from reports.models import KaraReportSnapshot
from reports.services.report_parser import flatten_rows
from reports.services.report_registry import ReportRegistry


class Command(BaseCommand):
    help = "Import report JSON files from data/ directory into KaraReportSnapshot"

    FILE_MAP = {
        "visitor_sale": "visitor_sale_report.json",
        "head_visitor_sale": "head_visitor_sale_report.json",
    }

    def handle(self, *args, **options):
        data_dir = Path(settings.BASE_DIR) / "data"
        imported = 0

        for report_key, filename in self.FILE_MAP.items():
            filepath = data_dir / filename
            if not filepath.exists():
                self.stdout.write(self.style.WARNING(f"فایل یافت نشد: {filepath}"))
                continue

            config = ReportRegistry.get(report_key)
            raw_data = json.loads(filepath.read_text(encoding="utf-8"))

            fetched_at_str = raw_data.get("fetched_at")
            if fetched_at_str:
                fetched_at = datetime.fromisoformat(fetched_at_str)
                if timezone.is_naive(fetched_at):
                    fetched_at = timezone.make_aware(fetched_at)
            else:
                fetched_at = timezone.now()

            rows = flatten_rows(raw_data)
            KaraReportSnapshot.objects.create(
                report_key=config.key,
                report_title=config.title,
                fetched_at=fetched_at,
                raw_data=raw_data,
                rows_count=len(rows),
            )
            imported += 1
            self.stdout.write(
                self.style.SUCCESS(f"[OK] {report_key}: {len(rows)} rows imported")
            )

        self.stdout.write(self.style.SUCCESS(f"Total: {imported} reports imported."))
