"""Message formatters for Bale bot."""

from __future__ import annotations

from django.contrib.auth.models import User

from reports.models import BaleUserIdentity, SaleOrderSnapshot
from reports.services.access_control import AccessControlService
from reports.services.analytics import AnalyticsService
from reports.services.currency import format_money
from reports.services.dates import format_jalali_datetime
from reports.services.display import role_label
from reports.bot.services.customers import BotCustomerService, CustomerSummary
from reports.bot.services.invoices import BotInvoiceService
from reports.bot.services.notifications import BotNotificationService
from reports.bot.services.performance import BotPerformanceService
from reports.bot.services.scope import is_supervisor, scope_label_suffix
from reports.bot.services.settlement import BotSettlementService, SettlementPartnerRow
from reports.bot.services.team import BotTeamService
from reports.models import BotUserNotification


def _user_display_name(user: User) -> str:
    identity = AccessControlService.get_identity(user)
    name = user.get_full_name().strip() or user.get_username()
    return name


def _sep() -> str:
    return "━━━━━━━━━━━━━━━━"


def welcome_message() -> str:
    return (
        "👋 به سامانه پخش مارکت خوش آمدید\n\n"
        "از طریق این ربات می‌توانید فاکتورها، گزارش فروش و اطلاعات کاری خود را "
        "سریع و ساده مشاهده کنید.\n\n"
        "🔐 برای ورود، کد پرسنلی خود را وارد کنید."
    )


def personnel_code_prompt(code: str) -> str:
    return (
        f"👤 کد پرسنلی: {code}\n\n"
        "🔐 اکنون رمز عبور خود را وارد کنید."
    )


def login_success_message(user: User) -> str:
    identity = AccessControlService.get_identity(user)
    role = role_label(identity.role) if identity else "ویزیتور"
    connection = AnalyticsService.connection_status()
    sync_label = connection.get("last_sync_label") or "—"
    return (
        "✅ ورود موفق\n\n"
        f"👤 {_user_display_name(user)}\n"
        f"💼 {role}\n\n"
        f"🕒 آخرین بروزرسانی اطلاعات:\n{sync_label}\n\n"
        "از منوی زیر بخش موردنظر را انتخاب کنید."
    )


def main_menu_message(user: User) -> str:
    identity = AccessControlService.get_identity(user)
    role = role_label(identity.role) if identity else "ویزیتور"
    connection = AnalyticsService.connection_status()
    sync_label = connection.get("last_sync_label") or "—"
    if is_supervisor(user):
        overview = BotTeamService.overview(user)
        team_hint = (
            f"👥 تیم: {overview.get('team_size', 0)} ویزیتور"
            f" ({overview.get('active_count', 0)} فعال)\n"
            if overview.get("has_data")
            else ""
        )
        return (
            "📊 پنل سرپرست فروش\n\n"
            f"👤 {_user_display_name(user)}\n"
            f"💼 {role}\n\n"
            f"{team_hint}"
            "از این بخش می‌توانید عملکرد تیم، فاکتورها و مطالبات را مشاهده کنید.\n\n"
            f"🕒 بروزرسانی اطلاعات:\n{sync_label}"
        )
    return (
        "📊 پنل شخصی ویزیتور\n\n"
        f"👤 {_user_display_name(user)}\n"
        f"💼 {role}\n\n"
        "از این بخش می‌توانید فاکتورها و اطلاعات کاری خود را مشاهده کنید.\n\n"
        f"🕒 بروزرسانی اطلاعات:\n{sync_label}"
    )


def performance_message(user: User) -> str:
    data = BotPerformanceService.snapshot(user)
    if data.get("mode") == "supervisor":
        lines = ["📊 گزارش تیم", _sep(), ""]
        if not data.get("has_data"):
            lines.append("— اطلاعات کافی موجود نیست")
            return "\n".join(lines)

        lines.append(f"🏆 رتبه شرکت: {data.get('company_rank', '—')}")
        lines.append(
            f"👥 تیم: {data.get('team_size', 0)} نفر"
            f" ({data.get('active_count', 0)} فعال)"
        )
        if data.get("total_sale"):
            lines.append(f"💰 فروش کل تیم: {data['total_sale']}")
        if data.get("avg_per_person"):
            lines.append(f"📊 میانگین هر نفر: {data['avg_per_person']}")

        lines.extend(["", "📅 امروز"])
        lines.append(f"   🧾 فاکتور: {data.get('today_orders', 0)}")
        lines.append(f"   💰 فروش: {data.get('today_sale') or '—'}")

        lines.extend(["", "📈 این ماه"])
        lines.append(f"   💰 فروش: {data.get('month_sale') or '—'}")
        lines.append(f"   🧾 فاکتور: {data.get('month_orders') or 0}")

        if data.get("total_invoices") is not None:
            lines.extend(["", "📋 کل دوره"])
            lines.append(f"   🧾 کل فاکتورهای تیم: {data['total_invoices']}")

        if data.get("settlement_remainder") or data.get("total_outstanding"):
            lines.extend(["", "💳 مطالبات تیم"])
            if data.get("settlement_remainder"):
                lines.append(f"   📌 مانده تسویه: {data['settlement_remainder']}")
            if data.get("total_outstanding"):
                lines.append(f"   ⏳ معوقات: {data['total_outstanding']}")

        lines.extend(["", _sep(), f"🕒 بروزرسانی: {data.get('sync_label', '—')}"])
        return "\n".join(lines)

    lines = ["📊 گزارش من", _sep(), ""]
    if not data.get("has_data"):
        lines.append("— اطلاعات کافی موجود نیست")
        return "\n".join(lines)

    lines.append("📅 امروز")
    lines.append(f"   🧾 فاکتور: {data.get('today_orders', 0)}")
    if data.get("today_sale"):
        lines.append(f"   💰 فروش: {data['today_sale']}")
    else:
        lines.append("   💰 فروش: —")

    lines.extend(["", "📈 این ماه"])
    if data.get("month_sale"):
        lines.append(f"   💰 فروش: {data['month_sale']}")
    else:
        lines.append("   💰 فروش: —")
    lines.append(f"   🧾 فاکتور: {data.get('month_orders') or 0}")
    if data.get("avg_order_value"):
        lines.append(f"   📊 میانگین فاکتور: {data['avg_order_value']}")

    lines.extend(["", "📋 کل دوره"])
    if data.get("total_invoices") is not None:
        lines.append(f"   🧾 کل فاکتورها: {data['total_invoices']}")
    if data.get("customer_count") is not None:
        lines.append(f"   👥 مشتریان: {data['customer_count']}")
    if data.get("active_days") is not None:
        lines.append(f"   📆 روزهای فعال: {data['active_days']}")

    if data.get("settlement_remainder") or data.get("total_outstanding"):
        lines.extend(["", "💳 مطالبات"])
        if data.get("settlement_remainder"):
            lines.append(f"   📌 مانده تسویه: {data['settlement_remainder']}")
        if data.get("total_outstanding"):
            lines.append(f"   ⏳ معوقات: {data['total_outstanding']}")

    lines.extend(["", _sep(), f"🕒 بروزرسانی: {data.get('sync_label', '—')}"])
    return "\n".join(lines)


def invoices_list_message(user: User, page: int, pages: int) -> str:
    agg = BotInvoiceService.aggregate(user)
    connection = AnalyticsService.connection_status()
    sync_label = connection.get("last_sync_label") or "—"
    suffix = scope_label_suffix(user)
    if agg["count"] == 0:
        return f"🧾 هنوز فاکتوری برای {suffix} ثبت نشده است."
    page_hint = f"صفحه {page} از {pages}\n\n" if pages > 1 else ""
    return (
        f"🧾 فاکتورهای {suffix}\n"
        f"{_sep()}\n\n"
        f"{page_hint}"
        f"📊 تعداد کل: {agg['count']}\n"
        f"💰 مجموع فروش: {format_money(agg['amount'])}\n"
        f"🕒 بروزرسانی: {sync_label}\n\n"
        "👇 برای مشاهده جزئیات، فاکتور را انتخاب کنید"
    )


def invoice_detail_message(order: SaleOrderSnapshot, user: User | None = None) -> str:
    summary = BotInvoiceService.to_summary(order)
    extra = BotInvoiceService.extra_fields(order)
    updated = format_jalali_datetime(order.last_seen_at, with_seconds=False) or "—"

    lines = [
        f"🧾 فاکتور #{summary.order_code}",
        _sep(),
        "",
        f"👤 {summary.partner_name}",
    ]
    if summary.partner_code and summary.partner_code != "—":
        lines.append(f"   🆔 کد مشتری: {summary.partner_code}")
    if extra.get("partner_groups"):
        lines.append(f"   🏷 {extra['partner_groups']}")

    lines.extend(["", f"📅 تاریخ: {summary.order_date}"])
    if summary.order_pre_code and summary.order_pre_code != "—":
        lines.append(f"📋 پیش‌فاکتور: {summary.order_pre_code}")
    if summary.items_count:
        lines.append(f"📦 تعداد اقلام: {summary.items_count:,}")

    lines.extend(["", "💰 مبلغ نهایی", f"   {summary.amount_label}"])
    if summary.reversion_label:
        lines.append(f"↩️ برگشت از فروش: {summary.reversion_label}")

    lines.extend(["", f"📌 وضعیت: {summary.status_label}"])

    if user and order.partner_code:
        outstanding = BotSettlementService.partner_outstanding(user, order.partner_code)
        if outstanding and outstanding > 0:
            lines.extend(["", f"💳 مانده معوق: {format_money(outstanding)}"])

    preview_items = BotInvoiceService.line_items_from_order(order)[:3]
    if preview_items:
        lines.extend(["", "📄 اقلام (خلاصه)"])
        for item in preview_items:
            unit = f" {item['unit']}" if item.get("unit") else ""
            lines.append(f"   • {item['name']}")
            lines.append(f"     {item['quantity']}{unit} — {item['amount']}")
        total_items = len(BotInvoiceService.line_items_from_order(order))
        if total_items > 3:
            lines.append(f"   … و {total_items - 3} قلم دیگر")

    lines.extend(["", _sep(), f"🕒 بروزرسانی: {updated}"])
    return "\n".join(lines)


def invoice_items_message(
    order: SaleOrderSnapshot, page: int = 1, pages: int = 1, total: int = 0
) -> str:
    items, page, pages, total = BotInvoiceService.line_items_page(order, page)
    summary = BotInvoiceService.to_summary(order)

    if not total:
        breakdown = BotInvoiceService.financial_breakdown(order)
        lines = [
            f"📄 فاکتور #{summary.order_code}",
            _sep(),
            "",
        ]
        if summary.items_count:
            lines.append(f"📦 تعداد کل اقلام: {summary.items_count:,}")
            lines.append("")
        if breakdown:
            lines.append("💰 خلاصه مالی فاکتور")
            for row in breakdown:
                lines.append(f"   {row['label']}: {row['value']}")
            lines.extend(
                [
                    "",
                    "ℹ️ برای مشاهده نام هر کالا، گزارش «فاکتور با ریز اقلام» را sync کنید:",
                    "   python manage.py kara_sync --report sale_orders_with_stuffs",
                ]
            )
        else:
            lines.append("— اطلاعات مالی تکمیلی برای این فاکتور موجود نیست.")
            lines.append("پس از sync بعدی، خلاصه مالی نمایش داده می‌شود.")
        lines.extend(["", _sep(), f"💰 مبلغ نهایی: {summary.amount_label}"])
        return "\n".join(lines)

    page_hint = f"صفحه {page} از {pages}  •  {total} قلم\n\n" if pages > 1 else f"{total} قلم\n\n"
    lines = [
        f"📄 اقلام فاکتور #{summary.order_code}",
        _sep(),
        "",
        page_hint,
    ]
    for item in items:
        unit = f" {item['unit']}" if item.get("unit") else ""
        group = f" ({item['group']})" if item.get("group") else ""
        lines.append(f"{item['index']}. {item['name']}{group}")
        lines.append(f"   🔢 {item['quantity']}{unit}  •  💰 {item['amount']}")
        lines.append("")
    lines.append(_sep())
    lines.append(f"💰 مبلغ نهایی: {summary.amount_label}")
    return "\n".join(lines)


def settlement_overview_message(user: User) -> str:
    data = BotSettlementService.overview(user)
    connection = AnalyticsService.connection_status()
    sync_label = connection.get("last_sync_label") or "—"

    if not data.get("has_data"):
        return (
            "💳 وضعیت تسویه\n"
            f"{_sep()}\n\n"
            "✅ مانده معوقی برای شما ثبت نشده است.\n\n"
            f"🕒 بروزرسانی: {sync_label}"
        )

    lines = ["💳 وضعیت تسویه", _sep(), ""]
    if data.get("settlement_remainder_label"):
        lines.append(f"📌 مانده تسویه: {data['settlement_remainder_label']}")
    if data.get("total_outstanding_label"):
        lines.append(f"⏳ کل معوقات: {data['total_outstanding_label']}")
    if data.get("partner_count"):
        lines.append(f"👥 مشتریان بدهکار: {data['partner_count']}")

    buckets = data.get("top_buckets") or []
    if buckets:
        lines.extend(["", "📊 جدول سنی معوقات"])
        for bucket in buckets:
            lines.append(f"   {bucket['label']}: {bucket['amount']}")

    lines.extend(["", _sep(), f"🕒 بروزرسانی: {sync_label}", "", "👇 برای جزئیات مشتری را انتخاب کنید"])
    return "\n".join(lines)


def settlement_partner_message(row: SettlementPartnerRow) -> str:
    lines = [
        f"💳 {row.partner_name}",
        _sep(),
        "",
        f"🆔 کد: {row.partner_code}",
    ]
    if row.city_name:
        lines.append(f"📍 شهر: {row.city_name}")
    lines.extend(["", f"⏳ مانده معوق: {format_money(row.total_outstanding)}"])

    buckets = row.bucket_amounts or {}
    nonzero = [
        (k, v) for k, v in buckets.items() if v and str(v) not in ("0", "0.0")
    ]
    if nonzero:
        from reports.constants import AGING_BUCKET_LABELS

        lines.extend(["", "📊 سنی معوقات"])
        for key, amount in nonzero[:6]:
            label = AGING_BUCKET_LABELS.get(key, key)
            lines.append(f"   {label}: {format_money(amount)}")
    return "\n".join(lines)


def settlement_list_message(page: int, pages: int) -> str:
    page_hint = f"صفحه {page} از {pages}\n\n" if pages > 1 else ""
    return (
        "💳 مشتریان دارای معوقه\n"
        f"{_sep()}\n\n"
        f"{page_hint}"
        "👇 مشتری را برای مشاهده جزئیات انتخاب کنید"
    )


def customers_overview_message(user: User, page: int, pages: int) -> str:
    overview = BotCustomerService.overview(user)
    connection = AnalyticsService.connection_status()
    sync_label = connection.get("last_sync_label") or "—"
    suffix = scope_label_suffix(user)

    if not overview.get("has_data"):
        return f"👥 هنوز مشتری‌ای برای {suffix} ثبت نشده است."

    page_hint = f"صفحه {page} از {pages}\n\n" if pages > 1 else ""
    return (
        f"👥 مشتریان {suffix}\n"
        f"{_sep()}\n\n"
        f"{page_hint}"
        f"📊 تعداد مشتریان: {overview['customer_count']}\n"
        f"🧾 کل فاکتورها: {overview['total_orders']}\n"
        f"💰 مجموع فروش: {format_money(overview['total_sale'])}\n"
        f"🕒 بروزرسانی: {sync_label}\n\n"
        "👇 برای مشاهده پرونده مشتری، انتخاب کنید"
    )


def customer_detail_message(user: User, customer: CustomerSummary) -> str:
    recent = BotCustomerService.recent_orders(user, customer.partner_code, limit=5)
    lines = [
        f"👤 {customer.partner_name}",
        _sep(),
        "",
        f"🆔 کد: {customer.partner_code}",
        f"🧾 تعداد فاکتور: {customer.order_count}",
        f"💰 مجموع خرید: {format_money(customer.total_sale)}",
        f"📅 آخرین خرید: {customer.last_order_date}",
    ]
    if customer.outstanding and customer.outstanding > 0:
        lines.append(f"⏳ مانده معوق: {format_money(customer.outstanding)}")

    if recent:
        lines.extend(["", "🧾 آخرین فاکتورها"])
        for order in recent:
            amount = format_money(order.order_final_price)
            lines.append(f"   • #{order.order_code} — {order.order_date} — {amount}")

    return "\n".join(lines)


CATEGORY_LABELS = {
    BotUserNotification.CATEGORY_INVOICE: "فاکتور",
    BotUserNotification.CATEGORY_SYNC: "بروزرسانی",
    BotUserNotification.CATEGORY_SETTLEMENT: "تسویه",
    BotUserNotification.CATEGORY_SYSTEM: "سیستم",
}


def notifications_list_message(
    bale_user_id: int, page: int, pages: int, unread: int
) -> str:
    overview = BotNotificationService.overview(bale_user_id)
    lines = ["🔔 اعلان‌های من", _sep(), ""]

    if not overview.get("has_data"):
        lines.append("📭 صندوق اعلان خالی است")
        lines.extend(
            [
                "",
                "اعلان‌های زیر به‌صورت خودکار ارسال می‌شوند:",
                "   🧾 تغییر وضعیت فاکتور",
                "   🔄 بروزرسانی اطلاعات سیستم",
                "   💳 تغییرات مطالبات و تسویه",
            ]
        )
        return "\n".join(lines)

    if unread:
        lines.append(f"🔴 {unread} اعلان خوانده‌نشده")
    else:
        lines.append("✅ همه اعلان‌ها خوانده شده")

    by_cat = overview.get("by_category") or {}
    if by_cat:
        parts = []
        for cat, count in by_cat.items():
            label = CATEGORY_LABELS.get(cat, cat)
            parts.append(f"{label}: {count}")
        lines.append(f"📊 {'  •  '.join(parts)}")

    if pages > 1:
        lines.append(f"\nصفحه {page} از {pages}")
    lines.extend(["", "👇 برای جزئیات، اعلان را انتخاب کنید"])
    return "\n".join(lines)


def notification_detail_message(notif: BotUserNotification) -> str:
    from reports.services.dates import format_jalali_datetime

    cat_label = CATEGORY_LABELS.get(notif.category, notif.category)
    when = format_jalali_datetime(notif.created_at, with_seconds=True) or "—"
    status = "✅ خوانده شده" if notif.is_read else "🔴 جدید"

    lines = [
        f"🔔 {notif.title}",
        _sep(),
        "",
        f"📂 دسته: {cat_label}",
        f"📌 وضعیت: {status}",
        f"🕒 {when}",
        "",
        notif.body,
    ]
    return "\n".join(lines)


def profile_message(user: User, bale_identity: BaleUserIdentity | None) -> str:
    identity = AccessControlService.get_identity(user)
    personnel = identity.personnel_code if identity else "—"
    role = role_label(identity.role) if identity else "—"
    status = "فعال" if identity and identity.is_active else "غیرفعال"
    last_login = (
        format_jalali_datetime(bale_identity.last_login_at)
        if bale_identity and bale_identity.last_login_at
        else "—"
    )
    connection = AnalyticsService.connection_status()
    return (
        "👤 حساب کاربری\n\n"
        f"👤 {_user_display_name(user)}\n"
        f"🆔 کد پرسنلی: {personnel}\n"
        f"💼 {role}\n"
        f"🟢 وضعیت: {status}\n"
        f"🕒 آخرین ورود: {last_login}\n"
        f"🔄 آخرین بروزرسانی داده: {connection.get('last_sync_label', '—')}"
    )


def placeholder_message(title: str, body: str) -> str:
    return f"{title}\n\n{body}"


def help_message(user: User | None = None) -> str:
    if user and is_supervisor(user):
        return (
            "ℹ️ راهنمای ربات (سرپرست)\n\n"
            "📊 گزارش تیم\n"
            "خلاصه عملکرد فروش تیم و رتبه شرکت\n\n"
            "👥 تیم من\n"
            "لیست ویزیتورها با فروش و سهم هر نفر\n\n"
            "🧾 فاکتورهای تیم\n"
            "مشاهده فاکتورهای ثبت‌شده برای اعضای تیم\n\n"
            "🔎 جستجوی فاکتور\n"
            "پیدا کردن فاکتور با شماره یا نام مشتری\n\n"
            "🔔 اعلان‌ها\n"
            "اعلان تغییر وضعیت فاکتورهای تیم\n\n"
            "💳 وضعیت تسویه تیم\n"
            "مانده معوق و جدول سنی مشتریان تیم\n\n"
            "👥 مشتریان تیم\n"
            "لیست مشتریان، خرید و معوقات تیم"
        )
    return (
        "ℹ️ راهنمای ربات\n\n"
        "🧾 فاکتورهای من\n"
        "مشاهده فاکتورهای ثبت‌شده برای شما\n\n"
        "🔎 جستجوی فاکتور\n"
        "پیدا کردن فاکتور با شماره یا نام مشتری\n\n"
        "📊 گزارش من\n"
        "خلاصه عملکرد فروش و مطالبات\n\n"
        "🔔 اعلان‌ها\n"
        "صندوق اعلان با شمارنده خوانده‌نشده\n\n"
        "💳 وضعیت تسویه\n"
        "مانده معوق و جدول سنی مشتریان\n\n"
        "👥 مشتریان من\n"
        "لیست مشتریان، خرید و معوقات"
    )


def team_list_message(user: User, page: int, pages: int) -> str:
    overview = BotTeamService.overview(user)
    connection = AnalyticsService.connection_status()
    sync_label = connection.get("last_sync_label") or "—"
    if not overview.get("has_data"):
        return "👥 هنوز اطلاعات تیمی برای شما ثبت نشده است."

    page_hint = f"صفحه {page} از {pages}\n\n" if pages > 1 else ""
    return (
        "👥 تیم من\n"
        f"{_sep()}\n\n"
        f"{page_hint}"
        f"📊 تعداد ویزیتور: {overview['team_size']}\n"
        f"🟢 فعال: {overview['active_count']}\n"
        f"💰 فروش کل: {overview['total_sale']}\n"
        f"🏆 رتبه: {overview['company_rank']}\n"
        f"🕒 بروزرسانی: {sync_label}\n\n"
        "👇 برای مشاهده پرونده ویزیتور، انتخاب کنید"
    )


def team_member_message(user: User, visitor_code: str) -> str:
    data = BotTeamService.member_snapshot(user, visitor_code)
    if not data.get("has_data"):
        return "🔍 ویزیتور یافت نشد یا در تیم شما نیست."

    lines = [
        f"👤 {data['personnel_name']}",
        _sep(),
        "",
        f"🆔 کد: {data['personnel_code']}",
        f"📊 سهم از تیم: {data.get('team_share', 0):.1f}٪",
    ]
    if data.get("total_sale"):
        lines.append(f"💰 فروش کل: {data['total_sale']}")
    if data.get("order_count"):
        lines.append(f"🧾 تعداد فاکتور: {data['order_count']}")

    lines.extend(["", "📅 امروز"])
    lines.append(f"   🧾 فاکتور: {data.get('today_orders', 0)}")
    lines.append(f"   💰 فروش: {data.get('today_sale') or '—'}")

    lines.extend(["", "📈 این ماه"])
    lines.append(f"   💰 فروش: {data.get('month_sale') or '—'}")
    lines.append(f"   🧾 فاکتور: {data.get('month_orders') or 0}")

    if data.get("active_days") is not None:
        lines.extend(["", f"📆 روزهای فعال: {data['active_days']}"])

    lines.extend(["", _sep(), f"🕒 بروزرسانی: {data.get('sync_label', '—')}"])
    return "\n".join(lines)


def team_invoices_message(
    user: User, visitor_code: str, page: int, pages: int
) -> str:
    member = BotTeamService.get_member(user, visitor_code)
    if not member:
        return "🔍 ویزیتور یافت نشد."
    agg = BotInvoiceService.aggregate_for_visitor(user, visitor_code)
    page_hint = f"صفحه {page} از {pages}\n\n" if pages > 1 else ""
    return (
        f"🧾 فاکتورهای {member.personnel_name}\n"
        f"{_sep()}\n\n"
        f"{page_hint}"
        f"📊 تعداد: {agg['count']}\n"
        f"💰 مجموع: {format_money(agg['amount'])}\n\n"
        "👇 برای جزئیات، فاکتور را انتخاب کنید"
    )


def error_message() -> str:
    return "⚠️ دریافت اطلاعات با مشکل مواجه شد.\n\nلطفاً دوباره تلاش کنید."
