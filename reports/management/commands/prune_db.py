"""Compact local SQLite: drop superseded snapshots and reclaim disk.

Examples:
  python manage.py prune_db
  python manage.py prune_db --vacuum
"""

from __future__ import annotations

import os

from django.conf import settings
from django.core.management.base import BaseCommand

from reports.services.retention import prune_database


class Command(BaseCommand):
    help = "پاکسازی اسنپ‌شات‌های قدیمی و بهینه‌سازی حجم دیتابیس"

    def add_arguments(self, parser):
        parser.add_argument(
            "--vacuum",
            action="store_true",
            help="بازنویسی فایل SQLite تا فضای آزاد واقعاً از دیسک آزاد شود",
        )

    def handle(self, *args, **options):
        vacuum = bool(options["vacuum"])
        db_path = settings.DATABASES["default"].get("NAME")
        before = 0
        if db_path and os.path.exists(db_path):
            before = os.path.getsize(db_path)

        stats = prune_database(vacuum=vacuum)

        after = before
        if db_path and os.path.exists(db_path):
            after = os.path.getsize(db_path)

        self.stdout.write(
            self.style.SUCCESS(
                "prune done - "
                f"raw={stats['raw_responses']} "
                f"snapshots={stats['snapshots']} "
                f"row_json={stats['normalized_raw_json']} "
                f"slimmed={stats['slimmed_payloads']} "
                f"jobs={stats['sync_jobs']} "
                f"refresh_logs={stats['refresh_logs']} "
                f"vacuum={stats['vacuum']}"
            )
        )
        if before:
            self.stdout.write(
                f"db size: {before / 1024 / 1024:.1f} MB -> {after / 1024 / 1024:.1f} MB"
            )
