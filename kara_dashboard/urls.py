from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("reports/", include("reports.urls")),
    path("dashboard/", lambda request: redirect("reports:dashboard")),
    path("tv/", lambda request: redirect("reports:tv_mode")),
    path("", lambda request: redirect("reports:dashboard")),
]
