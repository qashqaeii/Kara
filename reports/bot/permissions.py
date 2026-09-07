"""Bot permission checks — server-side, not UI-only."""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import User

from reports.constants import KaraRole
from reports.services.access_control import AccessControlService


def is_bot_admin(user: User, bale_user_id: int) -> bool:
    identity = AccessControlService.get_identity(user)

    # ویزیتورها و سرپرستان هرگز منوی مدیریت نمی‌بینند — حتی اگر Bale ID در BALE_ADMIN_IDS باشد.
    if identity and identity.role in {KaraRole.SALESPERSON, KaraRole.SALES_SUPERVISOR}:
        return False

    if bale_user_id in getattr(settings, "BALE_ADMIN_IDS", []):
        return True
    if user.is_superuser:
        return True
    if identity and identity.role in {
        KaraRole.SYSTEM_ADMIN,
        KaraRole.EXECUTIVE_MANAGER,
        KaraRole.SALES_MANAGER,
    }:
        return True
    return False
