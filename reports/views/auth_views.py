"""Web login and logout."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import login, logout
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from reports.bot.services.auth import AuthError
from reports.services.access_control import AccessControlService
from reports.services.web_auth import WebAuthService, WebLoginLockedError


def _client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def _post_login_redirect(user, next_url: str = "") -> str:
    if next_url and next_url.startswith("/reports/"):
        return next_url
    if AccessControlService.can_view_company(user):
        return reverse("reports:dashboard")
    return reverse("reports:my_performance")


class LoginView(View):
    template_name = "reports/auth/login.html"

    def get(self, request):
        if request.user.is_authenticated:
            return redirect(_post_login_redirect(request.user))
        return render(
            request,
            self.template_name,
            {"next": request.GET.get("next", "")},
        )

    def post(self, request):
        login_value = (request.POST.get("login") or "").strip()
        password = request.POST.get("password") or ""
        next_url = (request.POST.get("next") or "").strip()
        ip = _client_ip(request)

        try:
            user = WebAuthService.authenticate(login_value, password, ip=ip)
        except WebLoginLockedError as exc:
            messages.error(request, str(exc))
            return render(request, self.template_name, {"next": next_url, "login": login_value})
        except AuthError as exc:
            messages.error(request, str(exc))
            return render(request, self.template_name, {"next": next_url, "login": login_value})

        login(request, user)
        WebAuthService.touch_login(user)
        messages.success(request, f"خوش آمدید، {WebAuthService.display_name(user)}")
        return redirect(_post_login_redirect(user, next_url))


class LogoutView(View):
    def post(self, request):
        logout(request)
        messages.info(request, "با موفقیت خارج شدید.")
        return redirect("reports:login")

    def get(self, request):
        return self.post(request)
