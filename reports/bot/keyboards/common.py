"""Inline keyboards for Bale bot."""

from __future__ import annotations

from telebot import types

from reports.bot.permissions import is_bot_admin
from reports.bot.services.customers import CustomerSummary
from reports.bot.services.notifications import BotNotificationService, format_badge
from reports.bot.services.scope import is_supervisor, scope_label_suffix
from reports.bot.services.settlement import SettlementPartnerRow
from reports.bot.services.team import TeamMemberSummary
from reports.models import BotUserNotification, SaleOrderSnapshot

CATEGORY_ICONS = {
    BotUserNotification.CATEGORY_INVOICE: "🧾",
    BotUserNotification.CATEGORY_SYNC: "🔄",
    BotUserNotification.CATEGORY_SETTLEMENT: "💳",
    BotUserNotification.CATEGORY_SYSTEM: "ℹ️",
}


def _row(*buttons: types.InlineKeyboardButton) -> list[types.InlineKeyboardButton]:
    return list(buttons)


def nav_row() -> list[types.InlineKeyboardButton]:
    return _row(
        types.InlineKeyboardButton("⬅️", callback_data="nav:back"),
        types.InlineKeyboardButton("🏠", callback_data="nav:home"),
        types.InlineKeyboardButton("✖️", callback_data="nav:close"),
    )


def pagination_row(callback_prefix: str, page: int, pages: int) -> list[types.InlineKeyboardButton]:
    """RTL pagination: ▶️ = previous page, ◀️ = next page."""
    if pages <= 1:
        return []
    prev_p = max(1, page - 1)
    next_p = min(pages, page + 1)
    return [
        types.InlineKeyboardButton("▶️", callback_data=f"{callback_prefix}:{prev_p}"),
        types.InlineKeyboardButton(f"{page} / {pages}", callback_data="noop"),
        types.InlineKeyboardButton("◀️", callback_data=f"{callback_prefix}:{next_p}"),
    ]


def main_menu_keyboard(user, bale_user_id: int) -> types.InlineKeyboardMarkup:
    badges = BotNotificationService.menu_badges(bale_user_id)
    suffix = scope_label_suffix(user)
    kb = types.InlineKeyboardMarkup(row_width=2)
    if is_supervisor(user):
        kb.add(
            types.InlineKeyboardButton("📊 گزارش تیم", callback_data="menu:performance"),
            types.InlineKeyboardButton("👥 تیم من", callback_data="menu:team:1"),
        )
        kb.add(
            types.InlineKeyboardButton(
                format_badge("🧾 فاکتور", badges.get("invoices", 0))
                if badges.get("invoices")
                else "🧾 فاکتورهای تیم",
                callback_data="menu:invoices:1",
            ),
            types.InlineKeyboardButton("🔎 جستجوی فاکتور", callback_data="menu:search"),
        )
        kb.add(
            types.InlineKeyboardButton(
                format_badge("💳 تسویه", badges.get("settlement", 0))
                if badges.get("settlement")
                else "💳 وضعیت تسویه تیم",
                callback_data="menu:settlement:1",
            ),
            types.InlineKeyboardButton(
                format_badge("🔔 اعلان", badges.get("notifications", 0))
                if badges.get("notifications")
                else "🔔 اعلان‌ها",
                callback_data="menu:notifications:1",
            ),
        )
        kb.add(
            types.InlineKeyboardButton("👥 مشتریان تیم", callback_data="menu:customers:1"),
            types.InlineKeyboardButton("👤 حساب کاربری", callback_data="menu:profile"),
        )
        kb.add(types.InlineKeyboardButton("ℹ️ راهنما", callback_data="menu:help"))
    else:
        kb.add(
            types.InlineKeyboardButton("📊 گزارش من", callback_data="menu:performance"),
            types.InlineKeyboardButton(
                format_badge("🧾 فاکتور", badges.get("invoices", 0))
                if badges.get("invoices")
                else "🧾 فاکتورهای من",
                callback_data="menu:invoices:1",
            ),
        )
        kb.add(
            types.InlineKeyboardButton("🔎 جستجوی فاکتور", callback_data="menu:search"),
            types.InlineKeyboardButton(
                format_badge("💳 تسویه", badges.get("settlement", 0))
                if badges.get("settlement")
                else "💳 وضعیت تسویه",
                callback_data="menu:settlement:1",
            ),
        )
        kb.add(
            types.InlineKeyboardButton(f"👥 مشتریان {suffix}", callback_data="menu:customers:1"),
            types.InlineKeyboardButton(
                format_badge("🔔 اعلان", badges.get("notifications", 0))
                if badges.get("notifications")
                else "🔔 اعلان‌ها",
                callback_data="menu:notifications:1",
            ),
        )
        kb.add(
            types.InlineKeyboardButton("👤 حساب کاربری", callback_data="menu:profile"),
            types.InlineKeyboardButton("ℹ️ راهنما", callback_data="menu:help"),
        )
    if is_bot_admin(user, bale_user_id):
        kb.add(types.InlineKeyboardButton("🛡 مدیریت ربات", callback_data="admin:home"))
    return kb


def invoices_list_keyboard(
    orders: list[SaleOrderSnapshot],
    page: int,
    pages: int,
    *,
    page_callback: str = "menu:invoices",
) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=1)
    for order in orders:
        amount = ""
        if order.order_final_price:
            from reports.services.currency import format_money

            amount = f" • {format_money(order.order_final_price)}"
        label = f"🧾 #{order.order_code} • {(order.partner_name or '—')[:22]}{amount}"
        kb.add(types.InlineKeyboardButton(label, callback_data=f"inv:view:{order.order_code}"))
    nav_buttons = pagination_row(page_callback, page, pages)
    if nav_buttons:
        kb.row(*nav_buttons)
    kb.add(types.InlineKeyboardButton("🔎 جستجوی فاکتور", callback_data="menu:search"))
    kb.row(*nav_row())
    return kb


def invoice_detail_keyboard(
    order_code: str,
    *,
    has_items: bool = False,
    items_count: int = 0,
) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=1)
    if has_items or items_count:
        if has_items:
            label = "📄 مشاهده اقلام"
            if items_count:
                label = f"📄 مشاهده اقلام ({items_count})"
        else:
            label = "📄 خلاصه مالی فاکتور"
        kb.add(
            types.InlineKeyboardButton(label, callback_data=f"inv:items:{order_code}:1")
        )
    kb.row(*nav_row())
    return kb


def invoice_items_keyboard(
    order_code: str, page: int, pages: int
) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=1)
    nav_buttons = pagination_row(f"inv:items:{order_code}", page, pages)
    if nav_buttons:
        kb.row(*nav_buttons)
    kb.add(
        types.InlineKeyboardButton(
            "🧾 بازگشت به فاکتور", callback_data=f"inv:view:{order_code}"
        )
    )
    kb.row(*nav_row())
    return kb


def search_menu_keyboard() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("🔢 شماره فاکتور", callback_data="search:number"))
    kb.add(types.InlineKeyboardButton("👤 نام مشتری", callback_data="search:customer"))
    kb.row(*nav_row())
    return kb


def profile_keyboard(bale_user_id: int) -> types.InlineKeyboardMarkup:
    unread = BotNotificationService.unread_count(bale_user_id)
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(
            format_badge("🔔 اعلان‌ها", unread) if unread else "🔔 اعلان‌های من",
            callback_data="menu:notifications:1",
        )
    )
    kb.add(types.InlineKeyboardButton("🔐 خروج از حساب", callback_data="auth:logout"))
    kb.row(*nav_row())
    return kb


def logout_confirm_keyboard() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✅ خروج", callback_data="auth:logout:confirm"),
        types.InlineKeyboardButton("↩️ انصراف", callback_data="auth:logout:cancel"),
    )
    return kb


def performance_keyboard(user=None) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    if user and is_supervisor(user):
        kb.add(
            types.InlineKeyboardButton("👥 تیم من", callback_data="menu:team:1"),
            types.InlineKeyboardButton("💳 وضعیت تسویه تیم", callback_data="menu:settlement:1"),
        )
    else:
        kb.add(
            types.InlineKeyboardButton("👥 مشتریان من", callback_data="menu:customers:1"),
            types.InlineKeyboardButton("💳 وضعیت تسویه", callback_data="menu:settlement:1"),
        )
    kb.row(*nav_row())
    return kb


def subpage_keyboard() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.row(*nav_row())
    return kb


def settlement_keyboard(page: int, pages: int, partners: list[SettlementPartnerRow]) -> types.InlineKeyboardMarkup:
    from reports.services.currency import format_money

    kb = types.InlineKeyboardMarkup(row_width=1)
    for row in partners:
        label = f"💳 {(row.partner_name or '—')[:22]} • {format_money(row.total_outstanding)}"
        kb.add(
            types.InlineKeyboardButton(
                label, callback_data=f"stl:view:{row.partner_code}"
            )
        )
    nav_buttons = pagination_row("menu:settlement", page, pages)
    if nav_buttons:
        kb.row(*nav_buttons)
    kb.row(*nav_row())
    return kb


def settlement_partner_keyboard(partner_code: str) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(
            "👤 پرونده مشتری", callback_data=f"cust:view:{partner_code}"
        )
    )
    kb.add(
        types.InlineKeyboardButton(
            "📋 لیست معوقات", callback_data="menu:settlement:1"
        )
    )
    kb.row(*nav_row())
    return kb


def customers_list_keyboard(
    customers: list[CustomerSummary], page: int, pages: int
) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=1)
    for customer in customers:
        debt = ""
        if customer.outstanding and customer.outstanding > 0:
            debt = " ⏳"
        label = f"👤 {customer.partner_name[:24]} • {customer.order_count} فاکتور{debt}"
        kb.add(
            types.InlineKeyboardButton(
                label, callback_data=f"cust:view:{customer.partner_code}"
            )
        )
    nav_buttons = pagination_row("menu:customers", page, pages)
    if nav_buttons:
        kb.row(*nav_buttons)
    kb.row(*nav_row())
    return kb


def customer_detail_keyboard(partner_code: str, partner_name: str) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(
            "🧾 فاکتورهای این مشتری",
            callback_data=f"cust:invoices:{partner_code}",
        )
    )
    if partner_code:
        kb.add(
            types.InlineKeyboardButton(
                "💳 وضعیت معوقه",
                callback_data=f"stl:view:{partner_code}",
            )
        )
    kb.add(types.InlineKeyboardButton("📋 لیست مشتریان", callback_data="menu:customers:1"))
    kb.row(*nav_row())
    return kb


def admin_home_keyboard() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("👥 کاربران", callback_data="admin:users"),
        types.InlineKeyboardButton("📊 آمار ربات", callback_data="admin:stats"),
    )
    kb.add(
        types.InlineKeyboardButton("🚫 مسدودها", callback_data="admin:blocked"),
        types.InlineKeyboardButton("🔐 ورودها", callback_data="admin:logins"),
    )
    kb.add(
        types.InlineKeyboardButton("🔔 اعلان‌ها", callback_data="admin:notifications"),
        types.InlineKeyboardButton("🔄 وضعیت Sync", callback_data="admin:sync"),
    )
    kb.add(
        types.InlineKeyboardButton("📜 فعالیت‌ها", callback_data="admin:activity"),
        types.InlineKeyboardButton("⚙️ تنظیمات", callback_data="admin:settings"),
    )
    kb.row(*nav_row())
    return kb


def admin_user_keyboard(bale_user_id: int, *, is_blocked: bool) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=1)
    if is_blocked:
        kb.add(
            types.InlineKeyboardButton(
                "🔓 رفع مسدودی", callback_data=f"admin:unblock:{bale_user_id}"
            )
        )
    else:
        kb.add(
            types.InlineKeyboardButton(
                "🚫 مسدود کردن", callback_data=f"admin:block:{bale_user_id}"
            )
        )
    kb.add(
        types.InlineKeyboardButton(
            "🔄 قطع اتصال بله", callback_data=f"admin:disconnect:{bale_user_id}"
        )
    )
    kb.add(types.InlineKeyboardButton("⬅️ بازگشت", callback_data="admin:users"))
    return kb


def notification_invoice_button(order_code: str) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton(
            "🧾 مشاهده فاکتور", callback_data=f"inv:view:{order_code}"
        )
    )
    return kb


def notification_sync_button(report_key: str) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    if report_key in ("sale_orders",):
        kb.add(types.InlineKeyboardButton("🧾 فاکتورها", callback_data="menu:invoices:1"))
    elif report_key == "receivables_aging":
        kb.add(types.InlineKeyboardButton("💳 تسویه", callback_data="menu:settlement:1"))
    else:
        kb.add(types.InlineKeyboardButton("📊 گزارش من", callback_data="menu:performance"))
    kb.add(types.InlineKeyboardButton("🔔 صندوق اعلان", callback_data="menu:notifications:1"))
    return kb


def notifications_list_keyboard(
    items: list,
    page: int,
    pages: int,
    unread: int,
) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=1)
    for notif in items:
        icon = CATEGORY_ICONS.get(notif.category, "🔔")
        dot = "🔴" if not notif.is_read else "⚪"
        title = (notif.title or "اعلان")[:28]
        kb.add(
            types.InlineKeyboardButton(
                f"{dot} {icon} {title}",
                callback_data=f"notif:view:{notif.id}",
            )
        )
    nav_buttons = pagination_row("menu:notifications", page, pages)
    if nav_buttons:
        kb.row(*nav_buttons)
    if unread:
        kb.add(types.InlineKeyboardButton("✅ خواندن همه", callback_data="notif:read_all"))
    kb.row(*nav_row())
    return kb


def notification_detail_keyboard(notif: BotUserNotification) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=1)
    if notif.entity_type == "invoice" and notif.entity_code:
        kb.add(
            types.InlineKeyboardButton(
                "🧾 مشاهده فاکتور",
                callback_data=f"inv:view:{notif.entity_code}",
            )
        )
    elif notif.entity_type == "sync":
        key = notif.entity_code or (notif.metadata or {}).get("report_key", "")
        if key == "receivables_aging":
            kb.add(
                types.InlineKeyboardButton("💳 وضعیت تسویه", callback_data="menu:settlement:1")
            )
        elif key == "sale_orders":
            kb.add(
                types.InlineKeyboardButton("🧾 فاکتورها", callback_data="menu:invoices:1")
            )
        else:
            kb.add(types.InlineKeyboardButton("📊 گزارش من", callback_data="menu:performance"))
    kb.add(types.InlineKeyboardButton("📋 لیست اعلان‌ها", callback_data="menu:notifications:1"))
    kb.row(*nav_row())
    return kb


def team_list_keyboard(
    members: list[TeamMemberSummary], page: int, pages: int
) -> types.InlineKeyboardMarkup:
    from reports.services.currency import format_money

    kb = types.InlineKeyboardMarkup(row_width=1)
    for member in members:
        sale = format_money(member.total_sale) if member.total_sale else "—"
        label = f"👤 {member.personnel_name[:20]} • {sale}"
        kb.add(
            types.InlineKeyboardButton(
                label, callback_data=f"team:view:{member.personnel_code}"
            )
        )
    nav_buttons = pagination_row("menu:team", page, pages)
    if nav_buttons:
        kb.row(*nav_buttons)
    kb.row(*nav_row())
    return kb


def team_member_keyboard(visitor_code: str) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(
            "🧾 فاکتورهای این ویزیتور",
            callback_data=f"team:invoices:{visitor_code}:1",
        )
    )
    kb.add(types.InlineKeyboardButton("👥 لیست تیم", callback_data="menu:team:1"))
    kb.row(*nav_row())
    return kb


def team_invoices_keyboard(
    visitor_code: str,
    orders: list[SaleOrderSnapshot],
    page: int,
    pages: int,
) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=1)
    for order in orders:
        amount = ""
        if order.order_final_price:
            from reports.services.currency import format_money

            amount = f" • {format_money(order.order_final_price)}"
        label = f"🧾 #{order.order_code} • {(order.partner_name or '—')[:22]}{amount}"
        kb.add(types.InlineKeyboardButton(label, callback_data=f"inv:view:{order.order_code}"))
    nav_buttons = pagination_row(f"team:invoices:{visitor_code}", page, pages)
    if nav_buttons:
        kb.row(*nav_buttons)
    kb.add(
        types.InlineKeyboardButton(
            "👤 پرونده ویزیتور", callback_data=f"team:view:{visitor_code}"
        )
    )
    kb.row(*nav_row())
    return kb
