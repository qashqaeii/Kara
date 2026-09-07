"""Rich context for the personal / my-performance panel."""

from __future__ import annotations

from typing import Any

from django.contrib.auth.models import AnonymousUser, User

from reports.constants import DEFAULT_PERIOD_PRESET, KaraRole
from reports.services.access_control import AccessControlService, AccessScope
from reports.services.analytics import AnalyticsService
from reports.services.currency import currency_label
from reports.services.ranking_pages import (
    chart_payload,
    enrich_ranking_rows,
    orders_chart_payload,
    period_context,
    ranking_summary,
    team_share_payload,
)


def _kpi(kpis: dict, key: str) -> dict[str, Any]:
    row = kpis.get(key) or {}
    return {
        "label": row.get("label") or key,
        "formatted": row.get("formatted") or "—",
        "raw": row.get("value"),
        "delta": row.get("delta"),
        "delta_label": row.get("delta_label") or "",
    }


def _observer_context(
    scope: AccessScope, *, preset: str, user: User | AnonymousUser
) -> dict[str, Any]:
    """Company-wide cockpit for viewers / executives / unrestricted roles."""
    kpis = AnalyticsService.company_kpis(preset)
    visitors = enrich_ranking_rows(
        AnalyticsService.visitor_ranking(limit=15, preset=preset, user=user)
    )
    supervisors = enrich_ranking_rows(
        AnalyticsService.head_visitor_ranking(limit=8, preset=preset, user=user)
    )
    geo = AnalyticsService.geo_summary(limit=5, preset=preset)
    cities = list(geo.get("cities") or [])
    if cities:
        top_city = float(cities[0].get("amount") or cities[0].get("value") or 1) or 1.0
        for city in cities:
            amount = float(city.get("amount") or city.get("value") or 0)
            city["bar_percent"] = round(min(100.0, amount / top_city * 100), 1)
    geo = {**geo, "cities": cities}
    products = AnalyticsService.products_from_snapshot(limit=5, full_period=True) or []
    if not products:
        from reports.services.period_comparison import PeriodComparisonService
        from reports.services.dates import DateRange
        from reports.services.analytics_query import AnalyticsQueryService

        dr, _ = PeriodComparisonService.comparison_range(preset)
        if dr:
            products = AnalyticsQueryService.product_ranking(
                dr=DateRange(dr.start, dr.end), limit=5, preset=preset
            ) or []

    alerts = [
        {
            "severity": a.severity,
            "title": a.title,
            "description": a.description,
            "current_value": a.current_value,
        }
        for a in AnalyticsService.open_alerts(limit=5)
    ]

    from reports.services.insights import InsightsService

    insights = InsightsService.for_dashboard(preset=preset)[:4]

    pulse = {
        "total_pure_sale": _kpi(kpis, "total_pure_sale"),
        "total_sale": _kpi(kpis, "total_sale"),
        "final_order_count": _kpi(kpis, "final_order_count"),
        "avg_order_value": _kpi(kpis, "avg_order_value"),
        "active_visitors": _kpi(kpis, "active_visitors"),
        "reversion_rate": _kpi(kpis, "reversion_rate"),
    }

    visitor_summary = ranking_summary(visitors, label_singular="ویزیتور")
    supervisor_summary = ranking_summary(supervisors, label_singular="سرپرست")

    return {
        "mode": "observer",
        "mode_label": "نمای مشاهده مدیریتی",
        "mode_hint": "دسترسی مشاهده‌گر · داده‌های کل سازمان از دیتابیس محلی",
        "scope": scope,
        "pulse": pulse,
        "has_company_data": bool(kpis),
        "visitors": visitors,
        "visitor_summary": visitor_summary,
        "visitor_podium": visitors[:3],
        "visitor_chart": chart_payload(visitors, limit=8),
        "orders_chart": orders_chart_payload(visitors, limit=8),
        "team_chart": team_share_payload(visitors, limit=6),
        "supervisors": supervisors,
        "supervisor_summary": supervisor_summary,
        "geo": geo,
        "products": products[:5],
        "alerts": alerts,
        "insights": insights,
        "connection": AnalyticsService.connection_status(),
        "quick_links": [
            {"url_name": "reports:dashboard", "label": "نمای کلی", "icon": "bi-speedometer2"},
            {"url_name": "reports:analytics_salespersons", "label": "ویزیتورها", "icon": "bi-people"},
            {"url_name": "reports:analytics_supervisors", "label": "سرپرستان", "icon": "bi-person-badge"},
            {"url_name": "reports:tv_mode", "label": "تلویزیون", "icon": "bi-tv", "blank": True},
        ],
    }


def _personal_context(
    scope: AccessScope, *, preset: str, user: User | AnonymousUser
) -> dict[str, Any]:
    from reports.services.salesperson_detail import build_salesperson_detail

    detail = build_salesperson_detail(scope.personnel_code, preset=preset)
    peers = enrich_ranking_rows(
        AnalyticsService.visitor_ranking(limit=12, preset=preset, user=user)
    )
    my_row = next(
        (r for r in peers if str(r.get("code") or "") == scope.personnel_code),
        None,
    )
    return {
        "mode": "personal",
        "mode_label": "پرونده عملکرد من",
        "mode_hint": "نمایش بر اساس کد پرسنلی متصل به حساب شما",
        "scope": scope,
        "detail": detail,
        "my_row": my_row,
        "peers": peers,
        "connection": AnalyticsService.connection_status(),
        "has_company_data": bool(detail.get("has_data")),
        "quick_links": [
            {
                "url_name": "reports:analytics_salesperson_detail",
                "label": "پرونده کامل",
                "icon": "bi-file-person",
                "args": [scope.personnel_code],
            },
            {"url_name": "reports:analytics_salespersons", "label": "رتبه‌بندی ویزیتورها", "icon": "bi-people"},
            {"url_name": "reports:dashboard", "label": "نمای کلی", "icon": "bi-speedometer2"},
        ],
    }


def _team_context(
    scope: AccessScope, *, preset: str, user: User | AnonymousUser
) -> dict[str, Any]:
    from reports.services.supervisor_detail import build_supervisor_detail

    code = scope.supervisor_code or scope.personnel_code
    detail = build_supervisor_detail(code, preset=preset, user=user)
    return {
        "mode": "team",
        "mode_label": "عملکرد تیم من",
        "mode_hint": "نمایش بر اساس نقش سرپرست فروش",
        "scope": scope,
        "detail": detail,
        "connection": AnalyticsService.connection_status(),
        "has_company_data": bool(detail.get("has_data")),
        "quick_links": [
            {
                "url_name": "reports:analytics_supervisor_detail",
                "label": "پرونده تیم",
                "icon": "bi-diagram-3",
                "args": [code],
            },
            {"url_name": "reports:analytics_supervisors", "label": "رتبه‌بندی سرپرستان", "icon": "bi-person-badge"},
            {"url_name": "reports:dashboard", "label": "نمای کلی", "icon": "bi-speedometer2"},
        ],
    }


def build_my_performance(
    user: User | AnonymousUser,
    *,
    preset: str | None = None,
) -> dict[str, Any]:
    """Build template/API context for /reports/my-performance/."""
    preset = preset or DEFAULT_PERIOD_PRESET
    scope = AccessControlService.resolve_scope(user)
    ctx = period_context(preset)
    ctx["currency_unit"] = currency_label()
    ctx["user_display"] = (
        (user.get_full_name() or user.get_username())
        if getattr(user, "is_authenticated", False)
        else "مهمان"
    )

    if scope.role == KaraRole.SALESPERSON and scope.personnel_code:
        payload = _personal_context(scope, preset=preset, user=user)
    elif scope.role == KaraRole.SALES_SUPERVISOR and (
        scope.supervisor_code or scope.personnel_code
    ):
        payload = _team_context(scope, preset=preset, user=user)
    else:
        payload = _observer_context(scope, preset=preset, user=user)

    ctx.update(payload)
    return ctx
