"""User-facing Persian labels — never show English keys/status in UI."""

from __future__ import annotations

from reports.constants import (
    AGING_BUCKET_LABELS,
    ALERT_SEVERITY_LABELS,
    ALERT_STATUS_LABELS,
    KARA_ROLE_LABELS,
    PERIOD_PRESET_LABELS,
    SYNC_STATUS_LABELS,
    SYNC_TRIGGER_LABELS,
    AlertSeverity,
    AlertStatus,
    KaraRole,
    SyncStatus,
)


def report_title(report_key: str) -> str:
    """Persian title for a report key; falls back to key only if unknown."""
    try:
        from reports.services.report_registry import ReportRegistry

        return ReportRegistry.get(report_key).title
    except Exception:
        return report_key


def sync_status_label(status: str) -> str:
    try:
        return SYNC_STATUS_LABELS.get(SyncStatus(status), status)
    except ValueError:
        return status


def sync_trigger_label(triggered_by: str) -> str:
    if not triggered_by:
        return "—"
    return SYNC_TRIGGER_LABELS.get(triggered_by, triggered_by)


def severity_label(severity: str) -> str:
    try:
        return ALERT_SEVERITY_LABELS.get(AlertSeverity(severity), severity)
    except ValueError:
        return severity


def alert_status_label(status: str) -> str:
    try:
        return ALERT_STATUS_LABELS.get(AlertStatus(status), status)
    except ValueError:
        return status


def role_label(role: str) -> str:
    try:
        return KARA_ROLE_LABELS.get(KaraRole(role), role)
    except ValueError:
        return role


def period_preset_label(preset: str) -> str:
    return PERIOD_PRESET_LABELS.get(preset, preset)


def aging_bucket_label(key: str) -> str:
    return AGING_BUCKET_LABELS.get(key, key.replace("M", "ماه "))
