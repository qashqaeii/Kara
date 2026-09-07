"""Shared enums and constants for Kara dashboard."""

from __future__ import annotations

from enum import StrEnum


class SyncStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SyncStrategy(StrEnum):
    INCREMENTAL = "incremental"
    FULL = "full"
    SNAPSHOT = "snapshot"


class ConnectionStatus(StrEnum):
    CONNECTED = "connected"
    SYNCING = "syncing"
    NEEDS_RELOGIN = "needs_relogin"
    NETWORK_ERROR = "network_error"
    KARA_ERROR = "kara_error"
    STALE = "stale"
    UNKNOWN = "unknown"


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    CLOSED = "closed"


class CurrencyUnit(StrEnum):
    RIAL = "rial"
    TOMAN = "toman"


# Company-wide KPIs must come from a single report to avoid double counting.
PRIMARY_KPI_REPORT = "visitor_sale"
PROFIT_REPORT = "sale_orders"
PRODUCT_REPORT = "sale_stuffs"
MONTHLY_SALE_REPORT = "monthly_sale"
ACCOUNT_BALANCE_REPORT = "account_balance"
RECEIVABLES_AGING_REPORT = "receivables_aging"
PROFIT_LOSS_REPORT = "profit_and_loss"
# Product-level COGS / margin (Accounting LostBenefitSeparate grid)
LOST_BENEFIT_SEPARATE_REPORT = "lost_benefit_separate"
# Monthly benefit by stuff group (Accounting MonthlyStuffGroupDetailedLostBenefit)
MONTHLY_GROUP_LOST_BENEFIT_REPORT = "monthly_stuff_group_lost_benefit"

MONTH_BALANCE_KEYS: tuple[str, ...] = tuple(f"Month{i:02d}" for i in range(1, 13))
AGING_BUCKET_KEYS: tuple[str, ...] = tuple(f"M{i}" for i in range(1, 13))

# Jalali months — (internal key, Kara API field, Persian label)
JALALI_MONTHS: tuple[tuple[str, str, str], ...] = (
    ("farvardin", "FarvardinSale", "فروردین"),
    ("ordibehesht", "OrdibeheshtSale", "اردیبهشت"),
    ("khordad", "KhordadSale", "خرداد"),
    ("tir", "TirSale", "تیر"),
    ("mordad", "MordadSale", "مرداد"),
    ("shahrivar", "ShahrivarSale", "شهریور"),
    ("mehr", "MehrSale", "مهر"),
    ("aban", "AbanSale", "آبان"),
    ("azar", "AzarSale", "آذر"),
    ("dey", "DeySale", "دی"),
    ("bahman", "BahmanSale", "بهمن"),
    ("esfand", "EsfandSale", "اسفند"),
)

REPORT_BASED_ON_DEFAULT = (
    "Inserted|Confirmed|Total|Shipment|ConfirmedShipment|"
    "TotalReversion|WaitingForAccountingConfirm|Final|"
)

# Kara ReportBasedOn values for pre-order / invoice workflow status.
PRE_ORDER_STATUS_OPTIONS: tuple[tuple[str, str], ...] = (
    ("", "همه وضعیت‌ها"),
    ("Inserted", "ثبت شده"),
    ("Confirmed", "تایید شده"),
    ("Total", "سرجمع"),
    ("Shipment", "حمل و نقل"),
    ("ConfirmedShipment", "حمل و نقل تایید شده"),
    ("TotalReversion", "کاملا مرجوعی"),
    ("WaitingForAccountingConfirm", "منتظر تایید مالی"),
    ("Final", "نهایی"),
)

PRE_ORDER_STATUS_LABELS: dict[str, str] = dict(PRE_ORDER_STATUS_OPTIONS[1:])

USER_AGENT_DEFAULT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/149.0.0.0 Safari/537.36"
)

class KaraRole(StrEnum):
    SYSTEM_ADMIN = "system_admin"
    EXECUTIVE_MANAGER = "executive_manager"
    SALES_MANAGER = "sales_manager"
    SALES_SUPERVISOR = "sales_supervisor"
    SALESPERSON = "salesperson"
    VIEWER = "viewer"
    TV_DISPLAY = "tv_display"


class DataCapabilityStatus(StrEnum):
    AVAILABLE = "available"
    PARTIALLY_AVAILABLE = "partially_available"
    API_NOT_DISCOVERED = "api_not_discovered"
    DATA_NOT_SUFFICIENT = "data_not_sufficient"
    BLOCKED_BY_BUSINESS = "blocked_by_business"


class ProfitabilityStatus(StrEnum):
    """Whether gross profit / margin can be shown honestly in UI."""

    AVAILABLE = "available"
    API_NOT_DISCOVERED = "api_not_discovered"
    DATA_NOT_SUFFICIENT = "data_not_sufficient"


# Feature flags — disabled until API discovery completes (see DOCS/KARA_API_DISCOVERY_BACKLOG.md)
# Override profitability via KARA_FEATURE_PROFITABILITY env in settings.
FEATURE_FLAGS: dict[str, bool] = {
    "profitability": False,
    "targets": False,
    "receivables": True,
    "geo_map": False,
    "personal_panel": False,
    "interactive_dashboard_filters": False,
}


def apply_feature_flags_from_settings() -> None:
    """Called from AppConfig.ready when Django settings are loaded."""
    try:
        from django.conf import settings

        if getattr(settings, "KARA_FEATURE_PROFITABILITY", False):
            FEATURE_FLAGS["profitability"] = True
    except Exception:
        pass


CONNECTION_STATUS_LABELS = {
    ConnectionStatus.CONNECTED: "متصل",
    ConnectionStatus.SYNCING: "در حال همگام‌سازی",
    ConnectionStatus.NEEDS_RELOGIN: "نیازمند ورود مجدد",
    ConnectionStatus.NETWORK_ERROR: "خطای شبکه",
    ConnectionStatus.KARA_ERROR: "خطای کارا",
    ConnectionStatus.STALE: "اطلاعات قدیمی",
    ConnectionStatus.UNKNOWN: "نامشخص",
}

SYNC_STATUS_LABELS = {
    SyncStatus.PENDING: "در انتظار",
    SyncStatus.RUNNING: "در حال اجرا",
    SyncStatus.SUCCESS: "موفق",
    SyncStatus.PARTIAL: "ناقص",
    SyncStatus.FAILED: "ناموفق",
    SyncStatus.CANCELLED: "لغو شده",
}

SYNC_TRIGGER_LABELS = {
    "manual": "دستی",
    "auto": "خودکار",
    "scheduler": "زمان‌بند",
    "test": "تست",
    "backfill": "پر کردن تاریخی",
    "cli": "خط فرمان",
    "command": "خط فرمان",
}

ALERT_SEVERITY_LABELS = {
    AlertSeverity.INFO: "اطلاع",
    AlertSeverity.WARNING: "هشدار",
    AlertSeverity.CRITICAL: "بحرانی",
}

ALERT_STATUS_LABELS = {
    AlertStatus.OPEN: "باز",
    AlertStatus.ACKNOWLEDGED: "تأییدشده",
    AlertStatus.CLOSED: "بسته",
}

KARA_ROLE_LABELS = {
    KaraRole.SYSTEM_ADMIN: "مدیر سیستم",
    KaraRole.EXECUTIVE_MANAGER: "مدیر ارشد",
    KaraRole.SALES_MANAGER: "مدیر فروش",
    KaraRole.SALES_SUPERVISOR: "سرپرست فروش",
    KaraRole.SALESPERSON: "ویزیتور",
    KaraRole.VIEWER: "بازدیدکننده",
    KaraRole.TV_DISPLAY: "نمایش سالن",
}

# Default analytics period: full local history / latest full snapshot.
DEFAULT_PERIOD_PRESET = "all"

PERIOD_PRESET_LABELS = {
    "all": "کل داده‌ها",
    "today": "امروز",
    "yesterday": "دیروز",
    "current_week": "هفته جاری",
    "previous_week": "هفته قبل",
    "current_month": "ماه جاری",
    "previous_month": "ماه قبل",
    "last_7_days": "۷ روز اخیر",
    "last_30_days": "۳۰ روز اخیر",
}

AGING_BUCKET_LABELS = {
    "M1": "ماه ۱",
    "M2": "ماه ۲",
    "M3": "ماه ۳",
    "M4": "ماه ۴",
    "M5": "ماه ۵",
    "M6": "ماه ۶",
    "M7": "ماه ۷",
    "M8": "ماه ۸",
    "M9": "ماه ۹",
    "M10": "ماه ۱۰",
    "M11": "ماه ۱۱",
    "M12": "ماه ۱۲",
}
