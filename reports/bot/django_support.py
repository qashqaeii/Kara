"""Django ORM helpers for long-running telebot polling."""

from __future__ import annotations

import logging
from functools import wraps
from typing import Any, Callable, TypeVar

from django.db import close_old_connections

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def ensure_django_connection(func: F) -> F:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        close_old_connections()
        try:
            return func(*args, **kwargs)
        finally:
            close_old_connections()

    return wrapper  # type: ignore[return-value]
