import json
import logging

from django.apps import AppConfig
from django.db.backends.signals import connection_created

logger = logging.getLogger(__name__)


def _configure_sqlite(sender, connection, **kwargs):
    if connection.vendor != "sqlite":
        return
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA busy_timeout=30000;")


connection_created.connect(_configure_sqlite)


class ReportsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "reports"
    verbose_name = "گزارش‌های کارا"

    def ready(self) -> None:
        from reports.constants import apply_feature_flags_from_settings

        apply_feature_flags_from_settings()

        from reports.services.auto_refresh import should_start_scheduler, start_scheduler

        if should_start_scheduler():
            try:
                start_scheduler()
            except Exception:
                logger.exception("Failed to start auto-refresh scheduler")
