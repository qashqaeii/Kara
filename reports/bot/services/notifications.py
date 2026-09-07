"""User notification inbox, badges, and push delivery."""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from reports.models import BaleUserIdentity, BotNotificationEvent, BotUserNotification
from reports.constants import KaraRole, PRE_ORDER_STATUS_LABELS

logger = logging.getLogger(__name__)

STATUS_LABELS = dict(PRE_ORDER_STATUS_LABELS)

SYNC_REPORT_LABELS = {
    "sale_orders": "فاکتورها",
    "sale_orders_with_stuffs": "اقلام فاکتور",
    "receivables_aging": "مطالبات و تسویه",
    "visitor_sale": "گزارش فروش",
    "account_balance": "مانده حساب مشتریان",
}

CATEGORY_ICONS = {
    BotUserNotification.CATEGORY_INVOICE: "🧾",
    BotUserNotification.CATEGORY_SYNC: "🔄",
    BotUserNotification.CATEGORY_SETTLEMENT: "💳",
    BotUserNotification.CATEGORY_SYSTEM: "ℹ️",
}


def format_badge(label: str, count: int) -> str:
    """Format menu label with unread count, e.g. اعلان(3) or اعلان(+99)."""
    if count <= 0:
        return label
    if count > 99:
        return f"{label}(+99)"
    return f"{label}({count})"


class BotNotificationService:
    PAGE_SIZE = 8

    @classmethod
    def _base_qs(cls, bale_user_id: int):
        return BotUserNotification.objects.filter(bale_user_id=bale_user_id)

    @classmethod
    def unread_count(cls, bale_user_id: int, *, category: str | None = None) -> int:
        qs = cls._base_qs(bale_user_id).filter(is_read=False)
        if category:
            qs = qs.filter(category=category)
        return qs.count()

    @classmethod
    def menu_badges(cls, bale_user_id: int) -> dict[str, int]:
        return {
            "notifications": cls.unread_count(bale_user_id),
            "invoices": cls.unread_count(
                bale_user_id, category=BotUserNotification.CATEGORY_INVOICE
            ),
            "settlement": cls.unread_count(
                bale_user_id, category=BotUserNotification.CATEGORY_SETTLEMENT
            ),
            "sync": cls.unread_count(
                bale_user_id, category=BotUserNotification.CATEGORY_SYNC
            ),
        }

    @classmethod
    def create(
        cls,
        *,
        bale_user_id: int,
        user: User | None,
        category: str,
        event_type: str,
        title: str,
        body: str,
        entity_type: str = "",
        entity_code: str = "",
        metadata: dict | None = None,
        push: bool = True,
        push_markup=None,
    ) -> BotUserNotification:
        notif = BotUserNotification.objects.create(
            bale_user_id=bale_user_id,
            user=user,
            category=category,
            event_type=event_type,
            title=title,
            body=body,
            entity_type=entity_type,
            entity_code=entity_code,
            metadata=metadata or {},
        )
        if push:
            if cls._push_message(bale_user_id, body, push_markup):
                notif.pushed_at = timezone.now()
                notif.save(update_fields=["pushed_at"])
        return notif

    @classmethod
    def list_page(
        cls,
        bale_user_id: int,
        page: int = 1,
        *,
        category: str | None = None,
    ) -> tuple[list[BotUserNotification], int, int, int]:
        qs = cls._base_qs(bale_user_id)
        if category:
            qs = qs.filter(category=category)
        total = qs.count()
        unread = qs.filter(is_read=False).count()
        pages = max(1, (total + cls.PAGE_SIZE - 1) // cls.PAGE_SIZE)
        page = max(1, min(page, pages))
        offset = (page - 1) * cls.PAGE_SIZE
        items = list(qs[offset : offset + cls.PAGE_SIZE])
        return items, page, pages, unread

    @classmethod
    def get(cls, bale_user_id: int, notif_id: int) -> BotUserNotification | None:
        return cls._base_qs(bale_user_id).filter(pk=notif_id).first()

    @classmethod
    def mark_read(cls, bale_user_id: int, notif_id: int) -> bool:
        updated = (
            cls._base_qs(bale_user_id)
            .filter(pk=notif_id, is_read=False)
            .update(is_read=True)
        )
        return updated > 0

    @classmethod
    def mark_all_read(cls, bale_user_id: int, *, category: str | None = None) -> int:
        qs = cls._base_qs(bale_user_id).filter(is_read=False)
        if category:
            qs = qs.filter(category=category)
        return qs.update(is_read=True)

    @classmethod
    def overview(cls, bale_user_id: int) -> dict:
        qs = cls._base_qs(bale_user_id)
        total = qs.count()
        unread = qs.filter(is_read=False).count()
        by_category: dict[str, int] = {}
        for row in (
            qs.filter(is_read=False)
            .values("category")
            .order_by("category")
        ):
            cat = row["category"]
            by_category[cat] = by_category.get(cat, 0) + 1
        return {
            "total": total,
            "unread": unread,
            "by_category": by_category,
            "has_data": total > 0,
        }

    @classmethod
    def notify_invoice_status(cls, item: dict) -> int:
        """Create inbox + push for invoice status change; returns users notified."""
        event_key = item["new_key"]
        if BotNotificationEvent.objects.filter(
            event_type="INVOICE_STATUS",
            entity_type="invoice",
            entity_code=item["order_code"],
            new_value=event_key,
        ).exists():
            return 0

        identities = BaleUserIdentity.objects.filter(
            user__kara_identity__personnel_code=item["visitor_code"],
            is_blocked=False,
        ).select_related("user")

        supervisor_identities = BaleUserIdentity.objects.filter(
            is_blocked=False,
            user__kara_identity__role=KaraRole.SALES_SUPERVISOR,
        ).select_related("user", "user__kara_identity")

        from reports.bot.services.scope import can_access_visitor

        supervisor_targets = [
            ident
            for ident in supervisor_identities
            if can_access_visitor(ident.user, item["visitor_code"])
        ]

        if not identities.exists() and not supervisor_targets:
            return 0

        title = f"تغییر وضعیت فاکتور #{item['order_code']}"
        body = cls._invoice_status_body(item)
        from reports.bot.keyboards.common import notification_invoice_button

        kb = notification_invoice_button(item["order_code"])
        notified = 0
        seen_bale_ids: set[int] = set()

        for ident in identities:
            if ident.bale_user_id in seen_bale_ids:
                continue
            seen_bale_ids.add(ident.bale_user_id)
            cls.create(
                bale_user_id=ident.bale_user_id,
                user=ident.user,
                category=BotUserNotification.CATEGORY_INVOICE,
                event_type="INVOICE_STATUS",
                title=title,
                body=body,
                entity_type="invoice",
                entity_code=item["order_code"],
                metadata={
                    "order_code": item["order_code"],
                    "partner_name": item.get("partner_name") or "",
                    "old_status": item.get("old_status") or "",
                    "new_status": item.get("new_status") or "",
                    "new_key": event_key,
                    "visitor_code": item.get("visitor_code") or "",
                },
                push=True,
                push_markup=kb,
            )
            notified += 1

        if supervisor_targets:
            supervisor_body = cls._invoice_status_body_for_supervisor(item)
            supervisor_title = f"فاکتور تیم #{item['order_code']}"
            for ident in supervisor_targets:
                if ident.bale_user_id in seen_bale_ids:
                    continue
                seen_bale_ids.add(ident.bale_user_id)
                cls.create(
                    bale_user_id=ident.bale_user_id,
                    user=ident.user,
                    category=BotUserNotification.CATEGORY_INVOICE,
                    event_type="INVOICE_STATUS_TEAM",
                    title=supervisor_title,
                    body=supervisor_body,
                    entity_type="invoice",
                    entity_code=item["order_code"],
                    metadata={
                        "order_code": item["order_code"],
                        "partner_name": item.get("partner_name") or "",
                        "old_status": item.get("old_status") or "",
                        "new_status": item.get("new_status") or "",
                        "new_key": event_key,
                        "visitor_code": item.get("visitor_code") or "",
                        "team_notification": True,
                    },
                    push=True,
                    push_markup=kb,
                )
                notified += 1

        with transaction.atomic():
            BotNotificationEvent.objects.create(
                event_type="INVOICE_STATUS",
                entity_type="invoice",
                entity_code=item["order_code"],
                visitor_code=item["visitor_code"],
                old_value=item["old_status"],
                new_value=event_key,
            )
            from reports.bot.services.activity import log_activity

            log_activity(
                "NOTIFICATION_SENT",
                metadata={"order_code": item["order_code"], "status": event_key},
            )
        return notified

    @classmethod
    def notify_sync_complete(cls, report_key: str, row_count: int = 0) -> int:
        """Notify connected users about a successful data sync (deduped per 2h window)."""
        label = SYNC_REPORT_LABELS.get(report_key, "اطلاعات")
        category = (
            BotUserNotification.CATEGORY_SETTLEMENT
            if report_key == "receivables_aging"
            else BotUserNotification.CATEGORY_SYNC
        )
        now = timezone.localtime()
        dedupe_key = f"sync:{report_key}:{now.date().isoformat()}:{now.hour // 2}"
        title = f"بروزرسانی {label}"
        body = cls._sync_body(label, row_count, now)

        identities = BaleUserIdentity.objects.filter(is_blocked=False).select_related("user")
        notified = 0
        for ident in identities:
            if cls._base_qs(ident.bale_user_id).filter(
                metadata__dedupe_key=dedupe_key
            ).exists():
                continue
            from reports.bot.keyboards.common import notification_sync_button

            cls.create(
                bale_user_id=ident.bale_user_id,
                user=ident.user,
                category=category,
                event_type="SYNC_COMPLETE",
                title=title,
                body=body,
                entity_type="sync",
                entity_code=report_key,
                metadata={"report_key": report_key, "row_count": row_count, "dedupe_key": dedupe_key},
                push=True,
                push_markup=notification_sync_button(report_key),
            )
            notified += 1
        return notified

    @classmethod
    def notify_system(
        cls,
        bale_user_id: int,
        user: User | None,
        title: str,
        body: str,
        *,
        push: bool = False,
    ) -> BotUserNotification:
        return cls.create(
            bale_user_id=bale_user_id,
            user=user,
            category=BotUserNotification.CATEGORY_SYSTEM,
            event_type="SYSTEM",
            title=title,
            body=body,
            push=push,
        )

    @classmethod
    def _invoice_status_body_for_supervisor(cls, item: dict) -> str:
        partner = item.get("partner_name") or "—"
        visitor = item.get("visitor_code") or "—"
        return (
            "🔔 تغییر وضعیت فاکتور تیم\n"
            "━━━━━━━━━━━━━━━━\n\n"
            f"🧾 فاکتور #{item['order_code']}\n"
            f"👤 مشتری: {partner}\n"
            f"🧍 ویزیتور: {visitor}\n\n"
            f"⏳ قبلی: {item['old_status']}\n"
            f"✅ جدید: {item['new_status']}\n\n"
            f"🕒 {timezone.localtime().strftime('%Y/%m/%d  %H:%M')}"
        )

    @classmethod
    def _invoice_status_body(cls, item: dict) -> str:
        partner = item.get("partner_name") or "—"
        return (
            "🔔 تغییر وضعیت فاکتور\n"
            "━━━━━━━━━━━━━━━━\n\n"
            f"🧾 فاکتور #{item['order_code']}\n"
            f"👤 {partner}\n\n"
            f"⏳ قبلی: {item['old_status']}\n"
            f"✅ جدید: {item['new_status']}\n\n"
            f"🕒 {timezone.localtime().strftime('%Y/%m/%d  %H:%M')}"
        )

    @classmethod
    def _sync_body(cls, label: str, row_count: int, when) -> str:
        count_line = f"\n📊 {row_count:,} رکورد بروزرسانی شد" if row_count else ""
        return (
            "🔄 بروزرسانی سیستم\n"
            "━━━━━━━━━━━━━━━━\n\n"
            f"بخش «{label}» با موفقیت به‌روز شد.{count_line}\n\n"
            f"🕒 {when.strftime('%Y/%m/%d  %H:%M')}\n\n"
            "برای مشاهده آخرین اطلاعات از منوی ربات استفاده کنید."
        )

    @classmethod
    def _push_message(cls, bale_user_id: int, text: str, markup=None) -> bool:
        if not getattr(settings, "BALE_BOT_ENABLED", False):
            return False
        token = getattr(settings, "BALE_BOT_TOKEN", "")
        if not token:
            return False
        try:
            import telebot
            from telebot import apihelper

            apihelper.API_URL = getattr(
                settings, "BALE_API_URL", "https://tapi.bale.ai/bot{0}/{1}"
            )
            bot = telebot.TeleBot(token, threaded=False)
            bot.send_message(bale_user_id, text, reply_markup=markup)
            return True
        except Exception:
            logger.exception("push notification failed for %s", bale_user_id)
            return False
