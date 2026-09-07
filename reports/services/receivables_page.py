"""Rich context builder for receivables analytics page."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db.models import Count, Max, Sum

from reports.constants import AGING_BUCKET_KEYS
from reports.models import (
    AccountBalanceSnapshot,
    ReceivableAgingSnapshot,
    ReceivableDailyMetric,
)
from reports.services.currency import currency_label, display_float, format_money_number
from reports.services.dates import gregorian_to_jalali
from reports.services.display import aging_bucket_label

# Risk bands for monthly unsettled buckets (higher M = older).
FRESH_KEYS = ("M1", "M2", "M3")
WATCH_KEYS = ("M4", "M5", "M6")
CRITICAL_KEYS = ("M7", "M8", "M9", "M10", "M11", "M12")

BUCKET_RISK = {
    **{k: "fresh" for k in FRESH_KEYS},
    **{k: "watch" for k in WATCH_KEYS},
    **{k: "critical" for k in CRITICAL_KEYS},
}

BUCKET_HINT = {
    "M1": "تازه‌ترین مانده",
    "M2": "۱ ماه قبل",
    "M3": "۲ ماه قبل",
    "M4": "۳ ماه قبل",
    "M5": "۴ ماه قبل",
    "M6": "۵ ماه قبل",
    "M7": "۶ ماه قبل",
    "M8": "۷ ماه قبل",
    "M9": "۸ ماه قبل",
    "M10": "۹ ماه قبل",
    "M11": "۱۰ ماه قبل",
    "M12": "۱۱+ ماه قبل",
}


def _dec(v) -> Decimal:
    if v is None:
        return Decimal("0")
    return Decimal(str(v))


def _pct(part: Decimal, whole: Decimal) -> float:
    if whole <= 0:
        return 0.0
    return float((part / whole * 100).quantize(Decimal("0.1")))


def _best_aging_snapshot_id() -> int | None:
    """Prefer full aging grids over empty/partial sync pages."""
    row = (
        ReceivableAgingSnapshot.objects.values("snapshot_id")
        .annotate(
            tot=Sum("total_outstanding"),
            c=Count("id"),
            last=Max("last_seen_at"),
        )
        .filter(tot__gt=0)
        .order_by("-tot", "-c", "-last")
        .first()
    )
    if row:
        return row["snapshot_id"]
    row = (
        ReceivableAgingSnapshot.objects.values("snapshot_id")
        .annotate(c=Count("id"), last=Max("last_seen_at"))
        .order_by("-c", "-last")
        .first()
    )
    return row["snapshot_id"] if row else None


def _best_balance_snapshot_id() -> int | None:
    row = (
        AccountBalanceSnapshot.objects.values("snapshot_id")
        .annotate(c=Count("id"), last=Max("last_seen_at"))
        .order_by("-c", "-last")
        .first()
    )
    return row["snapshot_id"] if row else None


def _best_receivable_metric() -> ReceivableDailyMetric | None:
    return (
        ReceivableDailyMetric.objects.filter(total_outstanding__gt=0)
        .order_by("-business_date", "-calculated_at")
        .first()
        or ReceivableDailyMetric.objects.filter(partner_balance_total__gt=0)
        .order_by("-business_date", "-calculated_at")
        .first()
        or ReceivableDailyMetric.objects.order_by("-business_date").first()
    )


def build_receivables_page() -> dict[str, Any]:
    metric = _best_receivable_metric()
    has_any = (
        ReceivableAgingSnapshot.objects.exists()
        or AccountBalanceSnapshot.objects.exists()
        or bool(metric)
    )
    if not has_any:
        return {"available": False, "unit": currency_label()}

    aging_sid = _best_aging_snapshot_id()
    aging_rows = list(
        ReceivableAgingSnapshot.objects.filter(snapshot_id=aging_sid)
        if aging_sid
        else []
    )
    aging_sum = sum((_dec(r.total_outstanding) for r in aging_rows), Decimal("0"))
    # Ignore zero-only partial grids when a richer metric exists
    if aging_rows and aging_sum <= 0 and metric and _dec(metric.total_outstanding) > 0:
        aging_rows = []
        aging_sum = Decimal("0")

    balance_sid = _best_balance_snapshot_id()
    balance_qs = (
        AccountBalanceSnapshot.objects.filter(snapshot_id=balance_sid)
        if balance_sid
        else AccountBalanceSnapshot.objects.none()
    )

    if aging_rows and aging_sum > 0:
        total_out = aging_sum
        row_count = len(aging_rows)
    else:
        total_out = _dec(metric.total_outstanding) if metric else Decimal("0")
        row_count = int(metric.row_count or 0) if metric else 0

    partner_balance = _dec(metric.partner_balance_total) if metric else Decimal("0")
    partner_count = int(metric.partner_count or 0) if metric else 0
    if balance_qs.exists():
        partner_count = balance_qs.count()
        partner_balance = balance_qs.aggregate(s=Sum("total_balance"))["s"] or Decimal("0")

    buckets = _build_buckets(metric, aging_rows, total_out)
    bands = _build_bands(buckets, total_out)
    visitors = _rank_group(aging_rows, "visitor_code", "visitor_name", total_out, limit=12)
    cities = _rank_group(aging_rows, "city_name", "city_name", total_out, limit=10)
    zones = _rank_group(aging_rows, "zone_name", "zone_name", total_out, limit=10)
    detail_rows = _detail_rows(aging_rows, total_out)
    balances = _balance_insights(balance_qs)
    history = _metric_history()
    concentration = _concentration(detail_rows, total_out)
    insights = _insights(
        total_out=total_out,
        bands=bands,
        visitors=visitors,
        cities=cities,
        concentration=concentration,
        balances=balances,
        row_count=row_count,
    )

    avg_per_row = (total_out / row_count) if row_count else Decimal("0")
    critical_share = bands["critical"]["share"]
    date_label = gregorian_to_jalali(metric.business_date) if metric else "—"

    return {
        "available": bool(
            total_out > 0 or partner_balance or aging_rows or balance_qs.exists()
        ),
        "unit": currency_label(),
        "business_date_label": date_label,
        "as_of": date_label,
        "kpis": {
            "total_outstanding": {
                "formatted": format_money_number(total_out),
                "numeric": float(total_out),
            },
            "partner_balance": {
                "formatted": format_money_number(partner_balance),
                "numeric": float(partner_balance),
            },
            "partner_count": partner_count,
            "row_count": row_count,
            "visitor_count": len({r.visitor_code for r in aging_rows if r.visitor_code}),
            "city_count": len({r.city_name for r in aging_rows if r.city_name}),
            "avg_per_row": {"formatted": format_money_number(avg_per_row)},
            "critical_share": critical_share,
            "fresh_share": bands["fresh"]["share"],
        },
        "bands": bands,
        "buckets": buckets,
        "chart_buckets": [
            {
                "key": b["key"],
                "label": b["short_label"],
                "value": display_float(b["amount_raw"]),
                "formatted": b["formatted"],
                "risk": b["risk"],
            }
            for b in buckets
            if b["amount_raw"] > 0
        ],
        "chart_bands": [
            {
                "label": bands["fresh"]["label"],
                "value": display_float(bands["fresh"]["amount_raw"]),
                "color": "#0f766e",
            },
            {
                "label": bands["watch"]["label"],
                "value": display_float(bands["watch"]["amount_raw"]),
                "color": "#b45309",
            },
            {
                "label": bands["critical"]["label"],
                "value": display_float(bands["critical"]["amount_raw"]),
                "color": "#b91c1c",
            },
        ],
        "visitors": visitors,
        "cities": cities,
        "zones": zones,
        "detail_rows": detail_rows,
        "balances": balances,
        "history": history,
        "concentration": concentration,
        "insights": insights,
        "total_outstanding_formatted": format_money_number(total_out),
        "partner_balance_formatted": format_money_number(partner_balance),
        "partner_count": partner_count,
        "row_count": row_count,
    }


def _build_buckets(metric, aging_rows, total_out: Decimal) -> list[dict[str, Any]]:
    totals: dict[str, Decimal] = {k: Decimal("0") for k in AGING_BUCKET_KEYS}
    if aging_rows:
        for row in aging_rows:
            for key in AGING_BUCKET_KEYS:
                totals[key] += _dec((row.bucket_amounts or {}).get(key))
    elif metric and metric.bucket_totals:
        for key in AGING_BUCKET_KEYS:
            totals[key] = _dec((metric.bucket_totals or {}).get(key))

    max_amt = max(totals.values()) if totals else Decimal("1")
    if max_amt <= 0:
        max_amt = Decimal("1")

    out = []
    for key in AGING_BUCKET_KEYS:
        amt = totals[key]
        risk = BUCKET_RISK.get(key, "watch")
        out.append(
            {
                "key": key,
                "label": aging_bucket_label(key),
                "short_label": key.replace("M", "م"),
                "hint": BUCKET_HINT.get(key, ""),
                "amount_raw": amt,
                "amount": float(amt),
                "formatted": format_money_number(amt),
                "share": _pct(amt, total_out),
                "bar": float((amt / max_amt * 100).quantize(Decimal("0.1"))),
                "risk": risk,
            }
        )
    return out


def _build_bands(buckets: list[dict], total_out: Decimal) -> dict[str, Any]:
    groups = {
        "fresh": {"label": "جاری تا ۳ ماه", "keys": FRESH_KEYS, "tone": "positive"},
        "watch": {"label": "۴ تا ۶ ماه", "keys": WATCH_KEYS, "tone": "warning"},
        "critical": {"label": "۷ ماه و بیشتر", "keys": CRITICAL_KEYS, "tone": "danger"},
    }
    by_key = {b["key"]: b["amount_raw"] for b in buckets}
    result = {}
    for name, meta in groups.items():
        amt = sum((by_key.get(k, Decimal("0")) for k in meta["keys"]), Decimal("0"))
        result[name] = {
            "label": meta["label"],
            "tone": meta["tone"],
            "amount_raw": amt,
            "formatted": format_money_number(amt),
            "share": _pct(amt, total_out),
        }
    return result


def _rank_group(
    rows: list,
    code_attr: str,
    name_attr: str,
    total_out: Decimal,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    agg: dict[str, dict[str, Any]] = {}
    for r in rows:
        code = (getattr(r, code_attr) or "").strip() or "—"
        name = (getattr(r, name_attr) or "").strip() or code
        if code not in agg:
            agg[code] = {
                "code": code,
                "name": name,
                "total": Decimal("0"),
                "fresh": Decimal("0"),
                "watch": Decimal("0"),
                "critical": Decimal("0"),
                "rows": 0,
            }
        item = agg[code]
        item["total"] += _dec(r.total_outstanding)
        item["rows"] += 1
        for key in AGING_BUCKET_KEYS:
            amt = _dec((r.bucket_amounts or {}).get(key))
            risk = BUCKET_RISK.get(key, "watch")
            item[risk] += amt
        if name and name != code:
            item["name"] = name

    ranked = sorted(agg.values(), key=lambda x: x["total"], reverse=True)
    max_total = ranked[0]["total"] if ranked else Decimal("1")
    if max_total <= 0:
        max_total = Decimal("1")

    out = []
    for i, item in enumerate(ranked[:limit], 1):
        out.append(
            {
                "rank": i,
                "code": item["code"],
                "name": item["name"],
                "formatted": format_money_number(item["total"]),
                "share": _pct(item["total"], total_out),
                "bar": float((item["total"] / max_total * 100).quantize(Decimal("0.1"))),
                "rows": item["rows"],
                "fresh_share": _pct(item["fresh"], item["total"]) if item["total"] else 0,
                "watch_share": _pct(item["watch"], item["total"]) if item["total"] else 0,
                "critical_share": _pct(item["critical"], item["total"]) if item["total"] else 0,
                "critical_formatted": format_money_number(item["critical"]),
            }
        )
    return out


def _detail_rows(rows: list, total_out: Decimal) -> list[dict[str, Any]]:
    sorted_rows = sorted(rows, key=lambda r: _dec(r.total_outstanding), reverse=True)
    max_amt = _dec(sorted_rows[0].total_outstanding) if sorted_rows else Decimal("1")
    if max_amt <= 0:
        max_amt = Decimal("1")
    out = []
    for r in sorted_rows:
        total = _dec(r.total_outstanding)
        critical = sum(
            (_dec((r.bucket_amounts or {}).get(k)) for k in CRITICAL_KEYS),
            Decimal("0"),
        )
        watch = sum(
            (_dec((r.bucket_amounts or {}).get(k)) for k in WATCH_KEYS),
            Decimal("0"),
        )
        # Dominant bucket
        buckets = r.bucket_amounts or {}
        dominant_key = max(
            AGING_BUCKET_KEYS,
            key=lambda k: _dec(buckets.get(k)),
            default="M1",
        )
        risk = "critical" if critical > 0 else ("watch" if watch > 0 else "fresh")
        out.append(
            {
                "visitor_code": r.visitor_code,
                "visitor_name": r.visitor_name or r.visitor_code or "—",
                "partner_name": r.partner_name or "—",
                "city_name": r.city_name or "—",
                "zone_name": r.zone_name or "—",
                "route_name": r.route_name or "—",
                "formatted": format_money_number(total),
                "share": _pct(total, total_out),
                "bar": float((total / max_amt * 100).quantize(Decimal("0.1"))),
                "critical_formatted": format_money_number(critical),
                "critical_share": _pct(critical, total) if total else 0,
                "dominant_label": aging_bucket_label(dominant_key),
                "risk": risk,
                "filter_hay": " ".join(
                    [
                        r.visitor_name or "",
                        r.visitor_code or "",
                        r.partner_name or "",
                        r.city_name or "",
                        r.zone_name or "",
                        r.route_name or "",
                    ]
                ).lower(),
            }
        )
    return out


def _balance_insights(qs) -> dict[str, Any]:
    if not qs.exists():
        return {"available": False}
    rows = list(qs)
    debtors = sorted(
        [r for r in rows if _dec(r.total_balance) > 0],
        key=lambda r: _dec(r.total_balance),
        reverse=True,
    )
    creditors = sorted(
        [r for r in rows if _dec(r.total_balance) < 0],
        key=lambda r: _dec(r.total_balance),
    )
    positive = sum((_dec(r.total_balance) for r in debtors), Decimal("0"))
    negative = sum((_dec(r.total_balance) for r in creditors), Decimal("0"))
    zero_count = sum(1 for r in rows if _dec(r.total_balance) == 0)

    def _map(items, limit=8):
        return [
            {
                "code": r.partner_code,
                "name": r.partner_name or r.partner_legal_name or r.partner_code,
                "formatted": format_money_number(r.total_balance),
                "abs_formatted": format_money_number(abs(_dec(r.total_balance))),
            }
            for r in items[:limit]
        ]

    return {
        "available": True,
        "count": len(rows),
        "debtor_count": len(debtors),
        "creditor_count": len(creditors),
        "zero_count": zero_count,
        "positive_formatted": format_money_number(positive),
        "negative_formatted": format_money_number(negative),
        "top_debtors": _map(debtors),
        "top_creditors": _map(creditors),
    }


def _metric_history() -> list[dict[str, Any]]:
    metrics = list(
        ReceivableDailyMetric.objects.filter(total_outstanding__gt=0)
        .order_by("business_date")[:30]
    )
    return [
        {
            "date": m.business_date.isoformat(),
            "date_label": gregorian_to_jalali(m.business_date),
            "outstanding": display_float(m.total_outstanding),
            "outstanding_formatted": format_money_number(m.total_outstanding),
            "balance": display_float(m.partner_balance_total),
            "balance_formatted": format_money_number(m.partner_balance_total),
        }
        for m in metrics
    ]


def _concentration(detail_rows: list, total_out: Decimal) -> dict[str, Any]:
    if not detail_rows or total_out <= 0:
        return {"available": False}
    top3_share = sum(r["share"] for r in detail_rows[:3])
    top5_share = sum(r["share"] for r in detail_rows[:5])
    return {
        "available": True,
        "top1_share": round(detail_rows[0]["share"], 1) if detail_rows else 0,
        "top3_share": round(top3_share, 1),
        "top5_share": round(top5_share, 1),
        "top_name": detail_rows[0]["visitor_name"] if detail_rows else "—",
        "top_zone": (
            f"{detail_rows[0]['city_name']} · {detail_rows[0]['zone_name']}"
            if detail_rows
            else "—"
        ),
    }


def _insights(**kwargs) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    bands = kwargs["bands"]
    concentration = kwargs["concentration"]
    visitors = kwargs["visitors"]
    cities = kwargs["cities"]
    balances = kwargs["balances"]
    total_out = kwargs["total_out"]
    row_count = kwargs["row_count"]

    crit = bands["critical"]
    if crit["share"] >= 15:
        items.append(
            {
                "tone": "danger",
                "icon": "bi-exclamation-octagon",
                "title": "ریسک معوق بالا",
                "body": (
                    f"{crit['share']}٪ از معوقات ({crit['formatted']}) در باکت ۷ ماه و بیشتر است."
                ),
            }
        )
    elif bands["watch"]["share"] >= 40:
        items.append(
            {
                "tone": "warning",
                "icon": "bi-hourglass-split",
                "title": "تمرکز در باکت میانی",
                "body": (
                    f"{bands['watch']['share']}٪ از مطالبات در بازه ۴ تا ۶ ماه قرار دارد — "
                    "پیگیری وصول را جدی کنید."
                ),
            }
        )
    else:
        items.append(
            {
                "tone": "positive",
                "icon": "bi-shield-check",
                "title": "ساختار سنی نسبتاً سالم",
                "body": (
                    f"{bands['fresh']['share']}٪ از معوقات در سه ماه اول است "
                    f"و سهم بحرانی {crit['share']}٪."
                ),
            }
        )

    if concentration.get("available") and concentration["top1_share"] >= 25:
        items.append(
            {
                "tone": "warning",
                "icon": "bi-bullseye",
                "title": "تمرکز ریسک",
                "body": (
                    f"«{concentration['top_name']}» حدود {concentration['top1_share']}٪ "
                    f"از کل معوقات را دارد ({concentration['top_zone']})."
                ),
            }
        )
    elif concentration.get("available"):
        items.append(
            {
                "tone": "info",
                "icon": "bi-pie-chart",
                "title": "تمرکز ۳ ردیف برتر",
                "body": f"سه ردیف اول جمعاً {concentration['top3_share']}٪ از کل معوقات را تشکیل می‌دهند.",
            }
        )

    if visitors:
        top = visitors[0]
        items.append(
            {
                "tone": "info",
                "icon": "bi-person-badge",
                "title": "بیشترین معوق نزد ویزیتور",
                "body": (
                    f"{top['name']} با {top['formatted']} "
                    f"({top['share']}٪ از کل · بحرانی {top['critical_share']}٪)."
                ),
            }
        )

    if cities:
        items.append(
            {
                "tone": "info",
                "icon": "bi-geo-alt",
                "title": "شهر پرریسک",
                "body": f"{cities[0]['name']} با {cities[0]['formatted']} معوق ({cities[0]['share']}٪).",
            }
        )

    if balances.get("available") and balances["debtor_count"]:
        items.append(
            {
                "tone": "info",
                "icon": "bi-wallet2",
                "title": "مانده حساب مشتریان",
                "body": (
                    f"{balances['debtor_count']} مشتری با مانده مثبت "
                    f"(جمع {balances['positive_formatted']}) · "
                    f"{balances['zero_count']} بدون مانده."
                ),
            }
        )

    if total_out > 0 and row_count:
        items.append(
            {
                "tone": "info",
                "icon": "bi-table",
                "title": "پوشش ردیف‌ها",
                "body": f"{row_count} ردیف جدول سنی با جمع {format_money_number(total_out)} ثبت شده است.",
            }
        )

    return items[:6]
