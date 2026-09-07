"""Build form-urlencoded payloads and nested BindingArguments for Kara grids."""

from __future__ import annotations

from typing import Any


def encode_binding_arguments(arguments: dict[str, Any]) -> str:
    """
    Encode a dict into Kara's nested BindingArguments query string.

    Keys keep insertion order. Empty/None values become empty strings.
    Booleans become lowercase true/false. Trailing ``&`` is preserved
    to match Kara's browser payloads.
    """
    parts: list[str] = []
    for key, value in arguments.items():
        if value is None:
            raw = ""
        elif isinstance(value, bool):
            raw = "true" if value else "false"
        else:
            raw = str(value)
        # Kara expects unencoded keys/values inside BindingArguments,
        # then the whole string is form-urlencoded by requests.
        parts.append(f"{key}={raw}")
    return "&".join(parts) + ("&" if parts else "")


def build_grid_payload(
    *,
    grid_name: str,
    grid_title: str,
    binding_class: str,
    binding_method: str,
    binding_arguments: dict[str, Any],
    grid_from: int = 1,
    page_size: int = 100,
    grid_total: int = 0,
    sort_column: str = "",
    sort_order: str = "none",
    column_filter_string: str = "",
    export_type: str = "Grid",
) -> dict[str, str]:
    return {
        "GridName": grid_name,
        "GridTitle": grid_title,
        "GridJSFrom": str(grid_from),
        "GridJSCount": str(page_size),
        "GridJSTotal": str(grid_total),
        "SortColumn": sort_column,
        "SortOrder": sort_order,
        "ColumnFilterString": column_filter_string,
        "BindingClass": binding_class,
        "BindingMethod": binding_method,
        "BindingArguments": encode_binding_arguments(binding_arguments),
        "ExportType": export_type,
    }


def merge_arguments(
    defaults: dict[str, Any],
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged = dict(defaults)
    if overrides:
        merged.update({k: v for k, v in overrides.items() if v is not None})
    return merged
