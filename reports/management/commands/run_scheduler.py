"""Run the APScheduler background sync in a dedicated process."""

from __future__ import annotations

import signal
import time

from django.core.management.base import BaseCommand

from reports.services.auto_refresh import start_scheduler, stop_scheduler


class Command(BaseCommand):
    help = "Run Kara report auto-refresh scheduler (production dedicated service)"

    def handle(self, *args, **options):
        start_scheduler()
        self.stdout.write(self.style.SUCCESS("Scheduler started — waiting for jobs"))

        def _shutdown(signum, frame):
            self.stdout.write(self.style.WARNING(f"Signal {signum} received — stopping scheduler"))
            stop_scheduler()
            raise SystemExit(0)

        signal.signal(signal.SIGTERM, _shutdown)
        signal.signal(signal.SIGINT, _shutdown)

        try:
            while True:
                time.sleep(60)
        finally:
            stop_scheduler()
