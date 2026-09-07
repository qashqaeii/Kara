"""Load tenant UUID lists from env or discovered endpoint dumps."""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote

from django.conf import settings

logger = logging.getLogger(__name__)

STUFF_GROUP_DUMP = "SaleReport_StuffGroupsGrid-endpoint.txt"
SALE_ORDERS_DUMP = "SaleOrdersReportGrid-endpoint.txt"


def _endpoints_dir() -> Path:
    return Path(settings.BASE_DIR) / "DOCS" / "ENDpoints"


def _read_dump_text(filename: str) -> str:
    path = _endpoints_dir() / filename
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def _extract_binding_arguments(text: str) -> str:
    """Return BindingArguments value from a Kara endpoint capture file."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "BindingArguments" and i + 1 < len(lines):
            return lines[i + 1].strip()
    # URL-encoded single-line capture (MontlyReportGrid style)
    for line in lines:
        if "BindingArguments=" in line:
            match = re.search(r"BindingArguments=([^&]+)", line)
            if match:
                return unquote(match.group(1))
    return ""


def _extract_query_param(binding: str, key: str) -> str:
    if not binding:
        return ""
    pattern = rf"(?:^|&){re.escape(key)}=([^&]*)"
    match = re.search(pattern, binding)
    return unquote(match.group(1)) if match else ""


@lru_cache(maxsize=1)
def entity_group_ids_from_dump() -> str:
    binding = _extract_binding_arguments(_read_dump_text(STUFF_GROUP_DUMP))
    return _extract_query_param(binding, "EntityGroupIds")


@lru_cache(maxsize=1)
def partner_group_ids_from_dump() -> str:
    binding = _extract_binding_arguments(_read_dump_text(STUFF_GROUP_DUMP))
    return _extract_query_param(binding, "PartnerGroupIds")


@lru_cache(maxsize=1)
def sale_orders_dynamic_partner_groups_from_dump() -> str:
    binding = _extract_binding_arguments(_read_dump_text(SALE_ORDERS_DUMP))
    return _extract_query_param(binding, "DynamicPartnerGroups")


def tenant_ids_status() -> dict[str, bool]:
    return {
        "entity_group_ids": bool(entity_group_ids()),
        "partner_group_ids": bool(partner_group_ids()),
        "sale_orders_dynamic_partner_groups": bool(sale_orders_dynamic_partner_groups()),
    }


def entity_group_ids() -> str:
    env = getattr(settings, "KARA_ENTITY_GROUP_IDS", "") or ""
    if env:
        return env
    dump = entity_group_ids_from_dump()
    if dump:
        logger.info("Using EntityGroupIds from %s", STUFF_GROUP_DUMP)
        return dump
    return "0"


def partner_group_ids() -> str:
    env = getattr(settings, "KARA_PARTNER_GROUP_IDS", "") or ""
    if env:
        return env
    dump = partner_group_ids_from_dump()
    if dump:
        logger.info("Using PartnerGroupIds from %s", STUFF_GROUP_DUMP)
        return dump
    return "0"


def sale_orders_dynamic_partner_groups() -> str:
    env = getattr(settings, "KARA_SALE_ORDERS_DYNAMIC_PARTNER_GROUPS", "") or ""
    if env:
        return env
    dump = sale_orders_dynamic_partner_groups_from_dump()
    if dump:
        logger.info("Using DynamicPartnerGroups from %s", SALE_ORDERS_DUMP)
        return dump
    return ""
