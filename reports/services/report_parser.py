"""
Backward-compatible shim — implementation lives in reports.services.parsers.
"""

from reports.services.parsers import (  # noqa: F401
    ReportParser,
    flatten_rows,
    format_number,
    normalize_digits,
    parse_number,
)
