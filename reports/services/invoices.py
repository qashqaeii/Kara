"""Invoice and order-line queries from synced Kara sale_orders reports."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

from django.contrib.auth.models import User
from django.db.models import Count, Q, QuerySet, Sum
from django.utils import timezone

from reports.constants import PRE_ORDER_STATUS_LABELS, PRE_ORDER_STATUS_OPTIONS
from reports.models import KaraReportSnapshot, SaleOrderLineSnapshot, SaleOrderSnapshot
from reports.services.currency import format_money
from reports.services.dates import gregorian_to_jalali, parse_business_date
from reports.services.parsers.values import parse_decimal
from reports.services.retention import find_latest_full_snapshot

ORDERS_REPORT = "sale_orders"
LINE_ITEMS_REPORT = "sale_orders_with_stuffs"


def normalize_fa(text: str) -> str:
    return (text or "").replace("ي", "ی").replace("ك", "ک").strip()


def _row_text(row: dict, key: str) -> str:
    return str(row.get(key) or "").strip()


def _row_amount(row: dict, key: str) -> Decimal:
    return parse_decimal(row.get(key)) or Decimal("0")


def order_status_row(order: SaleOrderSnapshot) -> dict[str, Any]:
    """Build a Kara-like row dict for status derivation."""
    raw = dict(order.raw_data or {})
    if raw.get("OrderCode") or raw.get("OrderFinalPrice"):
        return raw
    return {
        "OrderCode": order.order_code,
        "OrderDate": order.order_date,
        "OrderFinalPrice": order.order_final_price,
        "SaleReversionAmount": order.sale_reversion_amount,
        "TotalCode": raw.get("TotalCode", ""),
        "DriverCode": raw.get("DriverCode", ""),
        "DriverName": raw.get("DriverName", ""),
        "PayeeCode": raw.get("PayeeCode", ""),
        "PayeeName": raw.get("PayeeName", ""),
        "PreOrderDate": raw.get("PreOrderDate", ""),
        "WarehouseDocumentDate": raw.get("WarehouseDocumentDate", ""),
    }


def derive_pre_order_status(row: dict) -> str:
    """Map a Kara sale_orders row to a ReportBasedOn status key."""
    reversion = _row_amount(row, "SaleReversionAmount")
    final_price = _row_amount(row, "OrderFinalPrice")
    total_code = _row_text(row, "TotalCode")
    driver = _row_text(row, "DriverCode") or _row_text(row, "DriverName")
    payee = _row_text(row, "PayeeCode") or _row_text(row, "PayeeName")
    order_date = _row_text(row, "OrderDate")
    pre_order_date = _row_text(row, "PreOrderDate")
    warehouse_date = _row_text(row, "WarehouseDocumentDate")

    if final_price > 0 and reversion >= final_price:
        return "TotalReversion"
    if driver and warehouse_date and payee:
        return "ConfirmedShipment"
    if driver:
        return "Shipment"
    if total_code and payee and not warehouse_date:
        return "WaitingForAccountingConfirm"
    if total_code:
        return "Total"
    if order_date and warehouse_date:
        return "Final"
    if order_date:
        return "Confirmed"
    if pre_order_date:
        return "Inserted"
    return "Inserted"


def pre_order_status_label(status_key: str) -> str:
    return PRE_ORDER_STATUS_LABELS.get(status_key, status_key or "—")


def derive_order_status(order: SaleOrderSnapshot) -> tuple[str, str]:
    """Return (status_key, display_label) for list/detail views."""
    key = (order.pre_order_status or "").strip()
    if not key:
        key = derive_pre_order_status(order_status_row(order))
    return key, pre_order_status_label(key)


INVOICE_STATUS_FILTER_OPTIONS = PRE_ORDER_STATUS_OPTIONS

@dataclass
class InvoiceSummary:
    order_code: str
    order_pre_code: str
    partner_name: str
    partner_code: str
    order_date: str
    amount_label: str
    status_label: str
    status_key: str
    items_count: int
    reversion_label: str | None


@dataclass
class InvoiceListFilters:
  """Query filters for the invoice list page."""

  q: str = ""
  status: str = ""
  visitor: str = ""
  date_from: str = ""
  date_to: str = ""
  min_amount: str = ""
  max_amount: str = ""

  @classmethod
  def from_request(cls, params) -> "InvoiceListFilters":
      return cls(
          q=(params.get("q") or "").strip(),
          status=(params.get("status") or "").strip(),
          visitor=(params.get("visitor") or "").strip(),
          date_from=(params.get("date_from") or "").strip(),
          date_to=(params.get("date_to") or "").strip(),
          min_amount=(params.get("min_amount") or "").strip(),
          max_amount=(params.get("max_amount") or "").strip(),
      )

  @property
  def has_advanced(self) -> bool:
      return bool(
          self.status
          or self.visitor
          or self.date_from
          or self.date_to
          or self.min_amount
          or self.max_amount
      )

  @property
  def is_active(self) -> bool:
      return bool(self.q) or self.has_advanced

  @property
  def active_count(self) -> int:
      return sum(
          1
          for value in (
              self.status,
              self.visitor,
              self.date_from,
              self.date_to,
              self.min_amount,
              self.max_amount,
          )
          if value
      )

  def to_params(self, *, page: int | None = None) -> dict[str, str]:
      params: dict[str, str] = {}
      if self.q:
          params["q"] = self.q
      if self.status:
          params["status"] = self.status
      if self.visitor:
          params["visitor"] = self.visitor
      if self.date_from:
          params["date_from"] = self.date_from
      if self.date_to:
          params["date_to"] = self.date_to
      if self.min_amount:
          params["min_amount"] = self.min_amount
      if self.max_amount:
          params["max_amount"] = self.max_amount
      if page is not None:
          params["page"] = str(page)
      return params

  def page_url(self, page: int) -> str:
      return "?" + urlencode(self.to_params(page=page))


class InvoiceService:
    """Shared invoice access for Django web, APIs, and the Bale bot."""

    PAGE_SIZE = 25
    ITEMS_PAGE_SIZE = 10

    @classmethod
    def invoice_snapshot(cls) -> KaraReportSnapshot | None:
        snap = find_latest_full_snapshot(ORDERS_REPORT)
        if snap:
            return snap
        return (
            KaraReportSnapshot.objects.filter(report_key=ORDERS_REPORT)
            .order_by("-fetched_at")
            .first()
        )

    @classmethod
    def line_items_snapshot(cls) -> KaraReportSnapshot | None:
        snap = find_latest_full_snapshot(LINE_ITEMS_REPORT)
        if snap:
            return snap
        return (
            KaraReportSnapshot.objects.filter(report_key=LINE_ITEMS_REPORT)
            .order_by("-fetched_at")
            .first()
        )

    @classmethod
    def _apply_scope(cls, qs: QuerySet, user: User | None, *, field: str = "visitor_code") -> QuerySet:
        if user is None or not user.is_authenticated:
            return qs
        from reports.bot.services.scope import apply_visitor_scope

        return apply_visitor_scope(qs, user, field=field)

    @classmethod
    def orders_qs(cls, user: User | None = None) -> QuerySet[SaleOrderSnapshot]:
        snap = cls.invoice_snapshot()
        if not snap:
            return SaleOrderSnapshot.objects.none()
        qs = SaleOrderSnapshot.objects.filter(snapshot=snap).order_by("-order_date", "-order_code")
        return cls._apply_scope(qs, user)

    @classmethod
    def lines_qs(cls, user: User | None = None) -> QuerySet[SaleOrderLineSnapshot]:
        snap = cls.line_items_snapshot()
        if not snap:
            return SaleOrderLineSnapshot.objects.none()
        qs = SaleOrderLineSnapshot.objects.filter(snapshot=snap)
        return cls._apply_scope(qs, user)

    @classmethod
    def get_order(cls, user: User | None, order_code: str) -> SaleOrderSnapshot | None:
        code = (order_code or "").strip()
        if not code:
            return None
        return cls.orders_qs(user).filter(order_code=code).first()

    @classmethod
    def apply_list_filters(
        cls, qs: QuerySet[SaleOrderSnapshot], filters: InvoiceListFilters
    ) -> QuerySet[SaleOrderSnapshot]:
        if filters.status:
            qs = qs.filter(pre_order_status=filters.status)

        if filters.visitor:
            qs = qs.filter(visitor_code=filters.visitor)

        if filters.date_from:
            qs = qs.filter(order_date__gte=filters.date_from)
        if filters.date_to:
            qs = qs.filter(order_date__lte=filters.date_to)

        min_amount = parse_decimal(filters.min_amount) if filters.min_amount else None
        if min_amount is not None:
            qs = qs.filter(order_final_price__gte=min_amount)

        max_amount = parse_decimal(filters.max_amount) if filters.max_amount else None
        if max_amount is not None:
            qs = qs.filter(order_final_price__lte=max_amount)

        if filters.q:
            q = filters.q.strip()
            if q.isdigit():
                raw = re.sub(r"\D", "", q)
                qs = qs.filter(
                    Q(order_code__icontains=raw) | Q(order_pre_code__icontains=raw)
                )
            else:
                term = normalize_fa(q)
                qs = qs.filter(
                    Q(partner_name__icontains=term) | Q(partner_name__icontains=q)
                )
        return qs

    @classmethod
    def filtered_qs(
        cls, user: User | None, filters: InvoiceListFilters
    ) -> QuerySet[SaleOrderSnapshot]:
        return cls.apply_list_filters(cls.orders_qs(user), filters)

    @classmethod
    def filter_page(
        cls,
        user: User | None,
        filters: InvoiceListFilters,
        page: int = 1,
        *,
        page_size: int | None = None,
    ) -> tuple[list[SaleOrderSnapshot], int, int]:
        qs = cls.filtered_qs(user, filters)
        total = qs.count()
        size = page_size or cls.PAGE_SIZE
        pages = max(1, (total + size - 1) // size) if total else 1
        page = max(1, min(page, pages))
        offset = (page - 1) * size
        return list(qs[offset : offset + size]), page, pages

    @classmethod
    def aggregate_qs(cls, qs: QuerySet[SaleOrderSnapshot]) -> dict[str, Any]:
        agg = qs.aggregate(total=Count("id"), amount=Sum("order_final_price"))
        return {
            "count": int(agg["total"] or 0),
            "amount": agg["amount"] or Decimal("0"),
        }

    @classmethod
    def list_visitor_options(cls, user: User | None) -> list[dict[str, str]]:
        rows = (
            cls.orders_qs(user)
            .exclude(visitor_code="")
            .values("visitor_code", "visitor_name")
            .distinct()
            .order_by("visitor_name", "visitor_code")
        )
        return [
            {
                "code": row["visitor_code"] or "",
                "name": (row["visitor_name"] or "").strip() or row["visitor_code"],
            }
            for row in rows
            if row["visitor_code"]
        ]

    @classmethod
    def list_page(
        cls, user: User | None = None, page: int = 1, *, page_size: int | None = None
    ) -> tuple[list[SaleOrderSnapshot], int, int]:
        qs = cls.orders_qs(user)
        total = qs.count()
        size = page_size or cls.PAGE_SIZE
        pages = max(1, (total + size - 1) // size)
        page = max(1, min(page, pages))
        offset = (page - 1) * size
        return list(qs[offset : offset + size]), page, pages

    @classmethod
    def aggregate(cls, user: User | None = None) -> dict[str, Any]:
        qs = cls.orders_qs(user)
        agg = qs.aggregate(total=Count("id"), amount=Sum("order_final_price"))
        return {
            "count": int(agg["total"] or 0),
            "amount": agg["amount"] or Decimal("0"),
        }

    @classmethod
    def period_aggregate(
        cls,
        user: User | None = None,
        *,
        jalali_exact: str | None = None,
        jalali_month_prefix: str | None = None,
    ) -> dict[str, Any]:
        qs = cls.orders_qs(user)
        if jalali_exact:
            qs = qs.filter(order_date=jalali_exact)
        elif jalali_month_prefix:
            qs = qs.filter(order_date__startswith=jalali_month_prefix)
        agg = qs.aggregate(total=Count("id"), amount=Sum("order_final_price"))
        return {
            "count": int(agg["total"] or 0),
            "amount": agg["amount"] or Decimal("0"),
        }

    @classmethod
    def search_by_number(cls, user: User | None, number: str) -> SaleOrderSnapshot | None:
        raw = re.sub(r"\D", "", (number or "").strip())
        if not raw:
            return None
        qs = cls.orders_qs(user)
        order = qs.filter(order_code=raw).first()
        if order:
            return order
        return qs.filter(order_code__icontains=raw).first()

    @classmethod
    def search_by_customer(
        cls, user: User | None, name: str, page: int = 1
    ) -> tuple[list[SaleOrderSnapshot], int, int]:
        term = normalize_fa(name)
        if not term:
            return [], 1, 1
        qs = cls.orders_qs(user).filter(
            Q(partner_name__icontains=term) | Q(partner_name__icontains=name.strip())
        )
        total = qs.count()
        size = cls.PAGE_SIZE
        pages = max(1, (total + size - 1) // size)
        page = max(1, min(page, pages))
        offset = (page - 1) * size
        return list(qs[offset : offset + size]), page, pages

    @classmethod
    def can_access_order(cls, user: User | None, order_code: str) -> bool:
        code = (order_code or "").strip()
        if not code:
            return False
        return cls.orders_qs(user).filter(order_code=code).exists()

    @classmethod
    def to_summary(
        cls, order: SaleOrderSnapshot, *, user: User | None = None
    ) -> InvoiceSummary:
        key, label = derive_order_status(order)
        date_label = order.order_date or "—"
        parsed = parse_business_date(order.order_date)
        if parsed:
            date_label = (
                gregorian_to_jalali(parsed)
                if "/" not in (order.order_date or "")
                else order.order_date
            )
        reversion = Decimal(str(order.sale_reversion_amount or 0))
        reversion_label = format_money(reversion) if reversion > 0 else None
        items_count = int(order.stuffs_quantity_sum or 0)
        if items_count <= 0:
            items_count = cls.line_items_for_order(order, user=user).count()
        return InvoiceSummary(
            order_code=order.order_code,
            order_pre_code=order.order_pre_code or "—",
            partner_name=order.partner_name or "—",
            partner_code=order.partner_code or "—",
            order_date=date_label,
            amount_label=format_money(order.order_final_price),
            status_label=label,
            status_key=key,
            items_count=items_count,
            reversion_label=reversion_label,
        )

    @classmethod
    def _normalized_raw_data(cls, order: SaleOrderSnapshot) -> dict[str, Any]:
        """Build a display dict from normalized columns (no full-snapshot scan)."""
        return {
            "OrderCode": order.order_code,
            "OrderPreCode": order.order_pre_code,
            "OrderDate": order.order_date,
            "PartnerCode": order.partner_code,
            "PartnerName": order.partner_name,
            "VisitorCode": order.visitor_code,
            "VisitorName": order.visitor_name,
            "OrderFinalPrice": order.order_final_price,
            "SaleReversionAmount": order.sale_reversion_amount,
            "StuffsQuantitySum": order.stuffs_quantity_sum,
            "FinalizedCostForCustomer": order.finalized_cost,
        }

    @classmethod
    def _effective_raw_data(cls, order: SaleOrderSnapshot) -> dict:
        raw = dict(order.raw_data or {})
        if raw.get("OrderCode") or raw.get("StuffsPriceSum") or raw.get("OrderFinalPrice"):
            return raw
        return cls._normalized_raw_data(order)

    @classmethod
    def _money_label(cls, value) -> str | None:
        if value is None or value == "":
            return None
        amount = parse_decimal(value)
        if amount is None:
            text = str(value).strip()
            return text if text and text not in ("0", "0.0") else None
        if amount == 0:
            return None
        return format_money(amount)

    @classmethod
    def financial_breakdown(
        cls, order: SaleOrderSnapshot, *, raw: dict | None = None
    ) -> list[dict[str, str]]:
        raw = raw if raw is not None else cls._effective_raw_data(order)
        rows = [
            ("📦 تعداد اقلام", raw.get("StuffsQuantitySum") or order.stuffs_quantity_sum),
            ("🔢 تعداد ردیف", raw.get("QuantitySum")),
            ("💵 جمع اقلام", cls._money_label(raw.get("StuffsPriceSum"))),
            ("🏷 تخفیف اقلام", cls._money_label(raw.get("StuffsDiscountSum"))),
            ("🎁 تخفیف فاکتور", cls._money_label(raw.get("OrderDiscountAmount"))),
            ("💵 تخفیف نقدی", cls._money_label(raw.get("OrderCashDiscountAmount"))),
            ("📊 مالیات", cls._money_label(raw.get("OrderTotalVAT"))),
            (
                "↩️ برگشت از فروش",
                cls._money_label(raw.get("SaleReversionAmount") or order.sale_reversion_amount),
            ),
        ]
        result: list[dict[str, str]] = []
        for label, value in rows:
            if value is None or value == "" or value == 0:
                continue
            if isinstance(value, Decimal):
                display = format_money(value)
            else:
                display = str(value)
            result.append({"label": label, "value": display})
        return result

    @classmethod
    def extra_fields(
        cls, order: SaleOrderSnapshot, *, raw: dict | None = None
    ) -> dict[str, Any]:
        raw = raw if raw is not None else cls._effective_raw_data(order)
        return {
            "stuffs_price": raw.get("StuffsPriceSum") or raw.get("stuffs_price"),
            "discount": raw.get("OrderDiscountAmount") or raw.get("StuffsDiscountSum"),
            "pre_order_date": raw.get("PreOrderDate") or "",
            "partner_address": raw.get("PartnerAddress") or "",
            "partner_groups": raw.get("PartnerGroups") or "",
        }

    @classmethod
    def line_items_for_order(
        cls, order: SaleOrderSnapshot | str, *, user: User | None = None
    ) -> QuerySet[SaleOrderLineSnapshot]:
        code = order.order_code if isinstance(order, SaleOrderSnapshot) else str(order or "").strip()
        if not code:
            return SaleOrderLineSnapshot.objects.none()
        return (
            cls.lines_qs(user)
            .filter(order_code=code)
            .order_by("stuff_group_name", "stuff_name", "stuff_code")
        )

    @classmethod
    def line_item_dict(cls, line: SaleOrderLineSnapshot, *, index: int) -> dict[str, Any]:
        qty = line.stuff_quantity or line.package_quantity
        unit_parts = [p for p in (line.package_name, line.unit_name) if p]
        raw = line.raw_data or {}
        return {
            "index": index,
            "stuff_code": line.stuff_code,
            "name": line.stuff_name or "—",
            "quantity": qty or "—",
            "unit": " / ".join(unit_parts) if unit_parts else "",
            "unit_fee": format_money(line.unit_fee) if line.unit_fee else cls._money_label(raw.get("Fee")),
            "amount": format_money(line.line_amount) if line.line_amount else "—",
            "group": line.stuff_group_name or "",
            "sub_group": line.stuff_sub_group_name or "",
            "buy_price": cls._money_label(raw.get("StuffBuyPrice")),
            "discount": cls._money_label(raw.get("DiscountsSum")),
            "vat": cls._money_label(raw.get("VATAmount")),
        }

    @classmethod
    def _line_items_from_raw(
        cls, order: SaleOrderSnapshot, *, raw: dict | None = None
    ) -> list[dict[str, Any]]:
        raw = raw if raw is not None else cls._effective_raw_data(order)
        items = raw.get("items") or raw.get("Stuffs") or []
        if not isinstance(items, list):
            return []
        result: list[dict[str, Any]] = []
        for idx, item in enumerate(items, 1):
            if not isinstance(item, dict):
                continue
            name = item.get("StuffName") or item.get("name") or "—"
            qty = item.get("Quantity") or item.get("SaleStuffQuantity") or "—"
            amount = item.get("SaleSum") or item.get("amount")
            unit = item.get("UnitName") or item.get("StuffUnitName") or ""
            result.append(
                {
                    "index": idx,
                    "stuff_code": str(item.get("StuffCode") or ""),
                    "name": str(name).strip() or "—",
                    "quantity": qty,
                    "unit": str(unit).strip(),
                    "unit_fee": cls._money_label(item.get("Fee")),
                    "amount": format_money(amount) if amount else "—",
                    "group": str(item.get("StuffGroupName") or ""),
                    "sub_group": str(item.get("StuffSubGroupName") or ""),
                    "buy_price": cls._money_label(item.get("StuffBuyPrice")),
                    "discount": cls._money_label(item.get("DiscountsSum")),
                    "vat": cls._money_label(item.get("VATAmount")),
                }
            )
        return result

    @classmethod
    def line_items_as_dicts(
        cls, order: SaleOrderSnapshot, *, user: User | None = None
    ) -> list[dict[str, Any]]:
        lines = list(cls.line_items_for_order(order, user=user))
        if lines:
            return [cls.line_item_dict(line, index=i) for i, line in enumerate(lines, 1)]
        return cls._line_items_from_raw(order)

    @classmethod
    def line_items_page(
        cls,
        order: SaleOrderSnapshot,
        page: int = 1,
        *,
        user: User | None = None,
        raw: dict | None = None,
    ) -> tuple[list[dict[str, Any]], int, int, int]:
        qs = cls.line_items_for_order(order, user=user)
        total = qs.count()
        size = cls.ITEMS_PAGE_SIZE
        if total:
            pages = max(1, (total + size - 1) // size)
            page = max(1, min(page, pages))
            offset = (page - 1) * size
            lines = list(qs[offset : offset + size])
            items = [
                cls.line_item_dict(line, index=offset + i + 1)
                for i, line in enumerate(lines)
            ]
            return items, page, pages, total

        items = cls._line_items_from_raw(order, raw=raw)
        total = len(items)
        pages = max(1, (total + size - 1) // size) if total else 1
        page = max(1, min(page, pages))
        if not items:
            return [], page, pages, 0
        offset = (page - 1) * size
        return items[offset : offset + size], page, pages, total

    @classmethod
    def has_line_items(
        cls,
        order: SaleOrderSnapshot,
        *,
        user: User | None = None,
        raw: dict | None = None,
    ) -> bool:
        if cls.line_items_for_order(order, user=user).exists():
            return True
        raw = raw if raw is not None else cls._effective_raw_data(order)
        items = raw.get("items") or raw.get("Stuffs") or []
        return isinstance(items, list) and bool(items)

    @classmethod
    def serialize_order_list(
        cls, order: SaleOrderSnapshot, *, user: User | None = None
    ) -> dict[str, Any]:
        summary = cls.to_summary(order, user=user)
        return {
            "order_code": summary.order_code,
            "order_pre_code": summary.order_pre_code,
            "partner_name": summary.partner_name,
            "partner_code": summary.partner_code,
            "visitor_name": order.visitor_name,
            "order_date": summary.order_date,
            "amount_label": summary.amount_label,
            "status_label": summary.status_label,
            "status_key": summary.status_key,
            "items_count": summary.items_count,
        }

    @classmethod
    def serialize_order(
        cls,
        order: SaleOrderSnapshot,
        *,
        user: User | None = None,
        include_lines: bool = False,
        lines_page: int = 1,
        raw: dict | None = None,
    ) -> dict[str, Any]:
        raw = raw if raw is not None else cls._effective_raw_data(order)
        summary = cls.to_summary(order, user=user)
        line_snap = cls.line_items_snapshot()
        payload: dict[str, Any] = {
            "order_code": summary.order_code,
            "order_pre_code": summary.order_pre_code,
            "partner_name": summary.partner_name,
            "partner_code": summary.partner_code,
            "visitor_code": order.visitor_code,
            "visitor_name": order.visitor_name,
            "order_date": summary.order_date,
            "amount": str(order.order_final_price),
            "amount_label": summary.amount_label,
            "finalized_cost": str(order.finalized_cost),
            "status_key": summary.status_key,
            "status_label": summary.status_label,
            "items_count": summary.items_count,
            "reversion_label": summary.reversion_label,
            "financial_breakdown": cls.financial_breakdown(order, raw=raw),
            "extra": cls.extra_fields(order, raw=raw),
            "has_line_items": cls.has_line_items(order, user=user, raw=raw),
            "line_items_synced": line_snap is not None,
        }
        if include_lines:
            lines, page, pages, total = cls.line_items_page(
                order, lines_page, user=user, raw=raw
            )
            payload["line_items"] = lines
            payload["line_items_page"] = page
            payload["line_items_pages"] = pages
            payload["line_items_total"] = total
            if not payload["has_line_items"] and total:
                payload["has_line_items"] = True
        return payload

    @classmethod
    def sync_status(cls) -> dict[str, Any]:
        inv_snap = cls.invoice_snapshot()
        line_snap = cls.line_items_snapshot()
        return {
            "orders_report": ORDERS_REPORT,
            "line_items_report": LINE_ITEMS_REPORT,
            "orders_snapshot_at": inv_snap.fetched_at.isoformat() if inv_snap else None,
            "line_items_snapshot_at": line_snap.fetched_at.isoformat() if line_snap else None,
            "orders_count": (
                SaleOrderSnapshot.objects.filter(snapshot=inv_snap).count() if inv_snap else 0
            ),
            "line_items_count": (
                SaleOrderLineSnapshot.objects.filter(snapshot=line_snap).count()
                if line_snap
                else 0
            ),
        }

    @classmethod
    def _jalali_today(cls) -> str:
        return gregorian_to_jalali(timezone.localdate())

    @classmethod
    def _jalali_month_prefix(cls) -> str:
        today = timezone.localdate()
        try:
            import jdatetime

            jtoday = jdatetime.date.fromgregorian(date=today)
            return f"{jtoday.year}/{jtoday.month:02d}/"
        except ImportError:
            parsed = parse_business_date(cls._jalali_today())
            if parsed:
                jl = gregorian_to_jalali(parsed)
                parts = jl.split("/")
                if len(parts) >= 2:
                    return f"{parts[0]}/{parts[1]}/"
            return ""
