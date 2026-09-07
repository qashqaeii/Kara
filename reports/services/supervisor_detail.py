"""Rich context builder for supervisor (head visitor) detail page."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.contrib.auth.models import AnonymousUser, User
from django.db.models import Count, Sum

from reports.models import SalespersonDailyMetric, SupervisorDailyMetric
from reports.services.analytics import AnalyticsService
from reports.services.currency import currency_label, display_float, format_money_number
from reports.services.dates import gregorian_to_jalali
from reports.services.period_comparison import PeriodComparisonService
from reports.services.ranking_pages import PERIOD_OPTIONS, enrich_ranking_rows, period_context


def _dec(v) -> Decimal:
    if v is None:
        return Decimal("0")
    return Decimal(str(v))


def _parse_orders(value: Any) -> int:
    if value is None or value == "":
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).replace(",", "").replace("٬", "").strip()
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return 0


def build_supervisor_detail(
    personnel_code: str,
    *,
    preset: str = "all",
    user: User | AnonymousUser | None = None,
) -> dict[str, Any]:
    code = (personnel_code or "").strip()
    dr, _ = PeriodComparisonService.comparison_range(preset)
    use_snapshot = PeriodComparisonService.uses_latest_snapshot(preset)

    # Resolve identity from daily metrics / company ranking.
    latest_sup = (
        SupervisorDailyMetric.objects.filter(supervisor_code=code)
        .order_by("-business_date")
        .first()
    )
    company_rank = _company_rank(code, preset=preset, user=user)
    name = (
        company_rank.get("name")
        or (latest_sup.supervisor_name if latest_sup else "")
        or code
    )

    # Daily supervisor history (for charts / history table).
    hist_qs = SupervisorDailyMetric.objects.filter(supervisor_code=code).order_by(
        "business_date"
    )
    if dr and not use_snapshot:
        hist_qs = hist_qs.filter(business_date__gte=dr.start, business_date__lte=dr.end)
    history_rows = list(hist_qs)
    period_note = ""
    if not history_rows and not use_snapshot:
        history_rows = list(
            SupervisorDailyMetric.objects.filter(supervisor_code=code).order_by(
                "business_date"
            )
        )
        if history_rows:
            period_note = "در بازه انتخابی داده روزانه نبود — کل تاریخچه نمایش داده می‌شود."

    # Team roster for selected period.
    team_members, team_source = _team_members(
        code, name=name, preset=preset, dr=dr, user=user
    )
    team_members = enrich_ranking_rows(team_members)
    team_total_for_share = sum(
        (_dec(m.get("total_sale") or 0) for m in team_members), Decimal("0")
    ) or Decimal("1")
    for m in team_members:
        share = (_dec(m.get("total_sale") or 0) / team_total_for_share * 100).quantize(
            Decimal("0.1")
        )
        m["team_share"] = float(share)

    total_sale = sum((_dec(m.get("total_sale") or m.get("amount") or 0) for m in team_members), Decimal("0"))
    if total_sale <= 0 and company_rank.get("total_sale"):
        total_sale = _dec(company_rank["total_sale"])
    total_pure = sum(
        (_dec(m.get("pure_sale_raw") or 0) for m in team_members),
        Decimal("0"),
    )
    if total_pure <= 0 and company_rank.get("pure_sale_formatted"):
        # Ranking stores formatted Toman — convert back for storage math, then display.
        total_pure = _money_from_formatted(company_rank.get("pure_sale_formatted"))
    elif total_pure <= 0:
        total_pure = total_sale

    orders = sum(_parse_orders(m.get("order_count")) for m in team_members)
    if orders <= 0:
        orders = _parse_orders(company_rank.get("order_count"))

    sale_rev = sum((_dec(m.get("sale_reversion_raw") or 0) for m in team_members), Decimal("0"))
    dist_rev = sum(
        (_dec(m.get("distribution_reversion_raw") or 0) for m in team_members),
        Decimal("0"),
    )
    if sale_rev <= 0:
        sale_rev = _money_from_formatted(company_rank.get("sale_reversion"))
    if dist_rev <= 0:
        dist_rev = _money_from_formatted(company_rank.get("distribution_reversion"))

    rev_base = abs(total_sale) + abs(sale_rev) + abs(dist_rev)
    rev_rate = (
        ((abs(sale_rev) + abs(dist_rev)) / rev_base * 100).quantize(Decimal("0.1"))
        if rev_base > 0
        else Decimal("0")
    )

    team_size = len(team_members)
    active_count = sum(1 for m in team_members if _dec(m.get("total_sale") or 0) > 0)
    avg_per_person = (total_sale / team_size) if team_size else Decimal("0")
    concentration = _concentration(team_members)
    coverage = (
        (Decimal(active_count) / Decimal(team_size) * 100).quantize(Decimal("0.1"))
        if team_size
        else Decimal("0")
    )

    # History table + charts from supervisor daily rows when available;
    # otherwise synthesize a single snapshot bar from team totals.
    history, chart_sale, chart_orders, chart_team_size = _history_and_charts(
        history_rows, total_sale=total_sale, orders=orders, team_size=team_size
    )

    best_member = team_members[0] if team_members else None
    weak_member = None
    active_sorted = [m for m in team_members if _dec(m.get("total_sale") or 0) > 0]
    if len(active_sorted) >= 2:
        weak_member = active_sorted[-1]

    share_chart = [
        {
            "name": (m.get("name") or "")[:22],
            "value": display_float(m.get("total_sale") or 0),
            "formatted": m.get("total_sale_formatted") or format_money_number(m.get("total_sale")),
        }
        for m in team_members[:8]
        if _dec(m.get("total_sale") or 0) > 0
    ]
    if team_size > 8:
        rest = sum((_dec(m.get("total_sale") or 0) for m in team_members[8:]), Decimal("0"))
        if rest > 0:
            share_chart.append(
                {
                    "name": "سایر اعضای تیم",
                    "value": display_float(rest),
                    "formatted": format_money_number(rest),
                }
            )

    orders_chart = sorted(
        [
            {
                "name": (m.get("name") or "")[:22],
                "value": _parse_orders(m.get("order_count")),
                "formatted": f"{_parse_orders(m.get('order_count')):,}",
            }
            for m in team_members
            if _parse_orders(m.get("order_count")) > 0
        ],
        key=lambda row: row["value"],
        reverse=True,
    )[:8]

    insights = _build_insights(
        name=name,
        team_size=team_size,
        active_count=active_count,
        total_sale=total_sale,
        rev_rate=rev_rate,
        company_rank=company_rank,
        concentration=concentration,
        best_member=best_member,
        weak_member=weak_member,
        coverage=coverage,
    )

    initials = "".join(part[0] for part in name.split()[:2] if part) or "س"
    date_from = gregorian_to_jalali(history_rows[0].business_date) if history_rows else "—"
    date_to = gregorian_to_jalali(history_rows[-1].business_date) if history_rows else "—"

    ctx = period_context(preset)
    ctx.update(
        {
            "supervisor_code": code,
            "name": name,
            "initials": initials,
            "period_note": period_note,
            "has_data": bool(
                team_members
                or history_rows
                or company_rank.get("rank")
                or _dec(company_rank.get("total_sale") or 0) > 0
            ),
            "team_source": team_source,
            "date_from_label": date_from,
            "date_to_label": date_to,
            "day_count": len(history_rows),
            "kpis": {
                "total_sale": {
                    "label": "فروش تیم",
                    "formatted": format_money_number(total_sale),
                    "numeric": display_float(total_sale),
                },
                "total_pure_sale": {
                    "label": "فروش خالص تیم",
                    "formatted": format_money_number(total_pure)
                    if total_pure
                    else (company_rank.get("pure_sale_formatted") or format_money_number(total_sale)),
                    "numeric": display_float(total_pure or total_sale),
                },
                "orders": {
                    "label": "سفارش نهایی",
                    "formatted": f"{orders:,}",
                    "numeric": orders,
                },
                "team_size": {
                    "label": "اندازه تیم",
                    "formatted": f"{team_size}",
                    "numeric": team_size,
                },
                "active_count": {
                    "label": "ویزیتور فعال",
                    "formatted": f"{active_count}",
                    "numeric": active_count,
                },
                "avg_per_person": {
                    "label": "میانگین فروش نفر",
                    "formatted": format_money_number(avg_per_person),
                    "numeric": display_float(avg_per_person),
                },
                "reversion_rate": {
                    "label": "نرخ برگشت",
                    "formatted": f"{rev_rate}",
                    "numeric": float(rev_rate),
                },
                "coverage": {
                    "label": "پوشش فعال",
                    "formatted": f"{coverage}",
                    "numeric": float(coverage),
                },
            },
            "rank": company_rank,
            "concentration": concentration,
            "team_members": team_members,
            "best_member": best_member,
            "weak_member": weak_member,
            "history": history,
            "chart_sale": chart_sale,
            "chart_orders_trend": chart_orders,
            "chart_team_size": chart_team_size,
            "share_chart": share_chart,
            "orders_chart": orders_chart,
            "insights": insights,
            "unit": currency_label(),
            "period_options": PERIOD_OPTIONS,
        }
    )
    return ctx


def _company_rank(
    code: str, *, preset: str, user: User | AnonymousUser | None = None
) -> dict[str, Any]:
    ranked = AnalyticsService.head_visitor_ranking(limit=100, preset=preset, user=user)
    for i, row in enumerate(ranked, 1):
        if str(row.get("code") or "") == code:
            total = len(ranked) or 1
            return {
                "rank": i,
                "label": f"{i} از {total}",
                "is_top3": i <= 3,
                "is_top10": i <= 10,
                "percentile": int(round((1 - (i - 1) / total) * 100)),
                "name": row.get("name") or "",
                "total_sale": row.get("total_sale"),
                "total_sale_formatted": row.get("total_sale_formatted"),
                "pure_sale_formatted": row.get("pure_sale_formatted"),
                "order_count": row.get("order_count"),
                "distribution_reversion": row.get("distribution_reversion"),
                "sale_reversion": row.get("sale_reversion"),
            }
    # Fallback identity from DB
    latest = (
        SupervisorDailyMetric.objects.filter(supervisor_code=code)
        .order_by("-business_date")
        .first()
    )
    return {
        "rank": None,
        "label": "—",
        "is_top3": False,
        "is_top10": False,
        "percentile": None,
        "name": (latest.supervisor_name if latest else "") or "",
        "total_sale": float(latest.total_sale) if latest else 0,
        "total_sale_formatted": format_money_number(latest.total_sale) if latest else "—",
        "pure_sale_formatted": format_money_number(latest.total_pure_sale) if latest else "—",
        "order_count": int(latest.final_order_count or 0) if latest else 0,
    }


def _team_members(
    code: str,
    *,
    name: str,
    preset: str,
    dr,
    user: User | AnonymousUser | None = None,
) -> tuple[list[dict], str]:
    """Return team roster with ranking-compatible fields."""
    if PeriodComparisonService.uses_latest_snapshot(preset):
        visitors = AnalyticsService.visitor_ranking(limit=200, preset=preset, user=user)
        matched = []
        for v in visitors:
            head = (v.get("head_visitor") or "").strip()
            if head and name and head == name:
                item = dict(v)
                item["sale_reversion_raw"] = _money_from_formatted(v.get("sale_reversion"))
                item["distribution_reversion_raw"] = _money_from_formatted(
                    v.get("distribution_reversion")
                )
                matched.append(item)
        if matched:
            return matched, "snapshot"

    # Period / fallback: aggregate salesperson daily metrics.
    qs = SalespersonDailyMetric.objects.filter(supervisor_code=code)
    if dr and not PeriodComparisonService.uses_latest_snapshot(preset):
        qs = qs.filter(business_date__gte=dr.start, business_date__lte=dr.end)
    rows = list(
        qs.values("personnel_code", "personnel_name")
        .annotate(
            total_sale=Sum("total_sale"),
            total_pure_sale=Sum("total_pure_sale"),
            final_order_count=Sum("final_order_count"),
            sale_reversion=Sum("sale_reversion"),
            distribution_reversion=Sum("distribution_reversion"),
            days=Count("business_date"),
        )
        .order_by("-total_sale")
    )
    if not rows:
        # Try name match on supervisor_name field
        qs2 = SalespersonDailyMetric.objects.filter(supervisor_name=name)
        if dr and not PeriodComparisonService.uses_latest_snapshot(preset):
            qs2 = qs2.filter(business_date__gte=dr.start, business_date__lte=dr.end)
        rows = list(
            qs2.values("personnel_code", "personnel_name")
            .annotate(
                total_sale=Sum("total_sale"),
                total_pure_sale=Sum("total_pure_sale"),
                final_order_count=Sum("final_order_count"),
                sale_reversion=Sum("sale_reversion"),
                distribution_reversion=Sum("distribution_reversion"),
                days=Count("business_date"),
            )
            .order_by("-total_sale")
        )

    result = []
    for i, r in enumerate(rows, 1):
        total = _dec(r["total_sale"])
        sale_rev = _dec(r["sale_reversion"])
        dist_rev = _dec(r["distribution_reversion"])
        rev = (
            ((sale_rev + dist_rev) / total * 100).quantize(Decimal("0.1"))
            if total > 0
            else Decimal("0")
        )
        result.append(
            {
                "rank": i,
                "code": r["personnel_code"],
                "name": r["personnel_name"] or r["personnel_code"],
                "head_visitor": name,
                "total_sale": float(total),
                "total_sale_formatted": format_money_number(total),
                "pure_sale_raw": float(r["total_pure_sale"] or 0),
                "pure_sale_formatted": format_money_number(r["total_pure_sale"]),
                "order_count": int(r["final_order_count"] or 0),
                "reversion_rate": float(rev),
                "sale_reversion_raw": float(sale_rev),
                "distribution_reversion_raw": float(dist_rev),
                "sale_reversion": format_money_number(sale_rev),
                "distribution_reversion": format_money_number(dist_rev),
                "active_days": int(r["days"] or 0),
            }
        )
    return result, "daily"


def _money_from_formatted(value: Any) -> Decimal:
    """Best-effort parse of already-formatted money back to storage Rial.

    Ranking tables store formatted Toman strings; multiply by 10 when unit is Toman.
    """
    if value is None or value == "" or value == "—":
        return Decimal("0")
    if isinstance(value, (int, float, Decimal)):
        return _dec(value)
    text = str(value).replace(",", "").replace("٬", "").strip()
    try:
        num = Decimal(text)
    except Exception:
        return Decimal("0")
    # Formatted display is Toman → convert back to Rial for aggregation consistency.
    from reports.constants import CurrencyUnit
    from reports.services.currency import get_currency_unit

    if get_currency_unit() == CurrencyUnit.TOMAN:
        return num * 10
    return num


def _concentration(members: list[dict]) -> dict[str, Any]:
    amounts = [_dec(m.get("total_sale") or 0) for m in members]
    total = sum(amounts) or Decimal("1")
    top1 = amounts[0] if amounts else Decimal("0")
    top3 = sum(amounts[:3]) if amounts else Decimal("0")
    return {
        "top1_share": float((top1 / total * 100).quantize(Decimal("0.1"))),
        "top3_share": float((top3 / total * 100).quantize(Decimal("0.1"))),
        "top1_name": (members[0].get("name") if members else "—") or "—",
        "member_count": len(members),
    }


def _history_and_charts(
    history_rows: list[SupervisorDailyMetric],
    *,
    total_sale: Decimal,
    orders: int,
    team_size: int,
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    history: list[dict] = []
    chart_sale: list[dict] = []
    chart_orders: list[dict] = []
    chart_team_size: list[dict] = []

    if history_rows:
        max_sale = max((_dec(r.total_sale) for r in history_rows), default=Decimal("1")) or Decimal(
            "1"
        )
        for r in history_rows:
            sale = _dec(r.total_sale)
            chart_sale.append(
                {
                    "date": r.business_date.isoformat(),
                    "date_label": gregorian_to_jalali(r.business_date),
                    "value": display_float(sale),
                }
            )
            chart_orders.append(
                {
                    "date": r.business_date.isoformat(),
                    "date_label": gregorian_to_jalali(r.business_date),
                    "value": int(r.final_order_count or 0),
                }
            )
            chart_team_size.append(
                {
                    "date": r.business_date.isoformat(),
                    "date_label": gregorian_to_jalali(r.business_date),
                    "value": int(r.active_salesperson_count or r.salesperson_count or 0),
                }
            )
        for r in reversed(history_rows):
            sale = _dec(r.total_sale)
            history.append(
                {
                    "date_label": gregorian_to_jalali(r.business_date),
                    "total_sale_formatted": format_money_number(sale),
                    "total_pure_formatted": format_money_number(r.total_pure_sale),
                    "order_count": int(r.final_order_count or 0),
                    "team_size": int(r.salesperson_count or 0),
                    "active_count": int(r.active_salesperson_count or 0),
                    "avg_per_person_formatted": format_money_number(r.average_sale_per_person),
                    "reversion_rate": float(r.reversion_rate or 0),
                    "share_of_best": float((sale / max_sale * 100).quantize(Decimal("0.1"))),
                }
            )
    elif total_sale > 0:
        # Snapshot-only: one synthetic point so charts aren't empty.
        chart_sale = [{"date": "", "date_label": "کل بازه", "value": display_float(total_sale)}]
        chart_orders = [{"date": "", "date_label": "کل بازه", "value": orders}]
        chart_team_size = [{"date": "", "date_label": "کل بازه", "value": team_size}]

    return history, chart_sale, chart_orders, chart_team_size


def _build_insights(
    *,
    name: str,
    team_size: int,
    active_count: int,
    total_sale: Decimal,
    rev_rate: Decimal,
    company_rank: dict,
    concentration: dict,
    best_member: dict | None,
    weak_member: dict | None,
    coverage: Decimal,
) -> list[dict]:
    items: list[dict] = []
    if company_rank.get("rank"):
        tone = "good" if company_rank["is_top3"] else "info"
        items.append(
            {
                "tone": tone,
                "icon": "bi-trophy",
                "title": "جایگاه سرپرست",
                "body": (
                    f"«{name}» رتبه {company_rank['label']} سرپرستان است"
                    + (
                        f" · صدک {company_rank['percentile']}"
                        if company_rank.get("percentile")
                        else ""
                    )
                    + "."
                ),
            }
        )
    if team_size:
        items.append(
            {
                "tone": "info",
                "icon": "bi-people",
                "title": "ترکیب تیم",
                "body": (
                    f"{active_count} ویزیتور فعال از {team_size} نفر "
                    f"(پوشش {coverage}٪) · فروش تیم {format_money_number(total_sale)} {currency_label()}."
                ),
            }
        )
    if concentration.get("top3_share", 0) >= 70:
        items.append(
            {
                "tone": "warning",
                "icon": "bi-pie-chart",
                "title": "تمرکز فروش",
                "body": (
                    f"۳ نفر برتر {concentration['top3_share']}٪ فروش تیم را دارند "
                    f"(پیشتاز: {concentration['top1_name']}). ریسک وابستگی به افراد کلیدی بالاست."
                ),
            }
        )
    elif best_member:
        items.append(
            {
                "tone": "good",
                "icon": "bi-star",
                "title": "پیشتاز تیم",
                "body": (
                    f"«{best_member.get('name')}» با {best_member.get('total_sale_formatted')} "
                    f"و سهم {best_member.get('share_of_leader', concentration.get('top1_share'))}٪ "
                    "نسبت به رتبه یک تیم در صدر است."
                ),
            }
        )
    if rev_rate >= 5:
        items.append(
            {
                "tone": "warning",
                "icon": "bi-arrow-return-left",
                "title": "نرخ برگشت تیم",
                "body": f"نرخ برگشت تیم {rev_rate}٪ است — برگشت فروش و توزیع را جداگانه بررسی کنید.",
            }
        )
    if weak_member and best_member and weak_member.get("code") != best_member.get("code"):
        items.append(
            {
                "tone": "info",
                "icon": "bi-lightning",
                "title": "فرصت مربی‌گری",
                "body": (
                    f"«{weak_member.get('name')}» با {weak_member.get('total_sale_formatted')} "
                    "کمترین فروش فعال تیم را دارد — کوچینگ روی این نفر اثر اهرمی دارد."
                ),
            }
        )
    return items
