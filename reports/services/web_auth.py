"""Web dashboard authentication (session login)."""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core.cache import cache
from django.utils import timezone

from reports.bot.services.auth import AuthError
from reports.bot.services.credentials import BotCredentialService, normalize_personnel_code


class WebLoginLockedError(AuthError):
    pass


class WebAuthService:
    LOCK_PREFIX = "kara:web_login_lock:"
    FAIL_PREFIX = "kara:web_login_fail:"

    @classmethod
    def _max_attempts(cls) -> int:
        from django.conf import settings

        return int(getattr(settings, "WEB_LOGIN_MAX_ATTEMPTS", 5))

    @classmethod
    def _lock_minutes(cls) -> int:
        from django.conf import settings

        return int(getattr(settings, "WEB_LOGIN_LOCK_MINUTES", 15))

    @classmethod
    def _throttle_key(cls, login: str, ip: str) -> str:
        safe = normalize_personnel_code(login) or (login or "").strip().lower()
        return f"{safe}|{ip or 'unknown'}"

    @classmethod
    def ensure_not_locked(cls, login: str, ip: str = "") -> None:
        key = cls.LOCK_PREFIX + cls._throttle_key(login, ip)
        if cache.get(key):
            raise WebLoginLockedError(
                f"به دلیل تلاش‌های ناموفق، ورود به مدت {cls._lock_minutes()} دقیقه قفل شده است."
            )

    @classmethod
    def _record_failure(cls, login: str, ip: str = "") -> None:
        base = cls._throttle_key(login, ip)
        fail_key = cls.FAIL_PREFIX + base
        count = int(cache.get(fail_key) or 0) + 1
        cache.set(fail_key, count, timeout=cls._lock_minutes() * 60)
        if count >= cls._max_attempts():
            cache.set(cls.LOCK_PREFIX + base, True, timeout=cls._lock_minutes() * 60)

    @classmethod
    def _clear_failures(cls, login: str, ip: str = "") -> None:
        base = cls._throttle_key(login, ip)
        cache.delete(cls.FAIL_PREFIX + base)
        cache.delete(cls.LOCK_PREFIX + base)

    @classmethod
    def authenticate(cls, login: str, password: str, *, ip: str = "") -> User:
        """Accept Django username or Kara personnel code + password."""
        login_value = (login or "").strip()
        password_value = (password or "").strip()
        if not login_value or not password_value:
            raise AuthError("نام کاربری / کد پرسنلی و رمز عبور الزامی است.")

        cls.ensure_not_locked(login_value, ip)

        user = authenticate(username=login_value, password=password_value)
        if user and user.is_active:
            cls._clear_failures(login_value, ip)
            return user

        code = normalize_personnel_code(login_value)
        cred = BotCredentialService.get_credential(code) if code else None
        if cred and cred.check_password(password_value) and cred.user.is_active:
            cls._clear_failures(login_value, ip)
            return cred.user

        cls._record_failure(login_value, ip)
        raise AuthError("نام کاربری / کد پرسنلی یا رمز عبور نادرست است.")

    @classmethod
    def display_name(cls, user: User) -> str:
        identity = getattr(user, "kara_identity", None)
        if identity and identity.personnel_code:
            name = (user.get_full_name() or "").strip()
            if name:
                return name
            cred = getattr(user, "bot_credential", None)
            if cred and cred.display_name:
                return cred.display_name
            return identity.personnel_code
        return user.get_full_name() or user.get_username()

    @classmethod
    def touch_login(cls, user: User) -> None:
        identity = getattr(user, "kara_identity", None)
        if identity:
            identity.last_login_at = timezone.now()
            identity.save(update_fields=["last_login_at"])
