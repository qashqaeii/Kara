"""Grid response flattening and generic parsing."""

from __future__ import annotations

from typing import Any


def flatten_rows(raw_data: dict) -> list[dict[str, Any]]:
    """Convert Kara grid Data (Key/Value pairs) to flat row dicts."""
    rows: list[dict[str, Any]] = []
    for item in raw_data.get("Data", []) or []:
        if isinstance(item, dict) and "Value" in item:
            row = dict(item["Value"] or {})
            row["_key"] = item.get("Key")
            rows.append(row)
        elif isinstance(item, dict):
            rows.append(dict(item))
    return rows


def extract_sum_row(raw_data: dict | None) -> dict | None:
    if not raw_data:
        return None
    sum_row = raw_data.get("SumRowData")
    return sum_row if isinstance(sum_row, dict) else None
