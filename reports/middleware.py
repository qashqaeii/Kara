"""Require login for web dashboard routes."""

from __future__ import annotations

from django.contrib.auth.views import redirect_to_login
from django.http import JsonResponse
from django.urls import resolve, Resolver404


class ReportsLoginRequiredMiddleware:
    """Protect /reports/* except login/logout and static assets."""

    EXEMPT_NAMES = frozenset(
        {
            "reports:login",
            "reports:logout",
        }
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path or ""
        if not path.startswith("/reports/"):
            return self.get_response(request)

        try:
            match = resolve(path)
            if match.url_name and f"{match.namespace}:{match.url_name}" in self.EXEMPT_NAMES:
                return self.get_response(request)
        except Resolver404:
            pass

        if request.user.is_authenticated:
            return self.get_response(request)

        if path.startswith("/reports/api/"):
            return JsonResponse(
                {"ok": False, "error": "برای دسترسی باید وارد شوید.", "login_required": True},
                status=401,
            )

        return redirect_to_login(request.get_full_path())
