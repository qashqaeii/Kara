"""Admin panel data for bot."""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.models import User
from django.utils import timezone

from reports.constants import SyncStatus
from reports.models import (
    BaleUserIdentity,
    BotActivityLog,
    BotNotificationEvent,
    KaraSyncJob,
)
from reports.services.analytics import AnalyticsService


class BotAdminService:
    @classmethod
    def stats(cls) -> dict:
        today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        identities = BaleUserIdentity.objects.select_related("user")
        return {
            "connected": identities.count(),
            "active": identities.filter(is_blocked=False).count(),
            "logins_today": BotActivityLog.objects.filter(
                action="LOGIN_SUCCESS", created_at__gte=today
            ).count(),
            "failed_logins": BotActivityLog.objects.filter(
                action="LOGIN_FAILED", created_at__gte=today
            ).count(),
            "invoice_views": BotActivityLog.objects.filter(
                action="INVOICE_VIEW", created_at__gte=today
            ).count(),
            "searches": BotActivityLog.objects.filter(
                action="INVOICE_SEARCH", created_at__gte=today
            ).count(),
            "notifications": BotNotificationEvent.objects.filter(sent_at__gte=today).count(),
        }

    @classmethod
    def list_users(cls, search: str = "") -> list[BaleUserIdentity]:
        qs = BaleUserIdentity.objects.select_related("user", "user__kara_identity").order_by(
            "-last_login_at"
        )
        term = (search or "").strip()
        if term:
            qs = qs.filter(
                user__kara_identity__personnel_code__icontains=term
            ) | qs.filter(user__first_name__icontains=term) | qs.filter(
                user__last_name__icontains=term
            )
        return list(qs[:20])

    @classmethod
    def block_user(cls, bale_user_id: int, *, admin: User) -> bool:
        updated = BaleUserIdentity.objects.filter(bale_user_id=bale_user_id).update(
            is_blocked=True
        )
        if updated:
            from reports.bot.services.activity import log_activity

            log_activity(
                "ADMIN_BLOCK_USER",
                bale_user_id=bale_user_id,
                user=admin,
                metadata={"target": bale_user_id},
            )
        return bool(updated)

    @classmethod
    def unblock_user(cls, bale_user_id: int, *, admin: User) -> bool:
        updated = BaleUserIdentity.objects.filter(bale_user_id=bale_user_id).update(
            is_blocked=False,
            failed_login_count=0,
            locked_until=None,
        )
        if updated:
            from reports.bot.services.activity import log_activity

            log_activity(
                "ADMIN_UNBLOCK_USER",
                bale_user_id=bale_user_id,
                user=admin,
                metadata={"target": bale_user_id},
            )
        return bool(updated)

    @classmethod
    def sync_status(cls) -> dict:
        connection = AnalyticsService.connection_status()
        keys = ("sale_orders", "visitor_sale", "account_balance")
        reports = []
        for key in keys:
            job = KaraSyncJob.objects.filter(report_key=key).order_by("-started_at").first()
            ok = job and job.status == SyncStatus.SUCCESS
            reports.append({"key": key, "ok": ok})
        return {
            "last_sync_label": connection.get("last_sync_label") or "—",
            "reports": reports,
        }

    @classmethod
    def recent_logins(cls, limit: int = 10) -> list[BotActivityLog]:
        return list(
            BotActivityLog.objects.filter(action="LOGIN_SUCCESS")
            .select_related("user")
            .order_by("-created_at")[:limit]
        )

    @classmethod
    def recent_activities(cls, limit: int = 15) -> list[BotActivityLog]:
        return list(BotActivityLog.objects.select_related("user").order_by("-created_at")[:limit])
