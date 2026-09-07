"""Invoice change notifications after sync."""

from __future__ import annotations

import logging

from reports.models import BotInvoiceWatchState, SaleOrderSnapshot
from reports.bot.services.invoices import derive_order_status
from reports.bot.services.notifications import BotNotificationService
from reports.services.invoices import pre_order_status_label

logger = logging.getLogger(__name__)


class InvoiceNotificationTracker:
    @classmethod
    def process_orders(cls, orders: list[SaleOrderSnapshot]) -> list[dict]:
        pending: list[dict] = []
        for order in orders:
            key, label = derive_order_status(order)
            watch, created = BotInvoiceWatchState.objects.get_or_create(
                order_code=order.order_code,
                defaults={
                    "visitor_code": order.visitor_code,
                    "status_key": key,
                },
            )
            if created:
                continue
            if watch.status_key != key:
                old_label = pre_order_status_label(watch.status_key)
                pending.append(
                    {
                        "order_code": order.order_code,
                        "visitor_code": order.visitor_code,
                        "partner_name": order.partner_name,
                        "old_status": old_label,
                        "new_status": label,
                        "new_key": key,
                    }
                )
                watch.status_key = key
                watch.visitor_code = order.visitor_code
                watch.save(update_fields=["status_key", "visitor_code", "updated_at"])
            elif watch.visitor_code != order.visitor_code:
                watch.visitor_code = order.visitor_code
                watch.save(update_fields=["visitor_code", "updated_at"])
        return pending

    @classmethod
    def send_pending(cls, pending: list[dict]) -> int:
        if not pending:
            return 0
        sent = 0
        for item in pending:
            try:
                sent += BotNotificationService.notify_invoice_status(item)
            except Exception:
                logger.exception(
                    "invoice notification failed for %s", item.get("order_code")
                )
        return sent
