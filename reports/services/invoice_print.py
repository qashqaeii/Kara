"""Fetch and serve official Kara invoice print HTML via the portal proxy."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.cache import cache
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.urls import reverse

from reports.exceptions import InvalidResponseError

if TYPE_CHECKING:
    from reports.models import SaleOrderSnapshot
    from reports.services.kara_client import KaraClient

logger = logging.getLogger(__name__)

PRINT_SIGNER_SALT = "kara-invoice-print"
_ACCESS_DENIED_MARKERS = ("عدم دسترسی", "LoginFailed", "شما دسترسی مشاهده")


class InvoicePrintError(Exception):
    """User-facing invoice print failure."""


def get_print_template_id() -> str:
    return (
        getattr(settings, "KARA_INVOICE_PRINT_ID", "")
        or "451a9d74-8c8d-47e5-b6c6-abe3b26e41fd"
    ).strip()


def resolve_kara_order_id(order: SaleOrderSnapshot) -> str:
    kara_id = (order.kara_order_id or "").strip()
    if kara_id:
        return kara_id
    raw = order.raw_data if isinstance(order.raw_data, dict) else {}
    return str(raw.get("OrderId") or "").strip()


def can_print(order: SaleOrderSnapshot) -> bool:
    return bool(resolve_kara_order_id(order))


def is_access_denied_html(html: str) -> bool:
    text = html or ""
    return any(marker in text for marker in _ACCESS_DENIED_MARKERS)


_PORTAL_PRINT_CSS = """
<style id="portal-invoice-print-enhance">
@media screen {
    .NoPrint { display: none !important; }
}
</style>
"""


def prepare_print_html(html: str) -> str:
    """Inject Kara base URL and portal screen/print enhancements."""
    if not html:
        return html

    head_injections: list[str] = []
    if not re.search(r"<base\s", html, flags=re.IGNORECASE):
        base_href = settings.KARA_BASE_URL.rstrip("/") + "/Sale/Print/"
        head_injections.append(f'<base href="{base_href}">')
    if "portal-invoice-print-enhance" not in html:
        head_injections.append(_PORTAL_PRINT_CSS)

    if not head_injections:
        return html

    injection = "".join(head_injections)
    match = re.search(r"<head[^>]*>", html, flags=re.IGNORECASE)
    if match:
        idx = match.end()
        return html[:idx] + injection + html[idx:]
    return injection + html


def fetch_print_html(
    kara_order_id: str,
    *,
    client: KaraClient | None = None,
    use_cache: bool = True,
) -> str:
    kara_order_id = (kara_order_id or "").strip()
    if not kara_order_id:
        raise InvoicePrintError("شناسه چاپ فاکتور موجود نیست.")

    cache_key = f"kara_invoice_print:v3:{kara_order_id}"
    if use_cache:
        cached = cache.get(cache_key)
        if cached:
            return cached

    from reports.services.kara_client import KaraClient

    kara_client = client or KaraClient()
    try:
        html = kara_client.fetch_invoice_print(
            kara_order_id,
            print_id=get_print_template_id(),
        )
    except InvalidResponseError as exc:
        raise InvoicePrintError(str(exc)) from exc

    if is_access_denied_html(html):
        raise InvoicePrintError("دسترسی به چاپ فاکتور در کارا ممکن نیست.")

    prepared = prepare_print_html(html)
    if use_cache:
        timeout = int(getattr(settings, "KARA_INVOICE_PRINT_CACHE_SECONDS", 600))
        cache.set(cache_key, prepared, timeout=timeout)
    return prepared


def print_token_max_age() -> int:
    return int(getattr(settings, "KARA_INVOICE_PRINT_TOKEN_SECONDS", 900))


def sign_print_token(order_code: str, user_id: int) -> str:
    signer = TimestampSigner(salt=PRINT_SIGNER_SALT)
    return signer.sign(f"{order_code}:{user_id}")


def verify_print_token(token: str) -> tuple[str, int]:
    signer = TimestampSigner(salt=PRINT_SIGNER_SALT)
    try:
        value = signer.unsign(token, max_age=print_token_max_age())
    except SignatureExpired:
        raise InvoicePrintError("لینک چاپ منقضی شده است. از ربات دوباره درخواست دهید.") from None
    except BadSignature:
        raise InvoicePrintError("لینک چاپ معتبر نیست.") from None

    if ":" not in value:
        raise InvoicePrintError("لینک چاپ معتبر نیست.")
    order_code, user_id_raw = value.split(":", 1)
    try:
        user_id = int(user_id_raw)
    except ValueError:
        raise InvoicePrintError("لینک چاپ معتبر نیست.") from None
    return order_code.strip(), user_id


def portal_public_base() -> str:
    base = (getattr(settings, "PORTAL_PUBLIC_URL", "") or "").strip()
    if base:
        return base.rstrip("/")
    origins = getattr(settings, "CSRF_TRUSTED_ORIGINS", None)
    if origins:
        first = origins[0] if isinstance(origins, (list, tuple)) else str(origins)
        return str(first).strip().rstrip("/")
    return ""


def build_portal_print_url(order_code: str, user_id: int) -> str:
    token = sign_print_token(order_code, user_id)
    path = reverse(
        "reports:invoice_print",
        kwargs={"order_code": order_code},
    )
    base = portal_public_base()
    if base:
        return f"{base}{path}?token={token}"
    return f"{path}?token={token}"


def print_path_for_order(order_code: str) -> str:
    return reverse("reports:invoice_print", kwargs={"order_code": order_code})


def print_content_path_for_order(order_code: str) -> str:
    return reverse("reports:invoice_print_content", kwargs={"order_code": order_code})


def append_query_token(url: str, token: str) -> str:
    token = (token or "").strip()
    if not token:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}token={token}"
