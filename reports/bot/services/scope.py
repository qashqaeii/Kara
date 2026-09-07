"""Bot data scope helpers — team membership and visitor filtering."""

from __future__ import annotations

from functools import lru_cache

from django.contrib.auth.models import User
from django.db.models import QuerySet

from reports.constants import KaraRole
from reports.models import SalespersonDailyMetric, VisitorSaleSnapshot
from reports.services.access_control import AccessControlService
from reports.services.retention import find_latest_full_snapshot


def is_supervisor(user: User) -> bool:
    scope = AccessControlService.resolve_scope(user)
    return scope.role == KaraRole.SALES_SUPERVISOR and not scope.unrestricted


def is_salesperson(user: User) -> bool:
    scope = AccessControlService.resolve_scope(user)
    return scope.role == KaraRole.SALESPERSON and not scope.unrestricted


def supervisor_code(user: User) -> str:
    scope = AccessControlService.resolve_scope(user)
    if scope.role != KaraRole.SALES_SUPERVISOR:
        return ""
    return scope.supervisor_code or scope.personnel_code or ""


@lru_cache(maxsize=256)
def _team_codes_for_supervisor(supervisor_code: str) -> frozenset[str]:
    code = (supervisor_code or "").strip()
    if not code:
        return frozenset()

    codes: set[str] = set(
        SalespersonDailyMetric.objects.filter(supervisor_code=code)
        .exclude(personnel_code="")
        .values_list("personnel_code", flat=True)
        .distinct()
    )

    snap = find_latest_full_snapshot("visitor_sale")
    if snap:
        codes.update(
            VisitorSaleSnapshot.objects.filter(
                snapshot=snap, head_visitor_code=code
            )
            .exclude(visitor_code="")
            .values_list("visitor_code", flat=True)
            .distinct()
        )

    codes.discard("")
    return frozenset(codes)


def team_visitor_codes(user: User) -> frozenset[str]:
    """Distinct visitor personnel codes managed by this supervisor."""
    if not is_supervisor(user):
        return frozenset()
    return _team_codes_for_supervisor(supervisor_code(user))


def can_access_visitor(user: User, visitor_code: str) -> bool:
    code = (visitor_code or "").strip()
    if not code:
        return False
    scope = AccessControlService.resolve_scope(user)
    if scope.unrestricted:
        return True
    if scope.role == KaraRole.SALESPERSON:
        return code == scope.personnel_code
    if scope.role == KaraRole.SALES_SUPERVISOR:
        sup = scope.supervisor_code or scope.personnel_code
        if code == sup:
            return True
        return code in team_visitor_codes(user)
    return False


def apply_visitor_scope(qs: QuerySet, user: User, *, field: str = "visitor_code") -> QuerySet:
    """Restrict a queryset to the current user's allowed visitor codes."""
    scope = AccessControlService.resolve_scope(user)
    if scope.unrestricted:
        return qs

    if scope.role == KaraRole.SALESPERSON and scope.personnel_code:
        return qs.filter(**{field: scope.personnel_code})

    if scope.role == KaraRole.SALES_SUPERVISOR:
        team = team_visitor_codes(user)
        if not team:
            return qs.none()
        return qs.filter(**{f"{field}__in": team})

    return qs.none()


def scope_label_suffix(user: User) -> str:
    """Short Persian suffix for scoped UI labels (من / تیم)."""
    return "تیم" if is_supervisor(user) else "من"
