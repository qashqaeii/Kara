"""Managerial insights derived only from available local analytics data."""

from __future__ import annotations

from typing import Any

from reports.services.currency import currency_label
from reports.services.dates import DateRange
from reports.services.period_comparison import PeriodComparisonService


class InsightsService:
    """Short, actionable conclusions for dashboard / TV — no invented KPIs."""

    @classmethod
    def for_dashboard(cls, *, preset: str = "all") -> list[dict[str, Any]]:
        from reports.services.analytics import AnalyticsService
        from reports.services.analytics_query import AnalyticsQueryService

        items: list[dict[str, Any]] = []
        kpis = AnalyticsService.company_kpis(preset)
        unit = currency_label()

        cmp = PeriodComparisonService.compare_field("total_pure_sale", preset)
        if cmp.is_comparable and cmp.percent_change is not None:
            pct = abs(cmp.percent_change)
            if cmp.direction == "up":
                items.append(
                    {
                        "tone": "positive",
                        "icon": "bi-graph-up-arrow",
                        "title": "رشد فروش خالص",
                        "body": f"فروش خالص نسبت به دوره قبل حدود {pct}٪ افزایش داشته است.",
                    }
                )
            elif cmp.direction == "down":
                items.append(
                    {
                        "tone": "warning",
                        "icon": "bi-graph-down-arrow",
                        "title": "افت فروش خالص",
                        "body": (
                            f"فروش خالص نسبت به دوره قبل حدود {pct}٪ کاهش یافته — "
                            "بررسی ویزیتور و سبد کالا توصیه می‌شود."
                        ),
                    }
                )

        rev_rate = (kpis.get("reversion_rate") or {}).get("numeric")
        if rev_rate is not None and rev_rate >= 3:
            items.append(
                {
                    "tone": "warning",
                    "icon": "bi-arrow-return-left",
                    "title": "نرخ برگشت بالا",
                    "body": (
                        f"نرخ برگشت {kpis['reversion_rate']['formatted']}٪ است. "
                        "برگشت فروش و توزیع را جداگانه بررسی کنید."
                    ),
                }
            )
        elif rev_rate is not None and rev_rate > 0:
            items.append(
                {
                    "tone": "info",
                    "icon": "bi-check2-circle",
                    "title": "نرخ برگشت کنترل‌شده",
                    "body": f"نرخ برگشت دوره {kpis['reversion_rate']['formatted']}٪ است.",
                }
            )

        dr, _ = PeriodComparisonService.comparison_range(preset)
        date_range = DateRange(dr.start, dr.end) if dr else None
        if PeriodComparisonService.uses_latest_snapshot(preset):
            top_products = AnalyticsService.products_from_snapshot(limit=1, full_period=True)
            top_rev = AnalyticsService.products_from_snapshot(
                limit=1, rank_by="sale_reversion_amount", full_period=True
            )
        else:
            top_products = AnalyticsQueryService.product_ranking(
                dr=date_range, limit=1, preset=preset
            )
            top_rev = AnalyticsQueryService.product_ranking(
                dr=date_range, limit=1, rank_by="sale_reversion_amount", preset=preset
            )
        if top_products:
            p = top_products[0]
            items.append(
                {
                    "tone": "info",
                    "icon": "bi-box-seam",
                    "title": "پیشتاز سبد کالا",
                    "body": (
                        f"«{p['name']}» با فروش خالص {p['pure_sale_formatted']} {unit} "
                        f"در صدر پرفروش‌هاست ({p.get('group') or '—'})."
                    ),
                }
            )

        if top_rev and (top_rev[0].get("sale_reversion_amount") or 0) > 0:
            r = top_rev[0]
            items.append(
                {
                    "tone": "warning",
                    "icon": "bi-exclamation-triangle",
                    "title": "بیشترین برگشت کالا",
                    "body": (
                        f"«{r['name']}» با {r['sale_reversion_formatted']} {unit} "
                        "بیشترین مبلغ برگشت را دارد."
                    ),
                }
            )

        top_profits = AnalyticsService.product_profit_ranking(limit=1)
        if top_profits and (top_profits[0].get("benefit_amount") or 0) != 0:
            p = top_profits[0]
            items.append(
                {
                    "tone": "positive" if (p.get("benefit_amount") or 0) > 0 else "danger",
                    "icon": "bi-piggy-bank",
                    "title": "پرسودترین کالا",
                    "body": (
                        f"«{p['name']}» با سود {p['benefit_formatted']} {unit} "
                        f"(حاشیه {p.get('margin_formatted', '—')}٪) در صدر است."
                    ),
                }
            )

        visitors = AnalyticsService.visitor_ranking(limit=1, preset=preset)
        if visitors:
            v = visitors[0]
            items.append(
                {
                    "tone": "positive",
                    "icon": "bi-person-badge",
                    "title": "ویزیتور برتر",
                    "body": (
                        f"{v['name']} با فروش {v['total_sale_formatted']} {unit} "
                        f"و {v.get('order_count', 0)} سفارش در رتبه یک است."
                    ),
                }
            )

        geo = AnalyticsService.geo_summary(limit=1, preset=preset)
        if geo.get("available") and geo.get("cities"):
            c = geo["cities"][0]
            items.append(
                {
                    "tone": "info",
                    "icon": "bi-geo-alt",
                    "title": "شهر پیشتاز",
                    "body": (
                        f"{c['name']} با {c['formatted']} {unit} "
                        "بالاترین فروش جغرافیایی را دارد."
                    ),
                }
            )

        pnl = AnalyticsQueryService.company_pnl_kpis()
        if pnl.get("pnl_operating_profit"):
            op = pnl["pnl_operating_profit"]
            margin = pnl.get("pnl_operating_margin_rate") or {}
            body = f"سود عملیاتی حسابداری: {op['formatted']} {unit}."
            if margin.get("formatted") is not None:
                body += f" حاشیه عملیاتی {margin['formatted']}٪."
            items.append(
                {
                    "tone": "positive" if (op.get("numeric") or 0) >= 0 else "danger",
                    "icon": "bi-cash-stack",
                    "title": "سودآوری شرکت",
                    "body": body,
                }
            )

        recv = AnalyticsQueryService.receivables_summary()
        if recv.get("available") and (recv.get("total_outstanding") or 0) > 0:
            items.append(
                {
                    "tone": "warning",
                    "icon": "bi-wallet2",
                    "title": "مطالبات معوق",
                    "body": (
                        f"جمع معوقات {recv['total_outstanding_formatted']} {unit} "
                        f"برای {recv.get('partner_count', 0)} مشتری ثبت شده است."
                    ),
                }
            )

        return items[:8]
