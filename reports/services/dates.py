"""Central date handling — storage ISO, display Jalali where needed."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import NamedTuple

from django.utils import timezone


class DateRange(NamedTuple):
    start: date
    end: date


def parse_business_date(value: str | date | datetime | None) -> date | None:
    """Parse Kara date strings (1405/04/01 or 1405-04-01) or datetime."""
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return timezone.localtime(value).date() if timezone.is_aware(value) else value.date()

    text = str(value).strip()
    if not text:
        return None

    # ISO yyyy-mm-dd
    if len(text) >= 10 and text[4] == "-":
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            pass

    # Jalali yyyy/mm/dd or yyyy-mm-dd (Persian calendar years ~1300–1600).
    # Gregorian years (e.g. 2026) must NOT be treated as Jalali.
    parts = text.replace("-", "/").split("/")
    if len(parts) == 3:
        try:
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
            if 1300 <= y <= 1600:
                return jalali_to_gregorian(y, m, d)
            return date(y, m, d)
        except (ValueError, TypeError):
            return None
    return None


def jalali_to_gregorian(jy: int, jm: int, jd: int) -> date:
    try:
        import jdatetime

        return jdatetime.date(jy, jm, jd).togregorian()
    except ImportError:
        # Fallback: treat as Gregorian if jdatetime missing
        return date(jy, jm, jd)


def gregorian_to_jalali(d: date | datetime | str | None) -> str:
    """Format a date/datetime/ISO string as Jalali YYYY/MM/DD for UI display."""
    if d is None or d == "":
        return ""
    if isinstance(d, str):
        parsed = parse_business_date(d)
        if parsed is None:
            # datetime ISO with time: 2026-07-30T14:55:00+03:30
            try:
                text = d.replace("Z", "+00:00")
                dt = datetime.fromisoformat(text)
                d = timezone.localtime(dt) if timezone.is_aware(dt) else dt
            except ValueError:
                return d
        else:
            d = parsed
    if isinstance(d, datetime):
        d = timezone.localtime(d).date() if timezone.is_aware(d) else d.date()
    if not isinstance(d, date):
        return str(d)
    try:
        import jdatetime

        j = jdatetime.date.fromgregorian(date=d)
        return f"{j.year:04d}/{j.month:02d}/{j.day:02d}"
    except ImportError:
        return d.isoformat()
    except (TypeError, ValueError):
        return str(d)


def format_jalali_datetime(
    value: date | datetime | str | None, *, with_seconds: bool = False
) -> str:
    """Jalali date + time for UI (e.g. 1405/05/08 14:30)."""
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        try:
            text = value.replace("Z", "+00:00")
            value = datetime.fromisoformat(text)
        except ValueError:
            # date-only string
            parsed = parse_business_date(value)
            return gregorian_to_jalali(parsed) if parsed else value
    if isinstance(value, datetime):
        dt = timezone.localtime(value) if timezone.is_aware(value) else value
        date_part = gregorian_to_jalali(dt.date())
        if with_seconds:
            return f"{date_part} {dt.strftime('%H:%M:%S')}"
        return f"{date_part} {dt.strftime('%H:%M')}"
    return gregorian_to_jalali(value)


def snapshot_business_date(
    *,
    period_to: str = "",
    period_from: str = "",
    fetched_at: datetime | None = None,
) -> date:
    """Resolve the business date a snapshot represents."""
    for candidate in (period_to, period_from):
        parsed = parse_business_date(candidate)
        if parsed:
            return parsed
    if fetched_at:
        return timezone.localtime(fetched_at).date()
    return timezone.localdate()


def date_range_days(start: date, end: date) -> list[date]:
    if end < start:
        return []
    days: list[date] = []
    cur = start
    while cur <= end:
        days.append(cur)
        cur += timedelta(days=1)
    return days
