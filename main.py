"""
دریافت گزارش‌های فروش از سیستم Kara و ذخیره در فایل JSON.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests

BASE_URL = "http://app.pakhshmarket.com"
LOGIN_URL = f"{BASE_URL}/Home/LogIn"
GRID_BINDING_URL = f"{BASE_URL}/Common/GridBinding/_GridAjaxBinding"
OUTPUT_DIR = Path(__file__).resolve().parent / "data"
CREDENTIALS_FILE = Path(__file__).resolve().parent / "credentials.txt"
COOKIE_FILE = Path(__file__).resolve().parent / "cookies.txt"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/149.0.0.0 Safari/537.36"
)

REPORT_BASED_ON = (
    "Inserted|Confirmed|Total|Shipment|ConfirmedShipment|TotalReversion|"
    "WaitingForAccountingConfirm|Final|"
)

REPORTS = {
    "visitor_sale": {
        "filename": "visitor_sale_report.json",
        "grid_name": "VisitorSaleReportGrid",
        "grid_title": "گزارش صورت وضعیت ویزیتور",
        "referer": f"{BASE_URL}/Sale/Report/VisitorsSale",
        "head_visitor_sale": "False",
        "page_size": 100,
    },
    "head_visitor_sale": {
        "filename": "head_visitor_sale_report.json",
        "grid_name": "HeadVisitorSaleReportGrid",
        "grid_title": "گزارش صورت وضعیت سرپرست",
        "referer": f"{BASE_URL}/Sale/Report/HeadVisitorsSale",
        "head_visitor_sale": "True",
        "page_size": 100,
    },
}


def load_credentials() -> tuple[str, str]:
    username = os.environ.get("KARA_USERNAME", "").strip()
    password = os.environ.get("KARA_PASSWORD", "").strip()
    if username and password:
        return username, password

    if CREDENTIALS_FILE.exists():
        values: dict[str, str] = {}
        for line in CREDENTIALS_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip().lower()] = value.strip()

        username = values.get("username", "")
        password = values.get("password", "")
        if username and password:
            return username, password

    raise RuntimeError(
        "اطلاعات ورود یافت نشد.\n"
        "یکی از این روش‌ها را انجام دهید:\n"
        "  1) متغیرهای KARA_USERNAME و KARA_PASSWORD را تنظیم کنید\n"
        "  2) فایل credentials.txt بسازید:\n"
        "       username=نام کاربری\n"
        "       password=رمز عبور"
    )


def load_cookie() -> str | None:
    cookie = os.environ.get("KARA_COOKIE", "").strip()
    if cookie:
        return cookie

    if COOKIE_FILE.exists():
        cookie = COOKIE_FILE.read_text(encoding="utf-8").strip()
        if cookie:
            return cookie

    return None


def create_base_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/json, text/javascript, */*",
            "Accept-Language": "en-US,en;q=0.9,fa;q=0.8",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": BASE_URL,
            "User-Agent": USER_AGENT,
            "X-Requested-With": "XMLHttpRequest",
        }
    )
    return session


def init_session_cookie(session: requests.Session) -> None:
    session.get(
        f"{BASE_URL}/",
        headers={"Referer": BASE_URL},
        timeout=60,
    )


def login(session: requests.Session, username: str, password: str) -> None:
    init_session_cookie(session)

    response = session.post(
        LOGIN_URL,
        data={"UserName": username, "Password": password},
        headers={"Referer": f"{BASE_URL}/"},
        timeout=60,
    )
    response.raise_for_status()

    payload = response.json()
    if payload.get("Success") is False:
        message = payload.get("Message", "LoginFailed")
        raise RuntimeError(f"ورود ناموفق بود: {message}")

    if not session.cookies.get(".KaraAuthProvider"):
        raise RuntimeError("ورود انجام شد اما کوکی احراز هویت دریافت نشد.")


def create_authenticated_session() -> requests.Session:
    username = os.environ.get("KARA_USERNAME", "").strip()
    password = os.environ.get("KARA_PASSWORD", "").strip()
    has_credentials = bool(username and password) or CREDENTIALS_FILE.exists()

    if has_credentials:
        login_username, login_password = load_credentials()
        session = create_base_session()
        print("در حال ورود به سیستم ...")
        login(session, login_username, login_password)
        print("ورود موفق بود.")
        return session

    cookie = load_cookie()
    if cookie:
        session = create_base_session()
        session.headers["Cookie"] = cookie
        return session

    raise RuntimeError(
        "اطلاعات ورود یافت نشد.\n"
        "فایل credentials.txt بسازید یا متغیرهای "
        "KARA_USERNAME و KARA_PASSWORD را تنظیم کنید."
    )


def build_binding_arguments(head_visitor_sale: str) -> str:
    return (
        "BPersonnelCode=&EPersonnelCode=&BPartnerCode=&EPartnerCode="
        "&BOrderCode=&EOrderCode=&BDate=&EDate=&BPreOrderInsertDate="
        "&EPreOrderInsertDate=&BoundSettlementInDate=false&TimeGrouping=0"
        f"&ReportBasedOn={REPORT_BASED_ON}"
        "&HeadVisitorCode=0&Period=&IncludeFreeProductPrices=false"
        f"&HeadVisitorSale={head_visitor_sale}&WithPartnerGroup=false&"
    )


def build_payload(report: dict, grid_from: int, page_size: int) -> dict[str, str]:
    return {
        "GridName": report["grid_name"],
        "GridTitle": report["grid_title"],
        "GridJSFrom": str(grid_from),
        "GridJSCount": str(page_size),
        "GridJSTotal": "0",
        "SortColumn": "",
        "SortOrder": "none",
        "ColumnFilterString": "",
        "BindingClass": "Kara.BLL.Sale.Report",
        "BindingMethod": "GetReportBinding_VisitorsSale",
        "BindingArguments": build_binding_arguments(report["head_visitor_sale"]),
        "ExportType": "Grid",
    }


def parse_grid_response(payload: dict) -> dict:
    if payload.get("Success") is False:
        message = payload.get("Message", "UnknownError")
        if message == "LoginExpiredError":
            raise RuntimeError(
                "نشست ورود منقضی شده است. دوباره python main.py را اجرا کنید."
            )
        raise RuntimeError(f"خطا از سمت سرور: {message}")

    if "Data" not in payload:
        raise RuntimeError("پاسخ سرور معتبر نیست.")

    return payload


def fetch_report(session: requests.Session, report: dict) -> dict:
    page_size = report["page_size"]
    grid_from = 1
    all_rows: list[dict] = []
    total_count: int | None = None
    sum_row_data = None
    other_informations: list | None = None

    while True:
        response = session.post(
            GRID_BINDING_URL,
            data=build_payload(report, grid_from, page_size),
            headers={"Referer": report["referer"]},
            timeout=60,
        )
        response.raise_for_status()
        payload = parse_grid_response(response.json())

        if total_count is None:
            total_count = int(payload.get("GridViewJSTotal", 0))
            sum_row_data = payload.get("SumRowData")
            other_informations = payload.get("OtherInformations", [])

        rows = payload.get("Data", [])
        all_rows.extend(rows)

        fetched_count = int(payload.get("GridViewJSCount", len(rows)))
        if fetched_count <= 0 or grid_from + fetched_count > total_count:
            break

        grid_from += fetched_count

    return {
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "report_name": report["grid_name"],
        "report_title": report["grid_title"],
        "GridViewJSTotal": total_count,
        "GridViewJSFrom": 1,
        "GridViewJSCount": len(all_rows),
        "Data": all_rows,
        "SumRowData": sum_row_data,
        "OtherInformations": other_informations or [],
    }


def save_json(data: dict, filepath: Path) -> None:
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with filepath.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def fetch_and_save_all() -> dict[str, Path]:
    session = create_authenticated_session()
    saved_files: dict[str, Path] = {}

    for report_key, report in REPORTS.items():
        print(f"در حال دریافت: {report['grid_title']} ...")
        data = fetch_report(session, report)
        output_path = OUTPUT_DIR / report["filename"]
        save_json(data, output_path)
        saved_files[report_key] = output_path
        print(f"  {len(data['Data'])} ردیف ذخیره شد -> {output_path}")

    return saved_files


def configure_console_encoding() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")


def main() -> int:
    configure_console_encoding()
    try:
        saved_files = fetch_and_save_all()
    except requests.RequestException as error:
        print(f"خطا در ارتباط با سرور: {error}", file=sys.stderr)
        return 1
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 1

    print("\nفایل‌های JSON:")
    for name, path in saved_files.items():
        print(f"  - {name}: {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
