"""Audit logging for bot actions — no secrets."""

from __future__ import annotations

from typing import Any

from django.contrib.auth.models import User

from reports.models import BotActivityLog


def log_activity(
    action: str,
    *,
    bale_user_id: int | None = None,
    user: User | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    BotActivityLog.objects.create(
        bale_user_id=bale_user_id,
        user=user,
        action=action,
        metadata=metadata or {},
    )
