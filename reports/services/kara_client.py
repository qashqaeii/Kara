"""
HTTP client for Kara authentication and grid binding requests.

Dashboard UI must NEVER call this directly — use the Sync layer instead.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import urljoin

import requests
from django.conf import settings
from django.utils import timezone

from reports.constants import USER_AGENT_DEFAULT
from reports.exceptions import (
    AuthenticationError,
    InvalidResponseError,
    KaraNetworkError,
    LoginExpiredError,
)
from reports.services.payload_builder import build_grid_payload, merge_arguments
from reports.services.report_registry import ReportDefinition, ReportRegistry
from reports.services.session_store import (
    apply_cookie_string,
    load_persisted_cookies,
    save_session_cookies,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class KaraPrintResponse:
    report_key: str
    report_title: str
    html: str
    parsed: dict
    sum_row_data: dict | None
    duration_ms: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "report_key": self.report_key,
            "report_title": self.report_title,
            "html": self.html,
            "parsed": self.parsed,
            "SumRowData": self.sum_row_data,
            "Data": [],
            "GridViewJSTotal": 0,
            "GridViewJSFrom": 1,
            "GridViewJSCount": 0,
            "duration_ms": self.duration_ms,
        }


@dataclass
class KaraGridResponse:
    report_key: str
    report_name: str
    report_title: str
    total: int
    count: int
    data: list[dict]
    sum_row_data: dict | None
    other_informations: list
    personnel_code: str = ""
    duration_ms: int = 0
    page_count: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "report_key": self.report_key,
            "report_name": self.report_name,
            "report_title": self.report_title,
            "personnel_code": self.personnel_code,
            "GridViewJSTotal": self.total,
            "GridViewJSFrom": 1,
            "GridViewJSCount": self.count,
            "Data": self.data,
            "SumRowData": self.sum_row_data,
            "OtherInformations": self.other_informations,
            "duration_ms": self.duration_ms,
            "page_count": self.page_count,
        }


class KaraClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: int | None = None,
        user_agent: str | None = None,
        max_retries: int = 2,
    ) -> None:
        self.base_url = (base_url or settings.KARA_BASE_URL).rstrip("/")
        self.login_url = f"{self.base_url}/Home/LogIn"
        self.grid_binding_url = f"{self.base_url}/Common/GridBinding/_GridAjaxBinding"
        self.timeout = timeout if timeout is not None else settings.KARA_REQUEST_TIMEOUT
        self.user_agent = user_agent or getattr(settings, "KARA_USER_AGENT", USER_AGENT_DEFAULT)
        self.max_retries = max_retries
        self._session: requests.Session | None = None
        self._session_created_at: timezone.datetime | None = None
        self._auth_mode: str = "unknown"
        self._last_login_at: timezone.datetime | None = None

    # ------------------------------------------------------------------ auth
    @property
    def session(self) -> requests.Session:
        if self._session is None:
            self._session = self.create_authenticated_session()
        return self._session

    def create_base_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(
            {
                "Accept": "application/json, text/javascript, */*",
                "Accept-Language": "en-US,en;q=0.9,fa;q=0.8",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": self.base_url,
                "User-Agent": self.user_agent,
                "X-Requested-With": "XMLHttpRequest",
            }
        )
        return session

    def _credentials_available(self) -> bool:
        try:
            username, password = self._load_credentials()
            return bool(username and password)
        except AuthenticationError:
            return False

    def _load_credentials(self) -> tuple[str, str]:
        username = (os.environ.get("KARA_USERNAME") or getattr(settings, "KARA_USERNAME", "") or "").strip()
        password = (os.environ.get("KARA_PASSWORD") or getattr(settings, "KARA_PASSWORD", "") or "").strip()
        if username and password:
            return username, password

        credentials_file = Path(settings.KARA_CREDENTIALS_FILE)
        if credentials_file.exists():
            values: dict[str, str] = {}
            for line in credentials_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip().lower()] = value.strip()
            username = values.get("username", "")
            password = values.get("password", "")
            if username and password:
                return username, password

        raise AuthenticationError(
            "اطلاعات ورود یافت نشد. KARA_USERNAME/KARA_PASSWORD یا فایل credentials.txt را تنظیم کنید."
        )

    def _load_cookie(self) -> str | None:
        cookie = (os.environ.get("KARA_COOKIE") or getattr(settings, "KARA_COOKIE", "") or "").strip()
        if cookie:
            return cookie
        return load_persisted_cookies()

    def _init_session_cookie(self, session: requests.Session) -> None:
        # Home page is always HTML — do not treat it as session expiry.
        self._request(
            session.get,
            f"{self.base_url}/",
            headers={"Referer": self.base_url},
            expect_json=False,
        )

    def login(self, session: requests.Session | None = None, username: str | None = None, password: str | None = None) -> None:
        if session is None:
            session = self.create_base_session()
            self._session = session
        if username is None or password is None:
            username, password = self._load_credentials()

        self._init_session_cookie(session)
        response = self._request(
            session.post,
            self.login_url,
            data={"UserName": username, "Password": password},
            headers={"Referer": f"{self.base_url}/"},
            expect_json=True,
        )
        payload = self._safe_json(response)
        if not isinstance(payload, dict):
            raise AuthenticationError("پاسخ ورود معتبر نیست.")
        if payload.get("Success") is False:
            message = payload.get("Message", "LoginFailed")
            raise AuthenticationError(f"ورود ناموفق بود: {message}")
        if not session.cookies.get(".KaraAuthProvider"):
            raise AuthenticationError("ورود انجام شد اما کوکی احراز هویت دریافت نشد.")
        save_session_cookies(session)
        self._auth_mode = "credentials"
        self._last_login_at = timezone.now()
        self._session_created_at = self._last_login_at
        logger.info("Kara login ok for user %s", username)

    def ensure_authenticated(self) -> None:
        if self._session is None:
            self._session = self.create_authenticated_session()

    def logout(self) -> None:
        self.reset_session()

    def _login_with_credentials(self) -> requests.Session:
        session = self.create_base_session()
        self.login(session)
        return session

    def _session_from_cookie(self, cookie: str) -> requests.Session:
        session = self.create_base_session()
        apply_cookie_string(session, cookie)
        self._auth_mode = "cookie"
        self._session_created_at = timezone.now()
        logger.info("Kara session established via cookie")
        return session

    def create_authenticated_session(self) -> requests.Session:
        if self._credentials_available():
            return self._login_with_credentials()
        cookie = self._load_cookie()
        if not cookie:
            raise AuthenticationError(
                "اطلاعات ورود یافت نشد. credentials.txt یا KARA_COOKIE را تنظیم کنید."
            )
        return self._session_from_cookie(cookie)

    def reset_session(self) -> None:
        if self._session is not None:
            try:
                self._session.close()
            except Exception:
                pass
        self._session = None
        self._session_created_at = None

    def can_auto_recover(self) -> bool:
        if not getattr(settings, "KARA_SESSION_AUTO_RECOVER", True):
            return False
        return self._credentials_available()

    def recover_session(self) -> None:
        if not self.can_auto_recover():
            raise LoginExpiredError(
                "نشست کارا منقضی شده است و بازیابی خودکار ممکن نیست."
            )
        logger.warning("Kara session expired — re-login")
        self.reset_session()
        self._session = self._login_with_credentials()

    def execute_with_retry(self, operation: Callable[[], T]) -> T:
        try:
            return operation()
        except LoginExpiredError:
            if not self.can_auto_recover():
                raise
            self.recover_session()
            return operation()

    # -------------------------------------------------------------- requests
    def _request(self, method, url: str, *, expect_json: bool = True, **kwargs) -> requests.Response:
        """
        HTTP helper.

        ``expect_json=True`` (API calls): HTML body means session expired / login page.
        ``expect_json=False`` (page loads like ``/``): HTML is normal and allowed.
        """
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = method(url, timeout=self.timeout, **kwargs)
                if response.status_code in {401, 403}:
                    raise LoginExpiredError("نشست کارا منقضی شده است.")
                response.raise_for_status()
                if expect_json:
                    content_type = (response.headers.get("Content-Type") or "").lower()
                    text = (response.text or "").lstrip()
                    if ("text/html" in content_type and "json" not in content_type) or text.startswith("<"):
                        raise LoginExpiredError(
                            "نشست کارا منقضی شده است (پاسخ HTML به‌جای JSON)."
                        )
                return response
            except LoginExpiredError:
                raise
            except requests.Timeout as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    time.sleep(0.5 * (2**attempt))
                    continue
                raise KaraNetworkError(f"زمان ارتباط با سرور کارا به پایان رسید: {exc}") from exc
            except requests.RequestException as exc:
                last_exc = exc
                # Don't retry 4xx except auth
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status and 400 <= status < 500 and status not in {401, 403, 408, 429}:
                    raise KaraNetworkError(f"خطا در ارتباط با سرور کارا: {exc}") from exc
                if attempt < self.max_retries:
                    time.sleep(0.5 * (2**attempt))
                    continue
                raise KaraNetworkError(f"خطا در ارتباط با سرور کارا: {exc}") from exc
        raise KaraNetworkError(f"خطا در ارتباط با سرور کارا: {last_exc}")

    def _safe_json(self, response: requests.Response) -> dict | list:
        text = (response.text or "").lstrip()
        if text.startswith("<") or "text/html" in (response.headers.get("Content-Type") or "").lower():
            raise LoginExpiredError("نشست کارا منقضی شده است (پاسخ HTML به‌جای JSON).")
        try:
            return response.json()
        except ValueError as exc:
            raise InvalidResponseError("پاسخ گزارش قابل پردازش نبود.") from exc

    def _parse_grid_response(self, payload: dict) -> dict:
        if payload.get("Success") is False:
            message = payload.get("Message", "UnknownError")
            if message == "LoginExpiredError":
                raise LoginExpiredError("نشست کارا منقضی شده است.")
            raise InvalidResponseError(f"خطا از سمت سرور کارا: {message}")
        if "Data" not in payload:
            raise InvalidResponseError("پاسخ سرور معتبر نیست — فیلد Data وجود ندارد.")
        return payload

    # ---------------------------------------------------------------- reports
    def run_report(
        self,
        report_key: str,
        arguments: dict | None = None,
        page: int = 1,
        page_size: int | None = None,
        personnel_code: str = "",
    ) -> KaraGridResponse:
        report = ReportRegistry.get(report_key)
        if report.is_print_report:
            raise InvalidResponseError(
                f"گزارش '{report_key}' از نوع Print است — از run_print_report استفاده کنید."
            )
        if not report.binding_method:
            raise InvalidResponseError(f"گزارش '{report_key}' از نوع GridBinding نیست.")
        return self.execute_with_retry(
            lambda: self._run_report_once(
                report,
                arguments=arguments,
                page_size=page_size or report.page_size,
                personnel_code=personnel_code,
            )
        )

    def run_print_report(
        self,
        report_key: str,
        arguments: dict | None = None,
    ) -> KaraPrintResponse:
        report = ReportRegistry.get(report_key)
        if not report.is_print_report:
            raise InvalidResponseError(f"گزارش '{report_key}' گزارش چاپی نیست.")
        return self.execute_with_retry(
            lambda: self._run_print_once(report, arguments=arguments)
        )

    def fetch_report(
        self, report: ReportDefinition, personnel_code: str = ""
    ) -> dict:
        """Backward-compatible wrapper used by ReportFetcher."""
        result = self.run_report(report.key, personnel_code=personnel_code)
        return result.as_dict()

    def _run_report_once(
        self,
        report: ReportDefinition,
        *,
        arguments: dict | None,
        page_size: int,
        personnel_code: str,
    ) -> KaraGridResponse:
        started = time.monotonic()
        grid_from = 1
        all_rows: list[dict] = []
        total_count: int | None = None
        sum_row_data = None
        other_informations: list = []
        page_count = 0
        seen_from: set[int] = set()

        args = merge_arguments(report.default_arguments, arguments)
        if personnel_code:
            if "BPersonnelCode" in args:
                args["BPersonnelCode"] = personnel_code
                args["EPersonnelCode"] = personnel_code

        referer = urljoin(self.base_url + "/", report.referer.lstrip("/"))
        self.ensure_authenticated()

        while True:
            if grid_from in seen_from:
                logger.error("Pagination loop detected for %s at from=%s", report.key, grid_from)
                break
            seen_from.add(grid_from)

            payload = build_grid_payload(
                grid_name=report.grid_name,
                grid_title=report.grid_title,
                binding_class=report.binding_class,
                binding_method=report.binding_method,
                binding_arguments=args,
                grid_from=grid_from,
                page_size=page_size,
            )
            response = self._request(
                self.session.post,
                self.grid_binding_url,
                data=payload,
                headers={"Referer": referer},
            )
            body = self._parse_grid_response(self._safe_json(response))  # type: ignore[arg-type]
            page_count += 1

            if total_count is None:
                total_count = int(body.get("GridViewJSTotal", 0) or 0)
                sum_row = body.get("SumRowData")
                sum_row_data = sum_row if isinstance(sum_row, dict) else None
                other_informations = body.get("OtherInformations") or []

            rows = body.get("Data") or []
            all_rows.extend(rows)

            fetched_count = int(body.get("GridViewJSCount", len(rows)) or 0)
            if fetched_count <= 0 or total_count is None or grid_from + fetched_count > total_count:
                break
            if page_count > 500:
                logger.error("Pagination safety stop for %s after 500 pages", report.key)
                break
            grid_from += fetched_count

        duration_ms = int((time.monotonic() - started) * 1000)
        title = report.grid_title
        if personnel_code:
            title = f"{report.grid_title} — {personnel_code}"

        logger.info(
            "kara_report ok key=%s records=%s pages=%s duration_ms=%s",
            report.key,
            len(all_rows),
            page_count,
            duration_ms,
        )
        return KaraGridResponse(
            report_key=report.key,
            report_name=report.grid_name,
            report_title=title,
            total=total_count or len(all_rows),
            count=len(all_rows),
            data=all_rows,
            sum_row_data=sum_row_data,
            other_informations=other_informations if isinstance(other_informations, list) else [],
            personnel_code=personnel_code,
            duration_ms=duration_ms,
            page_count=page_count,
        )

    def _run_print_once(
        self,
        report: ReportDefinition,
        *,
        arguments: dict | None,
    ) -> KaraPrintResponse:
        from reports.services.parsers.profit_loss import parse_lost_benefit_html, parsed_to_sum_row

        started = time.monotonic()
        args = merge_arguments(report.default_arguments, arguments)
        referer = urljoin(self.base_url + "/", report.referer.lstrip("/"))
        print_url = urljoin(self.base_url + "/", report.print_path.lstrip("/"))
        self.ensure_authenticated()
        response = self._request(
            self.session.get,
            print_url,
            params=args,
            headers={"Referer": referer, "Accept": "text/html,application/xhtml+xml"},
            expect_json=False,
        )
        html = response.text or ""
        if not html.strip():
            raise InvalidResponseError("خروجی گزارش چاپی خالی بود.")
        parsed = parse_lost_benefit_html(html)
        if not parsed.get("net_pure_sale") and not parsed.get("net_profit"):
            raise InvalidResponseError("گزارش سود و زیان قابل پردازش نبود.")
        sum_row = parsed_to_sum_row(parsed)
        duration_ms = int((time.monotonic() - started) * 1000)
        logger.info(
            "kara_print ok key=%s duration_ms=%s",
            report.key,
            duration_ms,
        )
        return KaraPrintResponse(
            report_key=report.key,
            report_title=report.title,
            html=html,
            parsed=parsed,
            sum_row_data=sum_row,
            duration_ms=duration_ms,
        )

    # ----------------------------------------------------------- entity search
    def search_entities(
        self,
        entity_global_type: int = 10203,
        query: str = "",
        limit: int = 30,
        referer_path: str = "/Sale/Report/VisitorsSale",
    ) -> list[dict]:
        return self.execute_with_retry(
            lambda: self._search_entities_once(entity_global_type, query, limit, referer_path)
        )

    def _search_entities_once(
        self,
        entity_global_type: int,
        query: str,
        limit: int,
        referer_path: str,
    ) -> list[dict]:
        url = f"{self.base_url}/Accounting/Entity/EntityList"
        params = {
            "EntityGlobalType": str(entity_global_type),
            "q": query,
            "limit": str(limit),
            "timestamp": str(int(time.time() * 1000)),
        }
        referer = urljoin(self.base_url + "/", referer_path.lstrip("/"))
        self.ensure_authenticated()
        response = self._request(
            self.session.get,
            url,
            params=params,
            headers={"Referer": referer},
        )
        payload = self._safe_json(response)
        if not isinstance(payload, list):
            raise InvalidResponseError("پاسخ جستجوی موجودیت معتبر نیست.")
        return [
            {
                "id": item.get("Id", ""),
                "code": item.get("Code", ""),
                "name": item.get("Name", ""),
            }
            for item in payload
            if item.get("Code")
        ]

    def search_personnel(
        self, query: str, referer_path: str, limit: int = 30
    ) -> list[dict]:
        return self.search_entities(
            entity_global_type=10203,
            query=query,
            limit=limit,
            referer_path=referer_path,
        )

    def test_connection(self) -> dict[str, Any]:
        started = time.monotonic()
        try:
            self.reset_session()
            self.ensure_authenticated()
            if not self.session.cookies.get(".KaraAuthProvider"):
                raise AuthenticationError("کوکی احراز هویت پس از ورود موجود نیست.")
            # Prove the session works with a tiny JSON API call (not the HTML home page).
            self.search_entities(query="1", limit=1)
            return {
                "ok": True,
                "auth_mode": self._auth_mode,
                "duration_ms": int((time.monotonic() - started) * 1000),
                "last_login_at": self._last_login_at.isoformat() if self._last_login_at else None,
            }
        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc),
                "duration_ms": int((time.monotonic() - started) * 1000),
            }

    def get_session_info(self) -> dict[str, Any]:
        return {
            "auth_mode": self._auth_mode,
            "created_at": self._session_created_at.isoformat() if self._session_created_at else None,
            "last_login_at": self._last_login_at.isoformat() if self._last_login_at else None,
            "can_auto_recover": self.can_auto_recover(),
            "has_active_session": self._session is not None,
        }
