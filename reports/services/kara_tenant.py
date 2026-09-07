"""Tenant-specific Kara API argument defaults (EntityGroupIds, etc.)."""

from __future__ import annotations

import re

from reports.services.tenant_id_loader import (
    entity_group_ids,
    partner_group_ids,
    sale_orders_dynamic_partner_groups,
    tenant_ids_status,
)

__all__ = [
    "apply_tenant_overrides",
    "entity_group_ids",
    "partner_group_ids",
    "sale_orders_dynamic_partner_groups",
    "sanitize_guid_list",
    "tenant_ids_status",
]

_GUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def sanitize_guid_list(value: str) -> str:
    """
    Normalize Kara GUID list arguments.

    Keeps the leading ``0`` sentinel used by Kara browser payloads, drops empty
    / whitespace tokens, and rejects malformed GUID fragments that trigger
    SQL ``uniqueidentifier`` conversion errors.
    """
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    parts: list[str] = []
    for raw in text.split(","):
        token = raw.strip()
        if not token:
            continue
        if token == "0":
            parts.append("0")
            continue
        if _GUID_RE.fullmatch(token):
            parts.append(token.lower())
    return ",".join(parts)


def _needs_tenant_ids(value) -> bool:
    """True when value is missing or the Kara ``0`` sentinel (all groups)."""
    if value is None:
        return True
    text = str(value).strip()
    return text == "" or text == "0"


def apply_tenant_overrides(report_key: str, overrides: dict) -> dict:
    """Inject tenant UUID lists when not explicitly provided in sync arguments."""
    result = dict(overrides)
    if report_key in (
        "stuff_group_sale",
        "monthly_sale",
        "account_balance",
        "receivables_aging",
        "lost_benefit_separate",
    ):
        if _needs_tenant_ids(result.get("EntityGroupIds")):
            ids = entity_group_ids()
            if ids:
                result["EntityGroupIds"] = sanitize_guid_list(ids)
        elif result.get("EntityGroupIds"):
            result["EntityGroupIds"] = sanitize_guid_list(str(result["EntityGroupIds"]))

        if _needs_tenant_ids(result.get("PartnerGroupIds")):
            ids = partner_group_ids()
            if ids:
                result["PartnerGroupIds"] = sanitize_guid_list(ids)
        elif result.get("PartnerGroupIds"):
            result["PartnerGroupIds"] = sanitize_guid_list(str(result["PartnerGroupIds"]))

    if report_key == "sale_orders" and not result.get("DynamicPartnerGroups"):
        groups = sale_orders_dynamic_partner_groups()
        if groups:
            result["DynamicPartnerGroups"] = groups
    if report_key == "sale_orders_with_stuffs" and not result.get("DynamicPartnerGroups"):
        groups = sale_orders_dynamic_partner_groups()
        if groups:
            result["DynamicPartnerGroups"] = groups
    return result
