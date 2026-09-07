"""Authentication and Bale user linking."""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone

from reports.models import BaleUserIdentity
from reports.bot.services.activity import log_activity
from reports.bot.services.credentials import BotCredentialService, normalize_personnel_code
from reports.bot.services.navigation import BotNavigationService


class AuthError(Exception):
    pass


class LockedError(AuthError):
    pass


class BlockedError(AuthError):
    pass


class BotAuthService:
    @staticmethod
    def get_identity(bale_user_id: int) -> BaleUserIdentity | None:
        return (
            BaleUserIdentity.objects.filter(bale_user_id=bale_user_id)
            .select_related("user", "user__kara_identity")
            .first()
        )

    @classmethod
    def get_linked_user(cls, bale_user_id: int) -> User | None:
        identity = cls.get_identity(bale_user_id)
        if identity and not identity.is_blocked:
            return identity.user
        return None

    @classmethod
    def _preauth_context(cls, bale_user_id: int) -> dict:
        return dict(BotNavigationService.get_state(bale_user_id).context or {})

    @classmethod
    def _set_preauth_context(cls, bale_user_id: int, **kwargs) -> None:
        ctx = cls._preauth_context(bale_user_id)
        ctx.update(kwargs)
        BotNavigationService.update_context(bale_user_id, **ctx)

    @classmethod
    def _record_failed_attempt(cls, bale_user_id: int) -> None:
        identity = cls.get_identity(bale_user_id)
        max_attempts = getattr(settings, "BALE_LOGIN_MAX_ATTEMPTS", 5)
        lock_min = getattr(settings, "BALE_LOGIN_LOCK_MINUTES", 15)
        if identity:
            identity.failed_login_count = (identity.failed_login_count or 0) + 1
            if identity.failed_login_count >= max_attempts:
                identity.locked_until = timezone.now() + timedelta(minutes=lock_min)
            identity.save(
                update_fields=["failed_login_count", "locked_until", "updated_at"]
            )
        else:
            ctx = cls._preauth_context(bale_user_id)
            failed = int(ctx.get("failed_login_count", 0)) + 1
            updates: dict = {"failed_login_count": failed}
            if failed >= max_attempts:
                updates["locked_until"] = (
                    timezone.now() + timedelta(minutes=lock_min)
                ).isoformat()
            cls._set_preauth_context(bale_user_id, **updates)
        log_activity("LOGIN_FAILED", bale_user_id=bale_user_id)

    @classmethod
    def ensure_not_locked(cls, bale_user_id: int) -> BaleUserIdentity | None:
        identity = cls.get_identity(bale_user_id)
        if identity and identity.is_blocked:
            raise BlockedError()
        if identity and identity.locked_until and identity.locked_until > timezone.now():
            raise LockedError()
        ctx = cls._preauth_context(bale_user_id)
        locked_until = ctx.get("locked_until")
        if locked_until:
            try:
                from datetime import datetime

                until = datetime.fromisoformat(locked_until)
                if timezone.is_naive(until):
                    until = timezone.make_aware(until)
                if until > timezone.now():
                    raise LockedError()
            except (ValueError, TypeError):
                pass
        return identity

    @classmethod
    def _is_locked_after_failure(cls, bale_user_id: int) -> bool:
        max_attempts = getattr(settings, "BALE_LOGIN_MAX_ATTEMPTS", 5)
        identity = cls.get_identity(bale_user_id)
        if identity and identity.locked_until:
            return True
        failed = int(cls._preauth_context(bale_user_id).get("failed_login_count", 0))
        return failed >= max_attempts

    @classmethod
    def validate_personnel_code(cls, personnel_code: str) -> str:
        code = normalize_personnel_code(personnel_code)
        if not code:
            raise AuthError("کد پرسنلی خالی است.")
        if not BotCredentialService.credential_exists(code):
            raise AuthError(
                "کد پرسنلی یافت نشد یا دسترسی ربات برای شما فعال نیست.\n"
                "لطفاً با پشتیبانی تماس بگیرید."
            )
        return code

    @classmethod
    def authenticate(
        cls, bale_user_id: int, personnel_code: str, password: str
    ) -> User:
        cls.ensure_not_locked(bale_user_id)
        code = cls.validate_personnel_code(personnel_code)
        password = (password or "").strip()
        if not password:
            raise AuthError("رمز عبور خالی است.")

        cred = BotCredentialService.get_credential(code)
        if not cred or not cred.check_password(password):
            cls._record_failed_attempt(bale_user_id)
            if cls._is_locked_after_failure(bale_user_id):
                raise LockedError()
            raise AuthError("رمز عبور نادرست است.")

        BaleUserIdentity.objects.update_or_create(
            bale_user_id=bale_user_id,
            defaults={
                "user": cred.user,
                "is_blocked": False,
                "failed_login_count": 0,
                "locked_until": None,
                "last_login_at": timezone.now(),
            },
        )
        BotNavigationService.clear_flow(bale_user_id)
        BotNavigationService.update_context(
            bale_user_id, failed_login_count=0, locked_until="", personnel_code=""
        )
        log_activity("LOGIN_SUCCESS", bale_user_id=bale_user_id, user=cred.user)
        return cred.user

    @classmethod
    def logout(cls, bale_user_id: int) -> None:
        identity = cls.get_identity(bale_user_id)
        if identity:
            user = identity.user
            identity.delete()
            log_activity("LOGOUT", bale_user_id=bale_user_id, user=user)
        BotConversationState_delete(bale_user_id)

    @classmethod
    def disconnect_bale(cls, bale_user_id: int) -> None:
        BaleUserIdentity.objects.filter(bale_user_id=bale_user_id).delete()
        BotConversationState_delete(bale_user_id)


def BotConversationState_delete(bale_user_id: int) -> None:
    from reports.models import BotConversationState

    BotConversationState.objects.filter(bale_user_id=bale_user_id).delete()
