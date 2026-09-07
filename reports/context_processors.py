"""Template context — currency, navigation, and user scope."""

from reports.services.access_control import AccessControlService
from reports.services.currency import currency_label, get_currency_unit
from reports.services.display import role_label
from reports.services.web_auth import WebAuthService


def currency_context(request):
    return {
        "currency_unit": currency_label(),
        "currency_unit_key": get_currency_unit().value,
    }


def kara_nav_context(request):
    user = request.user
    scope = AccessControlService.resolve_scope(user)
    perms = AccessControlService.nav_permissions(user)
    identity = AccessControlService.get_identity(user)
    return {
        "kara_scope": scope,
        "kara_nav": perms,
        "kara_identity": identity,
        "kara_role_label": role_label(scope.role),
        "kara_user_display": WebAuthService.display_name(user) if user.is_authenticated else "",
        "kara_personnel_code": (identity.personnel_code if identity else "") or "",
    }
