"""Rich context builder for salesperson detail page."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db.models import Sum

from reports.models import SalespersonDailyMetric, VisitorSaleSnapshot
from reports.services.currency import currency_label, display_float, format_money_number
from reports.services.dates import gregorian_to_jalali
from reports.services.period_comparison import PeriodComparisonService
from reports.services.ranking_pages import PERIOD_OPTIONS, period_context


def _dec(v) -> Decimal:
    if v is None:
        return Decimal("0")
    return Decimal(str(v))


def build_salesperson_detail(personnel_code: str, *, preset: str = "all") -> dict[str, Any]:
    code = (personnel_code or "").strip()
    dr, _ = PeriodComparisonService.comparison_range(preset)
    qs_all = SalespersonDailyMetric.objects.filter(personnel_code=code).order_by("business_date")
    qs = qs_all
    if dr:
        qs = qs_all.filter(business_date__gte=dr.start, business_date__lte=dr.end)

    rows = list(qs)
    if not rows:
        # Fall back to all history if selected period is empty
        rows = list(qs_all)
        period_note = "در بازه انتخابی داده‌ای نبود — کل تاریخچه نمایش داده می‌شود."
    else:
        period_note = ""

    latest = rows[-1] if rows else None
    snap = (
        VisitorSaleSnapshot.objects.filter(visitor_code=code)
        .order_by("-last_seen_at")
        .first()
    )

    name = (
        (latest.personnel_name if latest else "")
        or (snap.visitor_name if snap else "")
        or code
    )
    supervisor_code = (
        (latest.supervisor_code if latest else "")
        or (snap.head_visitor_code if snap else "")
    )
    supervisor_name = (
        (latest.supervisor_name if latest else "")
        or (snap.head_visitor_name if snap else "")
        or "—"
    )

    total_sale = sum((_dec(r.total_sale) for r in rows), Decimal("0"))
    total_pure = sum((_dec(r.total_pure_sale) for r in rows), Decimal("0"))
    orders = sum(int(r.final_order_count or 0) for r in rows)
    preorders = sum(int(r.preorder_count or 0) for r in rows)
    sale_rev = sum((_dec(r.sale_reversion) for r in rows), Decimal("0"))
    dist_rev = sum((_dec(r.distribution_reversion) for r in rows), Decimal("0"))
    active_days = sum(1 for r in rows if _dec(r.total_sale) > 0)
    avg_order = (total_sale / orders) if orders else Decimal("0")
    avg_daily_pure = (total_pure / len(rows)) if rows else Decimal("0")
    activity_rate = (
        (Decimal(active_days) / Decimal(len(rows)) * 100).quantize(Decimal("0.1"))
        if rows
        else Decimal("0")
    )
    rev_rate = (
        ((sale_rev + dist_rev) / total_sale * 100).quantize(Decimal("0.1"))
        if total_sale > 0
        else Decimal("0")
    )
    consistency = _consistency_score([_dec(r.total_pure_sale) for r in rows])

    # Best / worst day by pure sale
    best = max(rows, key=lambda r: _dec(r.total_pure_sale)) if rows else None
    worst = min(rows, key=lambda r: _dec(r.total_pure_sale)) if rows else None

    # Peer rank in period
    rank_info = _peer_rank(code, dr=dr, total_sale=total_sale)

    # Team average (same supervisor)
    team = _team_comparison(supervisor_code, code, dr=dr, total_sale=total_sale)

    # Trend direction: last 3 vs previous 3
    trend_insight = _trend_insight(rows)

    history = []
    max_pure = max((_dec(r.total_pure_sale) for r in rows), default=Decimal("1")) or Decimal("1")
    for r in reversed(rows):  # newest first for table
        pure = _dec(r.total_pure_sale)
        history.append(
            {
                "business_date": r.business_date,
                "date_label": gregorian_to_jalali(r.business_date),
                "total_sale": float(r.total_sale or 0),
                "total_sale_formatted": format_money_number(r.total_sale),
                "total_pure_sale": float(pure),
                "total_pure_sale_formatted": format_money_number(pure),
                "order_count": int(r.final_order_count or 0),
                "preorder_count": int(r.preorder_count or 0),
                "avg_order_formatted": format_money_number(r.average_order_value),
                "sale_reversion_formatted": format_money_number(r.sale_reversion),
                "distribution_reversion_formatted": format_money_number(r.distribution_reversion),
                "reversion_rate": float(r.reversion_rate or 0),
                "share_of_best": float((pure / max_pure * 100).quantize(Decimal("0.1"))),
                "is_active": bool(r.is_active and pure > 0),
            }
        )

    chart_pure = [
        {
            "date": r.business_date.isoformat(),
            "date_label": gregorian_to_jalali(r.business_date),
            "value": display_float(r.total_pure_sale),
        }
        for r in rows
    ]
    chart_orders = [
        {
            "date": r.business_date.isoformat(),
            "date_label": gregorian_to_jalali(r.business_date),
            "value": int(r.final_order_count or 0),
        }
        for r in rows
    ]
    chart_reversion = [
        {
            "date": r.business_date.isoformat(),
            "date_label": gregorian_to_jalali(r.business_date),
            "value": float(r.reversion_rate or 0),
        }
        for r in rows
    ]

    insights = _build_insights(
        name=name,
        total_sale=total_sale,
        rev_rate=rev_rate,
        best=best,
        worst=worst,
        rank_info=rank_info,
        team=team,
        trend_insight=trend_insight,
        active_days=active_days,
        day_count=len(rows),
        consistency=consistency,
    )

    initials = "".join(part[0] for part in name.split()[:2] if part) or "؟"

    ctx = period_context(preset)
    ctx.update(
        {
            "personnel_code": code,
            "name": name,
            "initials": initials,
            "supervisor_code": supervisor_code,
            "supervisor_name": supervisor_name,
            "period_note": period_note,
            "has_data": bool(rows),
            "day_count": len(rows),
            "active_days": active_days,
            "date_from_label": gregorian_to_jalali(rows[0].business_date) if rows else "—",
            "date_to_label": gregorian_to_jalali(rows[-1].business_date) if rows else "—",
            "kpis": {
                "total_sale": {
                    "label": "فروش نهایی",
                    "formatted": format_money_number(total_sale),
                    "numeric": display_float(total_sale),
                },
                "total_pure_sale": {
                    "label": "فروش خالص",
                    "formatted": format_money_number(total_pure),
                    "numeric": display_float(total_pure),
                },
                "orders": {"label": "سفارش نهایی", "formatted": f"{orders:,}", "numeric": orders},
                "preorders": {
                    "label": "پیش‌سفارش",
                    "formatted": f"{preorders:,}",
                    "numeric": preorders,
                },
                "avg_order": {
                    "label": "میانگین سفارش",
                    "formatted": format_money_number(avg_order),
                    "numeric": display_float(avg_order),
                },
                "sale_reversion": {
                    "label": "برگشت فروش",
                    "formatted": format_money_number(sale_rev),
                    "numeric": display_float(sale_rev),
                },
                "distribution_reversion": {
                    "label": "برگشت توزیع",
                    "formatted": format_money_number(dist_rev),
                    "numeric": display_float(dist_rev),
                },
                "reversion_rate": {
                    "label": "نرخ برگشت",
                    "formatted": f"{rev_rate}",
                    "numeric": float(rev_rate),
                },
                "avg_daily_pure": {
                    "label": "میانگین روزانه خالص",
                    "formatted": format_money_number(avg_daily_pure),
                    "numeric": float(avg_daily_pure),
                },
                "activity_rate": {
                    "label": "نرخ فعالیت",
                    "formatted": f"{activity_rate}",
                    "numeric": float(activity_rate),
                },
            },
            "consistency": consistency,
            "composition": {
                "labels": ["فروش خالص", "برگشت فروش", "برگشت توزیع"],
                "values": [
                    max(display_float(total_pure), 0.0),
                    max(display_float(sale_rev), 0.0),
                    max(display_float(dist_rev), 0.0),
                ],
            },
            "snapshot": {
                "partner_count": int(snap.partner_count or 0) if snap else 0,
                "settlement_formatted": (
                    format_money_number(snap.settlement_remainder) if snap else "—"
                ),
                "has_snapshot": bool(snap),
            },
            "rank": rank_info,
            "team": team,
            "best_day": {
                "date_label": gregorian_to_jalali(best.business_date) if best else "—",
                "formatted": format_money_number(best.total_pure_sale) if best else "—",
                "orders": int(best.final_order_count or 0) if best else 0,
            },
            "worst_day": {
                "date_label": gregorian_to_jalali(worst.business_date) if worst else "—",
                "formatted": format_money_number(worst.total_pure_sale) if worst else "—",
                "orders": int(worst.final_order_count or 0) if worst else 0,
            },
            "history": history,
            "chart_pure": chart_pure,
            "chart_orders": chart_orders,
            "chart_reversion": chart_reversion,
            "insights": insights,
            "unit": currency_label(),
            "period_options": PERIOD_OPTIONS,
        }
    )
    return ctx


def _peer_rank(code: str, *, dr, total_sale: Decimal) -> dict[str, Any]:
    qs = SalespersonDailyMetric.objects.all()
    if dr:
        qs = qs.filter(business_date__gte=dr.start, business_date__lte=dr.end)
    peers = list(
        qs.values("personnel_code", "personnel_name")
        .annotate(total=Sum("total_sale"))
        .order_by("-total")
    )
    if not peers:
        return {"rank": None, "total_peers": 0, "label": "—", "percentile": None}

    rank = None
    for i, p in enumerate(peers, 1):
        if p["personnel_code"] == code:
            rank = i
            break
    if rank is None:
        rank = len(peers) + 1
    total = len(peers)
    percentile = round((total - rank + 1) / total * 100, 1) if total else None
    return {
        "rank": rank,
        "total_peers": total,
        "label": f"{rank} از {total}",
        "percentile": percentile,
        "is_top10": rank <= max(1, total // 10) if total else False,
        "is_top3": rank <= 3,
    }


def _team_comparison(supervisor_code: str, code: str, *, dr, total_sale: Decimal) -> dict[str, Any]:
    if not supervisor_code:
        return {"available": False}
    qs = SalespersonDailyMetric.objects.filter(supervisor_code=supervisor_code)
    if dr:
        qs = qs.filter(business_date__gte=dr.start, business_date__lte=dr.end)
    teammates = list(
        qs.values("personnel_code", "personnel_name")
        .annotate(total=Sum("total_sale"), orders=Sum("final_order_count"))
        .order_by("-total")
    )
    if not teammates:
        return {"available": False}
    totals = [Decimal(str(t["total"] or 0)) for t in teammates]
    avg = sum(totals) / len(totals) if totals else Decimal("0")
    team_rank = next(
        (i for i, t in enumerate(teammates, 1) if t["personnel_code"] == code),
        None,
    )
    vs_avg = None
    if avg > 0:
        vs_avg = float(((total_sale - avg) / avg * 100).quantize(Decimal("0.1")))
    return {
        "available": True,
        "team_size": len(teammates),
        "team_rank": team_rank,
        "avg_formatted": format_money_number(avg),
        "vs_avg_percent": vs_avg,
        "teammates": [
            {
                "code": t["personnel_code"],
                "name": t["personnel_name"] or t["personnel_code"],
                "formatted": format_money_number(t["total"]),
                "orders": int(t["orders"] or 0),
                "is_self": t["personnel_code"] == code,
            }
            for t in teammates[:8]
        ],
    }


def _consistency_score(values: list[Decimal]) -> dict[str, Any]:
    """Lower coefficient of variation = steadier performance."""
    active = [v for v in values if v > 0]
    if len(active) < 3:
        return {"available": False, "label": "—", "score": None, "cv": None}
    mean = sum(active) / len(active)
    if mean <= 0:
        return {"available": False, "label": "—", "score": None, "cv": None}
    variance = sum((v - mean) ** 2 for v in active) / len(active)
    std = variance.sqrt() if hasattr(variance, "sqrt") else Decimal(str(float(variance) ** 0.5))
    cv = float((std / mean * 100).quantize(Decimal("0.1")))
    # Map CV to 0–100 score (CV 0 → 100, CV 80+ → ~0)
    score = max(0, min(100, round(100 - cv * 1.15)))
    if score >= 75:
        label = "پایدار"
        tone = "positive"
    elif score >= 50:
        label = "نسبتاً پایدار"
        tone = "info"
    else:
        label = "نوسانی"
        tone = "warning"
    return {
        "available": True,
        "score": score,
        "cv": cv,
        "label": label,
        "tone": tone,
    }


def _trend_insight(rows: list) -> dict[str, Any]:
    if len(rows) < 4:
        return {"available": False}
    half = max(2, len(rows) // 3)
    recent = rows[-half:]
    earlier = rows[-(half * 2) : -half] or rows[:half]
    recent_avg = sum(_dec(r.total_pure_sale) for r in recent) / len(recent)
    earlier_avg = sum(_dec(r.total_pure_sale) for r in earlier) / len(earlier)
    if earlier_avg <= 0:
        return {"available": False}
    change = float(((recent_avg - earlier_avg) / earlier_avg * 100).quantize(Decimal("0.1")))
    if change > 5:
        direction = "up"
        label = "روند صعودی"
    elif change < -5:
        direction = "down"
        label = "روند نزولی"
    else:
        direction = "flat"
        label = "روند نسبتاً ثابت"
    return {
        "available": True,
        "direction": direction,
        "label": label,
        "percent": abs(change),
    }


def _build_insights(**kwargs) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    rank = kwargs["rank_info"]
    if rank.get("rank"):
        tone = "positive" if rank.get("is_top3") else ("info" if rank.get("is_top10") else "warning")
        items.append(
            {
                "tone": tone,
                "icon": "bi-trophy" if rank.get("is_top3") else "bi-bar-chart",
                "title": "رتبه در شرکت",
                "body": f"رتبه {rank['label']} بین ویزیتورهای فعال بازه.",
            }
        )

    trend = kwargs["trend_insight"]
    if trend.get("available"):
        tone = {"up": "positive", "down": "warning", "flat": "info"}[trend["direction"]]
        icon = {"up": "bi-graph-up-arrow", "down": "bi-graph-down-arrow", "flat": "bi-dash-lg"}[
            trend["direction"]
        ]
        items.append(
            {
                "tone": tone,
                "icon": icon,
                "title": trend["label"],
                "body": f"میانگین روزهای اخیر نسبت به قبل حدود {trend['percent']}٪ تغییر کرده است.",
            }
        )

    rev = kwargs["rev_rate"]
    if rev >= 5:
        items.append(
            {
                "tone": "warning",
                "icon": "bi-arrow-return-left",
                "title": "نرخ برگشت بالا",
                "body": f"نرخ برگشت تجمیعی {rev}٪ است — برگشت توزیع و فروش را جدا بررسی کنید.",
            }
        )
    elif rev > 0:
        items.append(
            {
                "tone": "info",
                "icon": "bi-check2-circle",
                "title": "نرخ برگشت کنترل‌شده",
                "body": f"نرخ برگشت تجمیعی {rev}٪ است.",
            }
        )

    team = kwargs["team"]
    if team.get("available") and team.get("vs_avg_percent") is not None:
        vs = team["vs_avg_percent"]
        if vs >= 10:
            items.append(
                {
                    "tone": "positive",
                    "icon": "bi-people",
                    "title": "بالاتر از میانگین تیم",
                    "body": f"حدود {abs(vs)}٪ بالاتر از میانگین تیم سرپرست ({team['avg_formatted']}).",
                }
            )
        elif vs <= -10:
            items.append(
                {
                    "tone": "warning",
                    "icon": "bi-people",
                    "title": "پایین‌تر از میانگین تیم",
                    "body": f"حدود {abs(vs)}٪ پایین‌تر از میانگین تیم ({team['avg_formatted']}).",
                }
            )

    best = kwargs["best"]
    if best:
        items.append(
            {
                "tone": "positive",
                "icon": "bi-star",
                "title": "بهترین روز",
                "body": (
                    f"{gregorian_to_jalali(best.business_date)} با "
                    f"{format_money_number(best.total_pure_sale)} فروش خالص."
                ),
            }
        )

    active = kwargs["active_days"]
    days = kwargs["day_count"]
    if days:
        items.append(
            {
                "tone": "info",
                "icon": "bi-calendar-check",
                "title": "روزهای فعال",
                "body": f"{active} از {days} روز بازه با فروش مثبت ثبت شده است.",
            }
        )

    consistency = kwargs.get("consistency") or {}
    if consistency.get("available"):
        items.append(
            {
                "tone": consistency.get("tone", "info"),
                "icon": "bi-activity",
                "title": f"ثبات عملکرد: {consistency['label']}",
                "body": (
                    f"امتیاز ثبات {consistency['score']} از ۱۰۰ "
                    f"(ضریب نوسان روزانه حدود {consistency['cv']}٪)."
                ),
            }
        )

    return items[:6]
