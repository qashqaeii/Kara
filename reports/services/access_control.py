"""Row-level access control for Kara analytics."""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth.models import AnonymousUser, User

from reports.constants import KaraRole
from reports.models import UserKaraIdentity


@dataclass(frozen=True)
class AccessScope:
    """Resolved data scope for the current user."""

    role: str
    personnel_code: str = ""
    supervisor_code: str = ""
    allowed_city_codes: tuple[str, ...] = ()
    allowed_zone_codes: tuple[str, ...] = ()
    unrestricted: bool = True

    def filter_visitor_code(self, code: str) -> bool:
        if self.unrestricted:
            return True
        if self.role == KaraRole.SALESPERSON:
            return code == self.personnel_code
        if self.role == KaraRole.SALES_SUPERVISOR:
            from reports.bot.services.scope import _team_codes_for_supervisor

            sup = self.supervisor_code or self.personnel_code
            if not sup:
                return False
            if code == sup:
                return True
            return code in _team_codes_for_supervisor(sup)
        return False


class AccessControlService:
    MANAGEMENT_ROLES = frozenset(
        {
            KaraRole.SYSTEM_ADMIN,
            KaraRole.EXECUTIVE_MANAGER,
            KaraRole.SALES_MANAGER,
            KaraRole.VIEWER,
        }
    )

    @staticmethod
    def get_identity(user: User | AnonymousUser | None) -> UserKaraIdentity | None:
        if user is None or not user.is_authenticated:
            return None
        return getattr(user, "kara_identity", None)

    @classmethod
    def resolve_scope(cls, user: User | AnonymousUser | None) -> AccessScope:
        if user is None:
            user = AnonymousUser()
        if not user.is_authenticated:
            return AccessScope(role=KaraRole.VIEWER, unrestricted=False)

        if user.is_superuser or user.is_staff:
            return AccessScope(role=KaraRole.SYSTEM_ADMIN, unrestricted=True)

        identity = cls.get_identity(user)
        if identity is None or not identity.is_active:
            return AccessScope(role=KaraRole.VIEWER, unrestricted=True)

        if identity.is_executive or identity.role in cls.MANAGEMENT_ROLES:
            return AccessScope(role=identity.role, unrestricted=True)

        if identity.role == KaraRole.TV_DISPLAY:
            return AccessScope(role=identity.role, unrestricted=True)

        if identity.role == KaraRole.SALESPERSON:
            return AccessScope(
                role=identity.role,
                personnel_code=identity.personnel_code,
                unrestricted=False,
            )

        if identity.role == KaraRole.SALES_SUPERVISOR:
            return AccessScope(
                role=identity.role,
                supervisor_code=identity.supervisor_code or identity.personnel_code,
                personnel_code=identity.personnel_code,
                unrestricted=False,
            )

        return AccessScope(
            role=identity.role,
            personnel_code=identity.personnel_code,
            allowed_city_codes=tuple(identity.allowed_city_codes or []),
            allowed_zone_codes=tuple(identity.allowed_zone_codes or []),
            unrestricted=False,
        )

    @classmethod
    def can_view_company(cls, user: User | AnonymousUser) -> bool:
        return cls.resolve_scope(user).unrestricted

    @classmethod
    def can_manage_integration(cls, user: User | AnonymousUser) -> bool:
        if not user.is_authenticated:
            return False
        return bool(user.is_superuser or user.is_staff)

    @classmethod
    def can_access_visitor(cls, user: User | AnonymousUser, visitor_code: str) -> bool:
        code = (visitor_code or "").strip()
        if not code:
            return False
        scope = cls.resolve_scope(user)
        if scope.unrestricted:
            return True
        return scope.filter_visitor_code(code)

    @classmethod
    def filter_ranking_rows(
        cls,
        user: User | AnonymousUser,
        rows: list[dict],
        *,
        code_key: str = "code",
        fallback_key: str = "VisitorCode",
    ) -> list[dict]:
        scope = cls.resolve_scope(user)
        if scope.unrestricted:
            return rows

        def _code(row: dict) -> str:
            return str(row.get(code_key) or row.get(fallback_key) or "").strip()

        if scope.role == KaraRole.SALESPERSON and scope.personnel_code:
            return [r for r in rows if _code(r) == scope.personnel_code]

        if scope.role == KaraRole.SALES_SUPERVISOR:
            from reports.bot.services.scope import _team_codes_for_supervisor

            sup = scope.supervisor_code or scope.personnel_code
            if not sup:
                return []
            team = _team_codes_for_supervisor(sup)
            return [r for r in rows if _code(r) in team]

        return []

    @classmethod
    def filter_visitor_rows(cls, user: User | AnonymousUser, rows: list[dict]) -> list[dict]:
        scope = cls.resolve_scope(user)
        if scope.unrestricted:
            return rows
        if scope.role == KaraRole.SALESPERSON and scope.personnel_code:
            return [
                r
                for r in rows
                if str(r.get("VisitorCode", "")) == scope.personnel_code
            ]
        if scope.role == KaraRole.SALES_SUPERVISOR:
            from reports.bot.services.scope import _team_codes_for_supervisor

            sup = scope.supervisor_code or scope.personnel_code
            if not sup:
                return []
            team = _team_codes_for_supervisor(sup)
            return [r for r in rows if str(r.get("VisitorCode", "")) in team]
        return []

    @classmethod
    def can_access_tv(cls, user: User | AnonymousUser) -> bool:
        if not user.is_authenticated:
            return False
        scope = cls.resolve_scope(user)
        return scope.unrestricted or scope.role == KaraRole.TV_DISPLAY

    @classmethod
    def nav_permissions(cls, user: User | AnonymousUser) -> dict[str, bool]:
        scope = cls.resolve_scope(user)
        company = scope.unrestricted
        manage = cls.can_manage_integration(user)
        scoped = not scope.unrestricted
        return {
            "company": company,
            "manage": manage,
            "scoped": scoped,
            "invoices": user.is_authenticated,
            "my_performance": user.is_authenticated,
            "team": scope.role == KaraRole.SALES_SUPERVISOR,
            "salesperson": company or scope.role == KaraRole.SALES_SUPERVISOR,
            "supervisor": company,
            "regions": company,
            "receivables": company,
            "explorer": company,
            "sync": manage,
            "tv": cls.can_access_tv(user),
            "dashboard": company,
        }
