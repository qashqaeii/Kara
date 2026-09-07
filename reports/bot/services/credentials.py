"""Bot visitor credential provisioning and validation."""

from __future__ import annotations

import secrets
import string
import time
from dataclasses import dataclass

from django.contrib.auth.models import User
from django.db import OperationalError, transaction
from django.utils import timezone
from django.utils.crypto import get_random_string

from reports.constants import KaraRole
from reports.models import (
    BotVisitorCredential,
    HeadVisitorSaleSnapshot,
    UserKaraIdentity,
    VisitorSaleSnapshot,
)
from reports.services.parsers.values import normalize_digits


def normalize_personnel_code(value: str) -> str:
    return normalize_digits((value or "").strip())


def _username_for_code(personnel_code: str, *, role: str = KaraRole.SALESPERSON) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in personnel_code)
    prefix = "supervisor" if role == KaraRole.SALES_SUPERVISOR else "visitor"
    return f"{prefix}_{safe}"[:150]


@dataclass
class ProvisionResult:
    personnel_code: str
    display_name: str
    created: bool
    password: str | None = None


class BotCredentialService:
    @staticmethod
    def synced_visitors() -> list[dict[str, str]]:
        """Distinct visitors from latest synced Kara data."""
        rows = (
            VisitorSaleSnapshot.objects.exclude(visitor_code="")
            .order_by("visitor_code", "-last_seen_at")
            .values("visitor_code", "visitor_name")
        )
        seen: dict[str, str] = {}
        for row in rows:
            code = normalize_personnel_code(str(row["visitor_code"]))
            if not code or code in seen:
                continue
            seen[code] = (row.get("visitor_name") or "").strip()
        return [{"code": c, "name": n} for c, n in sorted(seen.items())]

    @classmethod
    def credential_exists(cls, personnel_code: str) -> bool:
        code = normalize_personnel_code(personnel_code)
        return BotVisitorCredential.objects.filter(
            personnel_code=code, is_active=True
        ).exists()

    @classmethod
    def get_credential(cls, personnel_code: str) -> BotVisitorCredential | None:
        code = normalize_personnel_code(personnel_code)
        if not code:
            return None
        return (
            BotVisitorCredential.objects.filter(personnel_code=code, is_active=True)
            .select_related("user", "user__kara_identity")
            .first()
        )

    @classmethod
    def default_password(cls, personnel_code: str) -> str:
        """Default bot password equals personnel code."""
        return normalize_personnel_code(personnel_code)

    @classmethod
    def generate_password(cls, length: int = 8) -> str:
        alphabet = string.digits
        return "".join(secrets.choice(alphabet) for _ in range(length))

    @staticmethod
    def synced_supervisors() -> list[dict[str, str]]:
        """Distinct supervisors from latest synced Kara data."""
        rows = (
            HeadVisitorSaleSnapshot.objects.exclude(head_visitor_code="")
            .order_by("head_visitor_code", "-last_seen_at")
            .values("head_visitor_code", "head_visitor_name")
        )
        seen: dict[str, str] = {}
        for row in rows:
            code = normalize_personnel_code(str(row["head_visitor_code"]))
            if not code or code in seen:
                continue
            seen[code] = (row.get("head_visitor_name") or "").strip()
        return [{"code": c, "name": n} for c, n in sorted(seen.items())]

    @classmethod
    def detect_role(cls, personnel_code: str) -> str:
        code = normalize_personnel_code(personnel_code)
        identity = UserKaraIdentity.objects.filter(personnel_code=code).first()
        if identity:
            return identity.role
        if HeadVisitorSaleSnapshot.objects.filter(head_visitor_code=code).exists():
            return KaraRole.SALES_SUPERVISOR
        return KaraRole.SALESPERSON

    @classmethod
    @transaction.atomic
    def ensure_user_for_personnel(
        cls,
        personnel_code: str,
        display_name: str = "",
        *,
        role: str | None = None,
    ) -> tuple[User, bool]:
        code = normalize_personnel_code(personnel_code)
        resolved_role = role or cls.detect_role(code)
        cred = BotVisitorCredential.objects.filter(personnel_code=code).select_related(
            "user"
        ).first()
        if cred:
            if display_name and cred.display_name != display_name:
                cred.display_name = display_name
                cred.save(update_fields=["display_name", "updated_at"])
            identity = getattr(cred.user, "kara_identity", None)
            if identity and identity.role != resolved_role:
                identity.role = resolved_role
                if resolved_role == KaraRole.SALES_SUPERVISOR:
                    identity.supervisor_code = code
                identity.save(update_fields=["role", "supervisor_code", "updated_at"])
            return cred.user, False

        identity = (
            UserKaraIdentity.objects.filter(personnel_code=code)
            .select_related("user")
            .first()
        )
        if identity:
            user = identity.user
            created = False
            if identity.role != resolved_role:
                identity.role = resolved_role
                if resolved_role == KaraRole.SALES_SUPERVISOR:
                    identity.supervisor_code = code
                identity.save(update_fields=["role", "supervisor_code", "updated_at"])
        else:
            username = _username_for_code(code, role=resolved_role)
            base = username
            n = 1
            while User.objects.filter(username=username).exists():
                username = f"{base}_{n}"
                n += 1
            user = User.objects.create_user(
                username=username,
                password=get_random_string(32),
                first_name=display_name[:30] if display_name else "",
            )
            identity_kwargs: dict = {
                "user": user,
                "personnel_code": code,
                "role": resolved_role,
                "is_active": True,
            }
            if resolved_role == KaraRole.SALES_SUPERVISOR:
                identity_kwargs["supervisor_code"] = code
            UserKaraIdentity.objects.create(**identity_kwargs)
            created = True

        return user, created

    @classmethod
    @transaction.atomic
    def ensure_user_for_visitor(
        cls, personnel_code: str, display_name: str = ""
    ) -> tuple[User, bool]:
        return cls.ensure_user_for_personnel(
            personnel_code, display_name, role=KaraRole.SALESPERSON
        )

    @classmethod
    @transaction.atomic
    def set_password(cls, personnel_code: str, raw_password: str) -> BotVisitorCredential:
        code = normalize_personnel_code(personnel_code)
        cred = BotVisitorCredential.objects.filter(personnel_code=code).first()
        if not cred:
            raise ValueError(f"اعتبار ورود برای کد {code} یافت نشد.")
        cred.set_password(raw_password)
        cred.is_active = True
        cred.save(
            update_fields=[
                "password",
                "password_changed_at",
                "must_change_password",
                "is_active",
                "updated_at",
            ]
        )
        return cred

    @classmethod
    @transaction.atomic
    def provision(
        cls,
        personnel_code: str,
        *,
        display_name: str = "",
        password: str | None = None,
        generate: bool = False,
        role: str | None = None,
    ) -> ProvisionResult:
        code = normalize_personnel_code(personnel_code)
        if not code:
            raise ValueError("کد پرسنلی خالی است.")

        existing = BotVisitorCredential.objects.filter(personnel_code=code).first()
        resolved_role = role or cls.detect_role(code)

        if existing and not password and not generate:
            user, upgraded = cls.ensure_user_for_personnel(
                code,
                display_name or existing.display_name,
                role=resolved_role,
            )
            if display_name and existing.display_name != display_name:
                existing.display_name = display_name
                existing.save(update_fields=["display_name", "updated_at"])
            return ProvisionResult(
                personnel_code=code,
                display_name=existing.display_name,
                created=upgraded,
            )

        user, user_created = cls.ensure_user_for_personnel(
            code, display_name, role=resolved_role
        )
        if password:
            raw_password = password
        elif generate:
            raw_password = cls.generate_password()
        else:
            raw_password = cls.default_password(code)

        cred, cred_created = BotVisitorCredential.objects.get_or_create(
            personnel_code=code,
            defaults={
                "user": user,
                "display_name": display_name,
                "is_active": True,
            },
        )
        if not cred_created:
            cred.user = user
            cred.display_name = display_name or cred.display_name
            cred.is_active = True
        cred.set_password(raw_password)
        cred.save()

        return ProvisionResult(
            personnel_code=code,
            display_name=display_name or cred.display_name,
            created=user_created or cred_created,
            password=raw_password,
        )

    @classmethod
    def provision_from_sync(
        cls,
        *,
        password: str | None = None,
        generate: bool = False,
        only_missing: bool = True,
        role: str = KaraRole.SALESPERSON,
    ) -> list[ProvisionResult]:
        results: list[ProvisionResult] = []
        source = (
            cls.synced_supervisors()
            if role == KaraRole.SALES_SUPERVISOR
            else cls.synced_visitors()
        )
        for person in source:
            code = person["code"]
            if only_missing and cls.credential_exists(code):
                continue
            result = cls._provision_with_retry(
                code,
                display_name=person["name"],
                password=password,
                generate=generate,
                role=role,
            )
            results.append(result)
        return results

    @classmethod
    def upgrade_synced_supervisors(cls) -> list[ProvisionResult]:
        """Ensure synced supervisors have SALES_SUPERVISOR role (fixes visitor mis-provision)."""
        results: list[ProvisionResult] = []
        for person in cls.synced_supervisors():
            if not cls.credential_exists(person["code"]):
                continue
            results.append(
                cls.provision_supervisor(
                    person["code"],
                    display_name=person["name"],
                )
            )
        return results

    @classmethod
    def provision_supervisor(
        cls,
        personnel_code: str,
        *,
        display_name: str = "",
        password: str | None = None,
        generate: bool = False,
    ) -> ProvisionResult:
        return cls.provision(
            personnel_code,
            display_name=display_name,
            password=password,
            generate=generate,
            role=KaraRole.SALES_SUPERVISOR,
        )

    @classmethod
    def _provision_with_retry(
        cls,
        personnel_code: str,
        *,
        display_name: str = "",
        password: str | None = None,
        generate: bool = False,
        role: str | None = None,
        max_attempts: int = 8,
    ) -> ProvisionResult:
        last_error: Exception | None = None
        for attempt in range(max_attempts):
            try:
                return cls.provision(
                    personnel_code,
                    display_name=display_name,
                    password=password,
                    generate=generate,
                    role=role,
                )
            except OperationalError as exc:
                last_error = exc
                if "locked" not in str(exc).lower() or attempt >= max_attempts - 1:
                    raise
                time.sleep(0.25 * (attempt + 1))
        if last_error:
            raise last_error
        raise RuntimeError("provision retry failed")
