from django import template

from reports.services.dates import format_jalali_datetime, gregorian_to_jalali
from reports.services.display import (
    aging_bucket_label,
    period_preset_label,
    report_title,
    role_label,
    severity_label,
    sync_status_label,
    sync_trigger_label,
)

register = template.Library()


@register.filter
def get_item(dictionary, key):
    if dictionary is None:
        return None
    return dictionary.get(key)


@register.filter(name="jalali")
def jalali_filter(value):
    """Gregorian date/datetime → شمسی YYYY/MM/DD."""
    if value is None or value == "":
        return "—"
    return gregorian_to_jalali(value) or "—"


@register.filter(name="jalali_dt")
def jalali_dt_filter(value):
    """Gregorian datetime → شمسی YYYY/MM/DD HH:MM."""
    if value is None or value == "":
        return "—"
    return format_jalali_datetime(value) or "—"


@register.filter(name="jalali_dts")
def jalali_dts_filter(value):
    """Gregorian datetime → شمسی با ثانیه."""
    if value is None or value == "":
        return "—"
    return format_jalali_datetime(value, with_seconds=True) or "—"


@register.filter
def fa_report(key):
    return report_title(key) if key else "—"


@register.filter
def fa_sync_status(status):
    return sync_status_label(status) if status else "—"


@register.filter
def fa_trigger(triggered_by):
    return sync_trigger_label(triggered_by)


@register.filter
def fa_severity(severity):
    return severity_label(severity) if severity else "—"


@register.filter
def fa_role(role):
    return role_label(role) if role else "—"


@register.filter
def fa_period(preset):
    return period_preset_label(preset) if preset else "—"


@register.filter
def fa_bucket(key):
    return aging_bucket_label(key) if key else "—"


@register.simple_tag
def currency_unit():
    from reports.services.currency import currency_label

    return currency_label()
