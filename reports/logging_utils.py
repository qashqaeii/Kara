"""Production logging helpers — redact secrets from log output."""

from __future__ import annotations

import logging
import re

_SENSITIVE_PATTERNS = (
    re.compile(
        r"(?i)(password|passwd|secret|token|cookie|authorization|api[_-]?key)"
        r"(\s*[=:]\s*|\s+)([^\s,;\"']+)"
    ),
    re.compile(r"(?i)(\.KaraAuthProvider=)[^;\s]+"),
    re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._\-+/=]+"),
)


def redact_sensitive_text(text: str) -> str:
    redacted = text
    for pattern in _SENSITIVE_PATTERNS:
        if pattern.groups >= 3:
            redacted = pattern.sub(r"\1\2***REDACTED***", redacted)
        else:
            redacted = pattern.sub(r"\1***REDACTED***", redacted)
    return redacted


class SensitiveDataFilter(logging.Filter):
    """Strip tokens, passwords, and cookies from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_sensitive_text(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    key: redact_sensitive_text(str(value)) if isinstance(value, str) else value
                    for key, value in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    redact_sensitive_text(str(arg)) if isinstance(arg, str) else arg
                    for arg in record.args
                )
        return True
