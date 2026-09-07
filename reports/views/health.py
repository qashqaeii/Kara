"""Lightweight health checks for load balancers and monitoring."""

from __future__ import annotations

from django.db import connection
from django.http import HttpRequest, JsonResponse


def health_view(request: HttpRequest) -> JsonResponse:
    db_ok = True
    try:
        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        db_ok = False

    payload = {
        "status": "ok" if db_ok else "degraded",
        "database": db_ok,
    }
    return JsonResponse(payload, status=200 if db_ok else 503)
