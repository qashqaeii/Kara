"""
Background auto-refresh scheduler for Kara reports.

Each enabled report runs on its own suggested_interval_minutes with staggered
start offsets to avoid hammering Kara with concurrent DB load.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

_scheduler = None


def refresh_all_reports(triggered_by: str = "auto") -> dict:
    from reports.constants import SyncStatus
    from reports.exceptions import KaraError
    from reports.models import DashboardRefreshLog
    from reports.services.analytics import AnalyticsService
    from reports.services.sync import SyncOrchestrator

    log = DashboardRefreshLog.objects.create(
        status=DashboardRefreshLog.STATUS_RUNNING,
        triggered_by=triggered_by,
    )
    try:
        jobs = SyncOrchestrator().sync_all(triggered_by=triggered_by)
        ok = [j for j in jobs if j.status == SyncStatus.SUCCESS]
        failed = [j for j in jobs if j.status == SyncStatus.FAILED]
        log.reports_refreshed = len(ok)
        log.finished_at = timezone.now()
        if failed and not ok:
            log.status = DashboardRefreshLog.STATUS_ERROR
            log.error_message = failed[0].friendly_error or failed[0].error_message
            log.save()
            return {"success": False, "error": log.error_message, "count": 0}
        if failed:
            log.status = DashboardRefreshLog.STATUS_SUCCESS
            log.error_message = f"{len(failed)} گزارش ناموفق"
            log.save()
            AnalyticsService.evaluate_alerts()
            return {
                "success": True,
                "partial": True,
                "count": len(ok),
                "failed": [j.report_key for j in failed],
            }
        log.status = DashboardRefreshLog.STATUS_SUCCESS
        log.save()
        AnalyticsService.evaluate_alerts()
        logger.info("Auto-refresh completed: %d reports", len(ok))
        return {"success": True, "count": len(ok)}
    except KaraError as exc:
        log.status = DashboardRefreshLog.STATUS_ERROR
        log.error_message = str(exc)
        log.finished_at = timezone.now()
        log.save()
        logger.error("Auto-refresh failed: %s", exc)
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        log.status = DashboardRefreshLog.STATUS_ERROR
        log.error_message = str(exc)
        log.finished_at = timezone.now()
        log.save()
        logger.exception("Auto-refresh unexpected error")
        return {"success": False, "error": str(exc)}


def refresh_report(report_key: str, triggered_by: str = "auto") -> dict:
    """Sync a single report — used by per-report scheduler jobs."""
    from reports.constants import SyncStatus
    from reports.exceptions import KaraError
    from reports.services.analytics import AnalyticsService
    from reports.services.sync import SyncOrchestrator

    try:
        job = SyncOrchestrator().sync_report(report_key, triggered_by=triggered_by)
        ok = job.status == SyncStatus.SUCCESS
        if ok:
            try:
                AnalyticsService.evaluate_alerts()
            except Exception:
                logger.exception("Alert evaluation after sync failed")
        return {
            "success": ok,
            "report_key": report_key,
            "status": job.status,
            "error": job.friendly_error or job.error_message or "",
        }
    except KaraError as exc:
        logger.error("Scheduled sync failed for %s: %s", report_key, exc)
        return {"success": False, "report_key": report_key, "error": str(exc)}
    except Exception as exc:
        logger.exception("Scheduled sync unexpected error for %s", report_key)
        return {"success": False, "report_key": report_key, "error": str(exc)}


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return

    if not getattr(settings, "AUTO_REFRESH_ENABLED", True):
        return

    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.interval import IntervalTrigger

    from reports.services.report_registry import ReportRegistry

    _scheduler = BackgroundScheduler(timezone=settings.TIME_ZONE)
    now = timezone.now()
    stagger_seconds = int(getattr(settings, "AUTO_REFRESH_STAGGER_SECONDS", 50))

    for index, (key, cfg) in enumerate(ReportRegistry.syncable().items()):
        interval = max(1, int(cfg.suggested_interval_minutes or 15))
        # Spread first runs so Kara is not hit by every report at once.
        first_delay = 20 + (index * stagger_seconds)
        _scheduler.add_job(
            refresh_report,
            trigger=IntervalTrigger(minutes=interval),
            id=f"kara_sync_{key}",
            replace_existing=True,
            kwargs={"report_key": key, "triggered_by": "scheduler"},
            max_instances=1,
            coalesce=True,
            next_run_time=now + timedelta(seconds=first_delay),
        )
        logger.info(
            "Scheduled %s every %d min (first in %ds)",
            key,
            interval,
            first_delay,
        )

    _scheduler.start()
    logger.info(
        "Per-report auto-refresh scheduler started (%d jobs)",
        len(ReportRegistry.syncable()),
    )


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def scheduler_jobs() -> list[dict]:
    """Snapshot of scheduled jobs for the sync center UI."""
    if _scheduler is None:
        return []
    out = []
    try:
        for job in _scheduler.get_jobs():
            next_run = getattr(job, "next_run_time", None)
            report_key = ""
            if job.kwargs:
                report_key = job.kwargs.get("report_key") or ""
            out.append(
                {
                    "id": job.id,
                    "report_key": report_key,
                    "next_run_at": next_run.isoformat() if next_run else None,
                    "next_run_label": _format_next(next_run),
                }
            )
    except Exception:
        logger.exception("Failed to list scheduler jobs")
    return out


def _format_next(dt) -> str:
    if not dt:
        return "—"
    try:
        from reports.services.dates import format_jalali_datetime

        return format_jalali_datetime(dt)
    except Exception:
        return dt.isoformat()


def should_start_scheduler() -> bool:
    if os.environ.get("KARA_DISABLE_AUTO_REFRESH", "").lower() in ("1", "true", "yes"):
        return False
    if any(
        cmd in sys.argv
        for cmd in ("migrate", "makemigrations", "test", "shell", "kara_sync", "prune_db")
    ):
        return False

    # Production: only the dedicated scheduler service/process.
    if os.environ.get("KARA_RUN_SCHEDULER", "").lower() in ("1", "true", "yes"):
        return True

    # Development: Django runserver child process only (not Gunicorn/manage.py).
    if "runserver" in sys.argv and os.environ.get("RUN_MAIN") == "true":
        return True

    return False
