"""Period-over-period comparison for management KPIs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Max, Min
from django.utils import timezone

from reports.constants import DEFAULT_PERIOD_PRESET, PERIOD_PRESET_LABELS
from reports.models import DailyBusinessMetric
from reports.services.currency import display_float
from reports.services.dates import DateRange, gregorian_to_jalali


@dataclass(frozen=True)
class ComparisonResult:
    current: Decimal
    previous: Decimal
    absolute_change: Decimal
    percent_change: Decimal | None
    direction: str  # up | down | flat | unknown
    is_comparable: bool
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "current": float(self.current),
            "previous": float(self.previous),
            "absolute_change": float(self.absolute_change),
            "percent_change": float(self.percent_change) if self.percent_change is not None else None,
            "direction": self.direction,
            "is_comparable": self.is_comparable,
            "note": self.note,
        }


class PeriodComparisonService:
    PERIOD_PRESETS = dict(PERIOD_PRESET_LABELS)

    @classmethod
    def full_data_range(cls, *, end: date | None = None) -> DateRange | None:
        """Min/max business_date available in local analytics history."""
        agg = DailyBusinessMetric.objects.aggregate(
            start=Min("business_date"),
            end=Max("business_date"),
        )
        if not agg["start"] or not agg["end"]:
            today = end or timezone.localdate()
            return DateRange(today, today)
        return DateRange(agg["start"], agg["end"])

    @classmethod
    def resolve_range(cls, preset: str, *, end: date | None = None) -> DateRange | None:
        today = end or timezone.localdate()
        if preset in ("all", "full", ""):
            return cls.full_data_range(end=today)
        if preset == "today":
            return DateRange(today, today)
        if preset == "yesterday":
            d = today - timedelta(days=1)
            return DateRange(d, d)
        if preset == "current_week":
            # Iranian week starts Saturday (not Monday).
            start = today - timedelta(days=(today.weekday() + 2) % 7)
            return DateRange(start, today)
        if preset == "previous_week":
            this_start = today - timedelta(days=(today.weekday() + 2) % 7)
            end_pw = this_start - timedelta(days=1)
            start_pw = end_pw - timedelta(days=6)
            return DateRange(start_pw, end_pw)
        if preset == "current_month":
            return DateRange(today.replace(day=1), today)
        if preset == "previous_month":
            first_this = today.replace(day=1)
            end_pm = first_this - timedelta(days=1)
            start_pm = end_pm.replace(day=1)
            return DateRange(start_pm, end_pm)
        if preset == "last_7_days":
            return DateRange(today - timedelta(days=6), today)
        if preset == "last_30_days":
            return DateRange(today - timedelta(days=29), today)
        return None

    @classmethod
    def comparison_range(cls, preset: str) -> tuple[DateRange | None, DateRange | None]:
        """Return (current_range, previous_range) for a preset."""
        current = cls.resolve_range(preset or DEFAULT_PERIOD_PRESET)
        if current is None:
            return None, None
        # Full history has no meaningful prior window.
        if (preset or DEFAULT_PERIOD_PRESET) in ("all", "full", ""):
            return current, None

        length = (current.end - current.start).days + 1
        prev_end = current.start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=length - 1)
        previous = DateRange(prev_start, prev_end)
        return current, previous

    @classmethod
    def uses_latest_snapshot(cls, preset: str) -> bool:
        """
        Full-data mode reads the latest period snapshot (YTD/all), not a sum of days.

        Summing daily rows mixes true daily deltas with full-period dumps and inflates KPIs.
        """
        return (preset or DEFAULT_PERIOD_PRESET) in ("all", "full", "")

    @classmethod
    def sum_metric(
        cls,
        field: str,
        date_range: DateRange,
    ) -> Decimal:
        qs = DailyBusinessMetric.objects.filter(
            business_date__gte=date_range.start,
            business_date__lte=date_range.end,
        )
        # One row per business_date (dedupe duplicate metric_date keys).
        latest_ids = (
            qs.values("business_date")
            .annotate(mid=Max("id"))
            .values_list("mid", flat=True)
        )
        total = Decimal("0")
        for row in DailyBusinessMetric.objects.filter(id__in=latest_ids):
            total += Decimal(getattr(row, field, 0) or 0)
        return total

    @classmethod
    def compare_field(cls, field: str, preset: str = DEFAULT_PERIOD_PRESET) -> ComparisonResult:
        current_range, previous_range = cls.comparison_range(preset)
        if not current_range:
            return ComparisonResult(
                current=Decimal("0"),
                previous=Decimal("0"),
                absolute_change=Decimal("0"),
                percent_change=None,
                direction="unknown",
                is_comparable=False,
                note="بازه نامعتبر",
            )
        if not previous_range:
            # "all" or no prior window — show current only.
            if cls.uses_latest_snapshot(preset):
                latest = (
                    DailyBusinessMetric.objects.filter(
                        business_date__gte=current_range.start,
                        business_date__lte=current_range.end,
                    )
                    .order_by("-business_date", "-id")
                    .first()
                )
                current_val = Decimal(getattr(latest, field, 0) or 0) if latest else Decimal("0")
            else:
                current_val = cls.sum_metric(field, current_range)
            return ComparisonResult(
                current=current_val,
                previous=Decimal("0"),
                absolute_change=Decimal("0"),
                percent_change=None,
                direction="flat",
                is_comparable=False,
                note="مقایسه دوره‌ای برای کل داده‌ها تعریف نشده",
            )

        current_val = cls.sum_metric(field, current_range)
        previous_val = cls.sum_metric(field, previous_range)

        current_days = (
            DailyBusinessMetric.objects.filter(
                business_date__gte=current_range.start,
                business_date__lte=current_range.end,
            )
            .values("business_date")
            .distinct()
            .count()
        )
        previous_days = (
            DailyBusinessMetric.objects.filter(
                business_date__gte=previous_range.start,
                business_date__lte=previous_range.end,
            )
            .values("business_date")
            .distinct()
            .count()
        )
        # Need meaningful coverage in both windows before showing % change.
        min_days = max(1, (current_range.end - current_range.start).days // 2)
        if current_days < min_days or previous_days < min_days:
            return ComparisonResult(
                current=current_val,
                previous=previous_val,
                absolute_change=current_val - previous_val,
                percent_change=None,
                direction="unknown",
                is_comparable=False,
                note="داده تاریخی کافی نیست — Backfill اجرا کنید",
            )

        if current_val == 0 and previous_val == 0:
            return ComparisonResult(
                current=current_val,
                previous=previous_val,
                absolute_change=Decimal("0"),
                percent_change=None,
                direction="flat",
                is_comparable=False,
                note="داده تاریخی کافی نیست — Backfill اجرا کنید",
            )

        change = current_val - previous_val
        if previous_val == 0:
            return ComparisonResult(
                current=current_val,
                previous=previous_val,
                absolute_change=change,
                percent_change=None,
                direction="up" if change > 0 else ("down" if change < 0 else "flat"),
                is_comparable=False,
                note="دوره قبل صفر بود",
            )

        pct = (change / previous_val * 100).quantize(Decimal("0.1"))
        # Cap absurd percentages from sparse/incomplete prior windows.
        if abs(pct) > Decimal("500"):
            return ComparisonResult(
                current=current_val,
                previous=previous_val,
                absolute_change=change,
                percent_change=None,
                direction="up" if change > 0 else ("down" if change < 0 else "flat"),
                is_comparable=False,
                note="تغییر دوره قابل اتکا نیست (داده ناقص)",
            )

        direction = "up" if change > 0 else ("down" if change < 0 else "flat")
        return ComparisonResult(
            current=current_val,
            previous=previous_val,
            absolute_change=change,
            percent_change=pct,
            direction=direction,
            is_comparable=True,
            note="",
        )

    @classmethod
    def trend_series(
        cls,
        field: str,
        *,
        days: int = 7,
        end: date | None = None,
        start: date | None = None,
    ) -> list[dict[str, Any]]:
        today = end or timezone.localdate()
        if start is not None:
            range_start = start
        else:
            range_start = today - timedelta(days=max(days, 1) - 1)
        # Cap very long series for chart readability.
        max_points = 120
        if (today - range_start).days + 1 > max_points:
            range_start = today - timedelta(days=max_points - 1)
        rows = {
            m.business_date: m
            for m in DailyBusinessMetric.objects.filter(
                business_date__gte=range_start,
                business_date__lte=today,
            ).order_by("business_date", "id")
        }
        series = []
        d = range_start
        while d <= today:
            m = rows.get(d)
            value = float(getattr(m, field, 0) or 0) if m else 0
            series.append(
                {
                    "date": d.isoformat(),
                    "date_label": gregorian_to_jalali(d),
                    "value": display_float(value),
                    "value_rial": value,
                }
            )
            d += timedelta(days=1)
        return series
