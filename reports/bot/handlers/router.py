"""Register telebot handlers."""

from __future__ import annotations

import logging

from django.contrib.auth.models import User
from telebot import TeleBot, types

from reports.bot import states
from reports.bot.formatters import messages as fmt
from reports.bot.keyboards import common as kb
from reports.bot.permissions import is_bot_admin
from reports.bot.services.activity import log_activity
from reports.bot.services.admin_panel import BotAdminService
from reports.bot.services.auth import AuthError, BlockedError, BotAuthService, LockedError
from reports.bot.services.customers import BotCustomerService
from reports.bot.services.invoices import BotInvoiceService
from reports.bot.services.navigation import BotNavigationService
from reports.bot.services.notifications import BotNotificationService
from reports.bot.services.settlement import BotSettlementService
from reports.bot.services.team import BotTeamService
from reports.bot.django_support import ensure_django_connection

logger = logging.getLogger(__name__)


class BotRouter:
    def __init__(self, bot: TeleBot) -> None:
        self.bot = bot
        self._register()

    def _uid(self, message: types.Message) -> int:
        return message.from_user.id

    def _require_user(self, bale_user_id: int) -> User | None:
        user = BotAuthService.get_linked_user(bale_user_id)
        if not user:
            return None
        return user

    def _edit_or_send(
        self,
        chat_id: int,
        message_id: int | None,
        text: str,
        markup: types.InlineKeyboardMarkup | None = None,
    ) -> types.Message:
        if message_id:
            try:
                self.bot.edit_message_text(
                    text,
                    chat_id,
                    message_id,
                    reply_markup=markup,
                )
                return types.Message(
                    message_id=message_id,
                    from_user=None,
                    date=0,
                    chat=types.Chat(id=chat_id, type="private"),
                    content_type="text",
                    options={},
                    json_string="",
                )
            except Exception as exc:
                err = str(exc).lower()
                if markup and ("not modified" in err or "same" in err):
                    try:
                        self.bot.edit_message_reply_markup(
                            chat_id, message_id, reply_markup=markup
                        )
                        return types.Message(
                            message_id=message_id,
                            from_user=None,
                            date=0,
                            chat=types.Chat(id=chat_id, type="private"),
                            content_type="text",
                            options={},
                            json_string="",
                        )
                    except Exception:
                        pass
                logger.warning("edit_message failed (%s), sending new message", exc)
        msg = self.bot.send_message(chat_id, text, reply_markup=markup)
        return msg

    def _show_main(self, bale_user_id: int, chat_id: int, message_id: int | None) -> None:
        user = self._require_user(bale_user_id)
        if not user:
            self._prompt_login(chat_id, message_id, bale_user_id)
            return
        BotNavigationService.reset_to_main(bale_user_id)
        text = fmt.main_menu_message(user)
        markup = kb.main_menu_keyboard(user, bale_user_id)
        msg = self._edit_or_send(chat_id, message_id, text, markup)
        BotNavigationService.set_menu_message(bale_user_id, chat_id, msg.message_id)

    def _prompt_login(self, chat_id: int, message_id: int | None, bale_user_id: int) -> None:
        BotNavigationService.set_flow(bale_user_id, states.WAITING_PERSONNEL_CODE)
        BotNavigationService.update_context(bale_user_id, personnel_code="")
        self._edit_or_send(chat_id, message_id, fmt.welcome_message())

    def _register(self) -> None:
        @self.bot.message_handler(commands=["start", "menu"])
        @ensure_django_connection
        def cmd_start(message: types.Message) -> None:
            uid = self._uid(message)
            try:
                BotAuthService.ensure_not_locked(uid)
            except BlockedError:
                self.bot.send_message(message.chat.id, "🚫 حساب شما مسدود شده است.")
                return
            except LockedError:
                self.bot.send_message(
                    message.chat.id, "🔒 به دلیل تلاش‌های ناموفق، موقتاً قفل شده‌اید."
                )
                return
            user = BotAuthService.get_linked_user(uid)
            if user:
                self._show_main(uid, message.chat.id, None)
            else:
                self._prompt_login(message.chat.id, None, uid)

        @self.bot.message_handler(commands=["help"])
        def cmd_help(message: types.Message) -> None:
            user = BotAuthService.get_linked_user(self._uid(message))
            self.bot.send_message(
                message.chat.id,
                fmt.help_message(user),
                reply_markup=kb.subpage_keyboard(),
            )

        @self.bot.message_handler(commands=["logout"])
        def cmd_logout(message: types.Message) -> None:
            uid = self._uid(message)
            if not BotAuthService.get_linked_user(uid):
                self.bot.send_message(message.chat.id, "شما وارد نشده‌اید.")
                return
            BotNavigationService.set_flow(uid, states.LOGOUT_CONFIRM)
            self.bot.send_message(
                message.chat.id,
                "🔐 خروج از حساب\n\nآیا مطمئن هستید؟",
                reply_markup=kb.logout_confirm_keyboard(),
            )

        @self.bot.message_handler(func=lambda m: True, content_types=["text"])
        @ensure_django_connection
        def on_text(message: types.Message) -> None:
            uid = self._uid(message)
            state = BotNavigationService.get_state(uid)
            flow = state.flow_state
            if flow == states.WAITING_PERSONNEL_CODE:
                try:
                    code = BotAuthService.validate_personnel_code(message.text or "")
                except BlockedError:
                    self.bot.send_message(message.chat.id, "🚫 حساب شما مسدود شده است.")
                    return
                except LockedError:
                    self.bot.send_message(
                        message.chat.id, "🔒 به دلیل تلاش‌های ناموفق، موقتاً قفل شده‌اید."
                    )
                    return
                except AuthError as exc:
                    self.bot.send_message(message.chat.id, str(exc))
                    return
                BotNavigationService.set_flow(
                    uid, states.WAITING_PASSWORD, personnel_code=code
                )
                self.bot.send_message(message.chat.id, fmt.personnel_code_prompt(code))
                return

            if flow == states.WAITING_PASSWORD:
                ctx = BotNavigationService.get_context(uid)
                personnel_code = ctx.get("personnel_code", "")
                if not personnel_code:
                    self._prompt_login(message.chat.id, None, uid)
                    return
                try:
                    user = BotAuthService.authenticate(
                        uid, personnel_code, message.text or ""
                    )
                except BlockedError:
                    self.bot.send_message(message.chat.id, "🚫 حساب شما مسدود شده است.")
                    return
                except LockedError:
                    self.bot.send_message(
                        message.chat.id, "🔒 به دلیل تلاش‌های ناموفق، موقتاً قفل شده‌اید."
                    )
                    return
                except AuthError as exc:
                    self.bot.send_message(message.chat.id, str(exc))
                    return
                BotNavigationService.clear_flow(uid)
                self.bot.send_message(message.chat.id, fmt.login_success_message(user))
                self._show_main(uid, message.chat.id, None)
                return

            user = self._require_user(uid)
            if not user:
                self._prompt_login(message.chat.id, None, uid)
                return

            if flow == states.WAITING_INVOICE_NUMBER:
                BotNavigationService.clear_flow(uid)
                order = BotInvoiceService.search_by_number(user, message.text or "")
                log_activity(
                    "INVOICE_SEARCH",
                    bale_user_id=uid,
                    user=user,
                    metadata={"type": "number"},
                )
                if not order:
                    self.bot.send_message(
                        message.chat.id,
                        "🔍 فاکتوری با این شماره در حساب شما پیدا نشد.",
                        reply_markup=kb.search_menu_keyboard(),
                    )
                    return
                self._show_invoice(uid, user, message.chat.id, None, order.order_code)
                return

            if flow == states.WAITING_CUSTOMER_NAME:
                term = message.text or ""
                BotNavigationService.update_context(uid, search_term=term, search_page=1)
                BotNavigationService.clear_flow(uid)
                log_activity(
                    "INVOICE_SEARCH",
                    bale_user_id=uid,
                    user=user,
                    metadata={"type": "customer"},
                )
                self._show_search_results(uid, user, message.chat.id, None, term, 1)
                return

        @self.bot.callback_query_handler(func=lambda c: True)
        @ensure_django_connection
        def on_callback(call: types.CallbackQuery) -> None:
            uid = call.from_user.id
            data = call.data or ""
            try:
                message = call.message
                if not message:
                    self.bot.answer_callback_query(call.id, "پیام یافت نشد.")
                    return
                chat_id = message.chat.id
                message_id = message.message_id
                try:
                    self.bot.answer_callback_query(call.id)
                except Exception:
                    pass

                logger.info("callback uid=%s data=%s", uid, data)

                if data == "noop":
                    return

                if data.startswith("nav:"):
                    self._handle_nav(uid, data, chat_id, message_id)
                    return

                user = self._require_user(uid)
                if not user and not data.startswith("auth:"):
                    self._prompt_login(chat_id, message_id, uid)
                    return

                if data.startswith("menu:"):
                    self._handle_menu(uid, user, data, chat_id, message_id)
                elif data.startswith("inv:"):
                    self._handle_invoice(uid, user, data, chat_id, message_id)
                elif data.startswith("stl:"):
                    self._handle_settlement(uid, user, data, chat_id, message_id)
                elif data.startswith("cust:"):
                    self._handle_customer(uid, user, data, chat_id, message_id)
                elif data.startswith("notif:"):
                    self._handle_notification(uid, user, data, chat_id, message_id)
                elif data.startswith("search:"):
                    self._handle_search(uid, user, data, chat_id, message_id)
                elif data.startswith("team:"):
                    self._handle_team(uid, user, data, chat_id, message_id)
                elif data.startswith("auth:"):
                    self._handle_auth(uid, user, data, chat_id, message_id)
                elif data.startswith("admin:"):
                    self._handle_admin(uid, user, data, chat_id, message_id)
            except Exception:
                logger.exception("callback failed data=%s uid=%s", data, uid)
                try:
                    self.bot.answer_callback_query(
                        call.id, "خطا در پردازش. دوباره تلاش کنید.", show_alert=True
                    )
                except Exception:
                    pass

    def _handle_nav(self, uid: int, data: str, chat_id: int, message_id: int) -> None:
        action = data.split(":", 1)[1]
        if action == "close":
            try:
                self.bot.delete_message(chat_id, message_id)
            except Exception:
                pass
            return
        if action == "home":
            self._show_main(uid, chat_id, message_id)
            return
        if action == "back":
            screen = BotNavigationService.pop_screen(uid)
            user = self._require_user(uid)
            if not user:
                self._prompt_login(chat_id, message_id, uid)
                return
            self._render_screen(uid, user, screen, chat_id, message_id)

    def _render_screen(
        self, uid: int, user: User, screen: str, chat_id: int, message_id: int
    ) -> None:
        if screen == "main":
            self._show_main(uid, chat_id, message_id)
        elif screen.startswith("invoices:"):
            page = int(screen.split(":")[-1])
            self._show_invoices(uid, user, chat_id, message_id, page)
        elif screen.startswith("settlement_partner:"):
            code = screen.split(":", 1)[1]
            row = BotSettlementService.get_partner(user, code)
            if row:
                text = fmt.settlement_partner_message(row)
                markup = kb.settlement_partner_keyboard(code)
                self._edit_or_send(chat_id, message_id, text, markup)
            else:
                self._show_settlement(uid, user, chat_id, message_id, 1)
        elif screen.startswith("invoice_items:"):
            parts = screen.split(":")
            code = parts[1] if len(parts) > 1 else ""
            page = int(parts[2]) if len(parts) > 2 else 1
            self._show_invoice_items(uid, user, chat_id, message_id, code, page)
        elif screen.startswith("invoice:"):
            code = screen.split(":", 1)[1]
            self._show_invoice(uid, user, chat_id, message_id, code)
        elif screen.startswith("settlement:"):
            page = int(screen.split(":")[-1])
            self._show_settlement(uid, user, chat_id, message_id, page)
        elif screen.startswith("customers:"):
            page = int(screen.split(":")[-1])
            self._show_customers(uid, user, chat_id, message_id, page)
        elif screen.startswith("customer:"):
            code = screen.split(":", 1)[1]
            self._show_customer_detail(uid, user, chat_id, message_id, code)
        elif screen.startswith("notifications:"):
            page = int(screen.split(":")[-1])
            self._show_notifications(uid, user, chat_id, message_id, page)
        elif screen.startswith("notification:"):
            notif_id = int(screen.split(":")[-1])
            self._show_notification_detail(uid, user, chat_id, message_id, notif_id)
        elif screen == "search":
            self._show_search_menu(uid, chat_id, message_id)
        elif screen == "performance":
            self._show_performance(uid, user, chat_id, message_id)
        elif screen == "profile":
            self._show_profile(uid, user, chat_id, message_id)
        elif screen.startswith("team:"):
            page = int(screen.split(":")[-1])
            self._show_team(uid, user, chat_id, message_id, page)
        elif screen.startswith("team_member:"):
            code = screen.split(":", 1)[1]
            self._show_team_member(uid, user, chat_id, message_id, code)
        elif screen.startswith("team_invoices:"):
            parts = screen.split(":")
            code = parts[1] if len(parts) > 1 else ""
            page = int(parts[2]) if len(parts) > 2 else 1
            self._show_team_invoices(uid, user, chat_id, message_id, code, page)
        else:
            self._show_main(uid, chat_id, message_id)

    def _handle_menu(
        self, uid: int, user: User, data: str, chat_id: int, message_id: int
    ) -> None:
        parts = data.split(":")
        action = parts[1] if len(parts) > 1 else ""
        if action == "invoices":
            page = int(parts[2]) if len(parts) > 2 else 1
            BotNavigationService.push_screen(uid, f"invoices:{page}")
            self._show_invoices(uid, user, chat_id, message_id, page)
        elif action == "performance":
            BotNavigationService.push_screen(uid, "performance")
            self._show_performance(uid, user, chat_id, message_id)
        elif action == "search":
            BotNavigationService.push_screen(uid, "search")
            self._show_search_menu(uid, chat_id, message_id)
        elif action == "settlement":
            page = int(parts[2]) if len(parts) > 2 else 1
            BotNavigationService.push_screen(uid, f"settlement:{page}")
            self._show_settlement(uid, user, chat_id, message_id, page)
        elif action == "customers":
            page = int(parts[2]) if len(parts) > 2 else 1
            BotNavigationService.push_screen(uid, f"customers:{page}")
            self._show_customers(uid, user, chat_id, message_id, page)
        elif action == "notifications":
            page = int(parts[2]) if len(parts) > 2 else 1
            BotNavigationService.push_screen(uid, f"notifications:{page}")
            self._show_notifications(uid, user, chat_id, message_id, page)
        elif action == "profile":
            BotNavigationService.push_screen(uid, "profile")
            self._show_profile(uid, user, chat_id, message_id)
        elif action == "team":
            page = int(parts[2]) if len(parts) > 2 else 1
            BotNavigationService.push_screen(uid, f"team:{page}")
            self._show_team(uid, user, chat_id, message_id, page)
        elif action == "help":
            BotNavigationService.push_screen(uid, "help")
            self._edit_or_send(
                chat_id, message_id, fmt.help_message(user), kb.subpage_keyboard()
            )
        elif action == "search_results":
            page = int(parts[2]) if len(parts) > 2 else 1
            ctx = BotNavigationService.get_context(uid)
            term = ctx.get("search_term", "")
            self._show_search_results(uid, user, chat_id, message_id, term, page)

    def _show_invoices(
        self, uid: int, user: User, chat_id: int, message_id: int, page: int
    ) -> None:
        try:
            orders, page, pages = BotInvoiceService.list_page(user, page)
            text = fmt.invoices_list_message(user, page, pages)
            if orders:
                markup = kb.invoices_list_keyboard(orders, page, pages)
            else:
                markup = kb.subpage_keyboard()
            self._edit_or_send(chat_id, message_id, text, markup)
        except Exception:
            logger.exception("invoices list failed")
            self._edit_or_send(chat_id, message_id, fmt.error_message(), kb.subpage_keyboard())

    def _show_invoice(
        self, uid: int, user: User, chat_id: int, message_id: int, order_code: str
    ) -> None:
        try:
            order = BotInvoiceService.get_order(user, order_code)
            if not order:
                self._edit_or_send(
                    chat_id,
                    message_id,
                    "🔍 فاکتوری با این شماره در حساب شما پیدا نشد.",
                    kb.subpage_keyboard(),
                )
                return
            log_activity(
                "INVOICE_VIEW",
                bale_user_id=uid,
                user=user,
                metadata={"order_code": order_code},
            )
            BotNavigationService.push_screen(uid, f"invoice:{order_code}")
            has_items = BotInvoiceService.has_line_items(order)
            items_count = len(BotInvoiceService.line_items_from_order(order)) or int(
                order.stuffs_quantity_sum or 0
            )
            text = fmt.invoice_detail_message(order, user)
            markup = kb.invoice_detail_keyboard(
                order_code, has_items=has_items, items_count=items_count
            )
            self._edit_or_send(chat_id, message_id, text, markup)
        except Exception:
            logger.exception("invoice detail failed")
            self._edit_or_send(chat_id, message_id, fmt.error_message(), kb.subpage_keyboard())

    def _handle_invoice(
        self, uid: int, user: User, data: str, chat_id: int, message_id: int
    ) -> None:
        parts = data.split(":")
        if len(parts) < 3:
            return
        action, code = parts[1], parts[2]
        if action == "view":
            self._show_invoice(uid, user, chat_id, message_id, code)
        elif action == "items":
            page = int(parts[3]) if len(parts) > 3 else 1
            self._show_invoice_items(uid, user, chat_id, message_id, code, page)

    def _show_invoice_items(
        self, uid: int, user: User, chat_id: int, message_id: int, order_code: str, page: int
    ) -> None:
        try:
            order = BotInvoiceService.get_order(user, order_code)
            if not order:
                self._edit_or_send(chat_id, message_id, fmt.error_message(), kb.subpage_keyboard())
                return
            BotNavigationService.push_screen(uid, f"invoice_items:{order_code}:{page}")
            _, page, pages, total = BotInvoiceService.line_items_page(order, page)
            text = fmt.invoice_items_message(order, page, pages, total)
            markup = kb.invoice_items_keyboard(order_code, page, pages)
            self._edit_or_send(chat_id, message_id, text, markup)
        except Exception:
            logger.exception("invoice items failed")
            self._edit_or_send(chat_id, message_id, fmt.error_message(), kb.subpage_keyboard())

    def _show_settlement(
        self, uid: int, user: User, chat_id: int, message_id: int, page: int
    ) -> None:
        try:
            overview = BotSettlementService.overview(user)
            if not overview.get("has_data"):
                text = fmt.settlement_overview_message(user)
                self._edit_or_send(chat_id, message_id, text, kb.subpage_keyboard())
                return
            partners, page, pages = BotSettlementService.list_page(user, page)
            text = fmt.settlement_overview_message(user)
            if partners:
                text = text + "\n\n" + fmt.settlement_list_message(page, pages)
                markup = kb.settlement_keyboard(page, pages, partners)
            else:
                markup = kb.subpage_keyboard()
            self._edit_or_send(chat_id, message_id, text, markup)
        except Exception:
            logger.exception("settlement list failed")
            self._edit_or_send(chat_id, message_id, fmt.error_message(), kb.subpage_keyboard())

    def _handle_settlement(
        self, uid: int, user: User, data: str, chat_id: int, message_id: int
    ) -> None:
        parts = data.split(":")
        if len(parts) < 3 or parts[1] != "view":
            return
        partner_code = parts[2]
        row = BotSettlementService.get_partner(user, partner_code)
        if not row:
            self._edit_or_send(
                chat_id,
                message_id,
                "🔍 اطلاعات معوقه‌ای برای این مشتری یافت نشد.",
                kb.subpage_keyboard(),
            )
            return
        BotNavigationService.push_screen(uid, f"settlement_partner:{partner_code}")
        text = fmt.settlement_partner_message(row)
        markup = kb.settlement_partner_keyboard(partner_code)
        self._edit_or_send(chat_id, message_id, text, markup)

    def _show_customers(
        self, uid: int, user: User, chat_id: int, message_id: int, page: int
    ) -> None:
        try:
            customers, page, pages = BotCustomerService.list_page(user, page)
            text = fmt.customers_overview_message(user, page, pages)
            if not customers:
                self._edit_or_send(chat_id, message_id, text, kb.subpage_keyboard())
                return
            markup = kb.customers_list_keyboard(customers, page, pages)
            self._edit_or_send(chat_id, message_id, text, markup)
        except Exception:
            logger.exception("customers list failed")
            self._edit_or_send(chat_id, message_id, fmt.error_message(), kb.subpage_keyboard())

    def _show_customer_detail(
        self, uid: int, user: User, chat_id: int, message_id: int, partner_code: str
    ) -> None:
        try:
            customer = BotCustomerService.get_customer(user, partner_code)
            if not customer:
                self._edit_or_send(
                    chat_id,
                    message_id,
                    "🔍 مشتری یافت نشد.",
                    kb.subpage_keyboard(),
                )
                return
            BotNavigationService.push_screen(uid, f"customer:{partner_code}")
            text = fmt.customer_detail_message(user, customer)
            markup = kb.customer_detail_keyboard(partner_code, customer.partner_name)
            self._edit_or_send(chat_id, message_id, text, markup)
        except Exception:
            logger.exception("customer detail failed")
            self._edit_or_send(chat_id, message_id, fmt.error_message(), kb.subpage_keyboard())

    def _handle_customer(
        self, uid: int, user: User, data: str, chat_id: int, message_id: int
    ) -> None:
        parts = data.split(":")
        if len(parts) < 3:
            return
        action, partner_code = parts[1], parts[2]
        if action == "view":
            self._show_customer_detail(uid, user, chat_id, message_id, partner_code)
        elif action == "invoices":
            customer = BotCustomerService.get_customer(user, partner_code)
            if not customer:
                self._edit_or_send(chat_id, message_id, fmt.error_message(), kb.subpage_keyboard())
                return
            BotNavigationService.update_context(
                uid, search_term=customer.partner_name, search_page=1
            )
            self._show_search_results(
                uid, user, chat_id, message_id, customer.partner_name, 1
            )

    def _show_search_menu(self, uid: int, chat_id: int, message_id: int) -> None:
        self._edit_or_send(
            chat_id,
            message_id,
            "🔎 جستجوی فاکتور",
            kb.search_menu_keyboard(),
        )

    def _handle_search(
        self, uid: int, user: User, data: str, chat_id: int, message_id: int
    ) -> None:
        action = data.split(":")[1]
        if action == "number":
            BotNavigationService.set_flow(uid, states.WAITING_INVOICE_NUMBER)
            self._edit_or_send(
                chat_id,
                message_id,
                "🔢 جستجو با شماره فاکتور\n\nشماره فاکتور موردنظر را ارسال کنید.",
                kb.subpage_keyboard(),
            )
        elif action == "customer":
            BotNavigationService.set_flow(uid, states.WAITING_CUSTOMER_NAME)
            self._edit_or_send(
                chat_id,
                message_id,
                "👤 جستجو با نام مشتری\n\nنام یا بخشی از نام مشتری را ارسال کنید.",
                kb.subpage_keyboard(),
            )

    def _show_search_results(
        self, uid: int, user: User, chat_id: int, message_id: int | None, term: str, page: int
    ) -> None:
        try:
            orders, page, pages = BotInvoiceService.search_by_customer(user, term, page)
            if not orders:
                self._edit_or_send(
                    chat_id,
                    message_id,
                    "🔍 فاکتوری با این مشخصات در حساب شما پیدا نشد.",
                    kb.search_menu_keyboard(),
                )
                return
            BotNavigationService.update_context(uid, search_term=term, search_page=page)
            text = f"🔎 نتایج جستجو برای «{term}»\n\n{len(orders)} مورد در این صفحه"
            markup = kb.invoices_list_keyboard(
                orders, page, pages, page_callback="menu:search_results"
            )
            self._edit_or_send(chat_id, message_id, text, markup)
        except Exception:
            logger.exception("search failed")
            self._edit_or_send(chat_id, message_id, fmt.error_message(), kb.search_menu_keyboard())

    def _show_performance(self, uid: int, user: User, chat_id: int, message_id: int) -> None:
        try:
            text = fmt.performance_message(user)
            self._edit_or_send(chat_id, message_id, text, kb.performance_keyboard(user))
        except Exception:
            logger.exception("performance failed")
            self._edit_or_send(chat_id, message_id, fmt.error_message(), kb.subpage_keyboard())

    def _show_team(
        self, uid: int, user: User, chat_id: int, message_id: int, page: int
    ) -> None:
        try:
            members, page, pages = BotTeamService.list_page(user, page)
            text = fmt.team_list_message(user, page, pages)
            if members:
                markup = kb.team_list_keyboard(members, page, pages)
            else:
                markup = kb.subpage_keyboard()
            self._edit_or_send(chat_id, message_id, text, markup)
        except Exception:
            logger.exception("team list failed")
            self._edit_or_send(chat_id, message_id, fmt.error_message(), kb.subpage_keyboard())

    def _show_team_member(
        self, uid: int, user: User, chat_id: int, message_id: int, visitor_code: str
    ) -> None:
        try:
            member = BotTeamService.get_member(user, visitor_code)
            if not member:
                self._edit_or_send(
                    chat_id,
                    message_id,
                    "🔍 ویزیتور یافت نشد یا در تیم شما نیست.",
                    kb.subpage_keyboard(),
                )
                return
            BotNavigationService.push_screen(uid, f"team_member:{visitor_code}")
            text = fmt.team_member_message(user, visitor_code)
            markup = kb.team_member_keyboard(visitor_code)
            self._edit_or_send(chat_id, message_id, text, markup)
        except Exception:
            logger.exception("team member failed")
            self._edit_or_send(chat_id, message_id, fmt.error_message(), kb.subpage_keyboard())

    def _show_team_invoices(
        self,
        uid: int,
        user: User,
        chat_id: int,
        message_id: int,
        visitor_code: str,
        page: int,
    ) -> None:
        try:
            orders, page, pages = BotInvoiceService.list_page_for_visitor(
                user, visitor_code, page
            )
            text = fmt.team_invoices_message(user, visitor_code, page, pages)
            if orders:
                markup = kb.team_invoices_keyboard(visitor_code, orders, page, pages)
            else:
                markup = kb.team_member_keyboard(visitor_code)
            BotNavigationService.push_screen(uid, f"team_invoices:{visitor_code}:{page}")
            self._edit_or_send(chat_id, message_id, text, markup)
        except Exception:
            logger.exception("team invoices failed")
            self._edit_or_send(chat_id, message_id, fmt.error_message(), kb.subpage_keyboard())

    def _handle_team(
        self, uid: int, user: User, data: str, chat_id: int, message_id: int
    ) -> None:
        parts = data.split(":")
        if len(parts) < 3:
            return
        action, code = parts[1], parts[2]
        if action == "view":
            self._show_team_member(uid, user, chat_id, message_id, code)
        elif action == "invoices":
            page = int(parts[3]) if len(parts) > 3 else 1
            self._show_team_invoices(uid, user, chat_id, message_id, code, page)

    def _show_profile(self, uid: int, user: User, chat_id: int, message_id: int) -> None:
        from reports.models import BaleUserIdentity

        ident = BaleUserIdentity.objects.filter(bale_user_id=uid).first()
        text = fmt.profile_message(user, ident)
        self._edit_or_send(chat_id, message_id, text, kb.profile_keyboard(uid))

    def _show_notifications(
        self, uid: int, user: User, chat_id: int, message_id: int, page: int
    ) -> None:
        try:
            items, page, pages, unread = BotNotificationService.list_page(uid, page)
            text = fmt.notifications_list_message(uid, page, pages, unread)
            if items:
                markup = kb.notifications_list_keyboard(items, page, pages, unread)
            else:
                markup = kb.subpage_keyboard()
            self._edit_or_send(chat_id, message_id, text, markup)
        except Exception:
            logger.exception("notifications list failed")
            self._edit_or_send(chat_id, message_id, fmt.error_message(), kb.subpage_keyboard())

    def _show_notification_detail(
        self, uid: int, user: User, chat_id: int, message_id: int, notif_id: int
    ) -> None:
        try:
            notif = BotNotificationService.get(uid, notif_id)
            if not notif:
                self._edit_or_send(
                    chat_id,
                    message_id,
                    "🔍 اعلان یافت نشد.",
                    kb.subpage_keyboard(),
                )
                return
            BotNotificationService.mark_read(uid, notif_id)
            BotNavigationService.push_screen(uid, f"notification:{notif_id}")
            text = fmt.notification_detail_message(notif)
            markup = kb.notification_detail_keyboard(notif)
            self._edit_or_send(chat_id, message_id, text, markup)
        except Exception:
            logger.exception("notification detail failed")
            self._edit_or_send(chat_id, message_id, fmt.error_message(), kb.subpage_keyboard())

    def _handle_notification(
        self, uid: int, user: User, data: str, chat_id: int, message_id: int
    ) -> None:
        parts = data.split(":")
        action = parts[1] if len(parts) > 1 else ""
        if action == "view" and len(parts) > 2:
            notif_id = int(parts[2])
            self._show_notification_detail(uid, user, chat_id, message_id, notif_id)
        elif action == "read_all":
            BotNotificationService.mark_all_read(uid)
            self._show_notifications(uid, user, chat_id, message_id, 1)

    def _handle_auth(
        self, uid: int, user: User | None, data: str, chat_id: int, message_id: int
    ) -> None:
        if data == "auth:logout":
            BotNavigationService.set_flow(uid, states.LOGOUT_CONFIRM)
            self._edit_or_send(
                chat_id,
                message_id,
                "🔐 خروج از حساب\n\nآیا مطمئن هستید؟",
                kb.logout_confirm_keyboard(),
            )
        elif data == "auth:logout:confirm":
            BotAuthService.logout(uid)
            self._edit_or_send(chat_id, message_id, fmt.welcome_message())
        elif data == "auth:logout:cancel":
            if user:
                self._show_main(uid, chat_id, message_id)

    def _handle_admin(
        self, uid: int, user: User, data: str, chat_id: int, message_id: int
    ) -> None:
        if not is_bot_admin(user, uid):
            self._edit_or_send(chat_id, message_id, "⛔ دسترسی مجاز نیست.", kb.subpage_keyboard())
            return
        parts = data.split(":")
        action = parts[1] if len(parts) > 1 else ""
        if action == "home":
            text = "🛡 مدیریت ربات\n\nمدیریت کاربران و وضعیت ربات"
            self._edit_or_send(chat_id, message_id, text, kb.admin_home_keyboard())
        elif action == "stats":
            stats = BotAdminService.stats()
            text = (
                "📊 آمار ربات\n\n"
                f"👥 کاربران متصل: {stats['connected']}\n"
                f"🟢 کاربران فعال: {stats['active']}\n"
                f"🔐 ورودهای امروز: {stats['logins_today']}\n"
                f"❌ ورود ناموفق: {stats['failed_logins']}\n"
                f"🧾 مشاهده فاکتور: {stats['invoice_views']}\n"
                f"🔎 جستجوها: {stats['searches']}\n"
                f"🔔 اعلان ارسال‌شده: {stats['notifications']}"
            )
            self._edit_or_send(chat_id, message_id, text, kb.admin_home_keyboard())
        elif action == "users":
            users = BotAdminService.list_users()
            lines = ["👥 کاربران ربات", ""]
            buttons = []
            from telebot import types

            for ident in users:
                k = ident.user.kara_identity
                name = ident.user.get_full_name() or ident.user.username
                lines.append(f"• {name} — {k.personnel_code if k else '—'}")
                buttons.append(
                    types.InlineKeyboardButton(
                        f"👤 {name[:20]}",
                        callback_data=f"admin:user:{ident.bale_user_id}",
                    )
                )
            markup = types.InlineKeyboardMarkup(row_width=1)
            for btn in buttons[:10]:
                markup.add(btn)
            markup.row(*kb.nav_row())
            self._edit_or_send(chat_id, message_id, "\n".join(lines) or "— کاربری نیست", markup)
        elif action == "user" and len(parts) > 2:
            target_id = int(parts[2])
            from reports.models import BaleUserIdentity

            ident = BaleUserIdentity.objects.filter(bale_user_id=target_id).select_related(
                "user", "user__kara_identity"
            ).first()
            if not ident:
                self._edit_or_send(chat_id, message_id, "کاربر یافت نشد.", kb.admin_home_keyboard())
                return
            k = ident.user.kara_identity
            from reports.services.display import role_label

            text = (
                f"👤 {ident.user.get_full_name() or ident.user.username}\n\n"
                f"🆔 کد پرسنلی: {k.personnel_code if k else '—'}\n"
                f"💼 {role_label(k.role) if k else '—'}\n"
                f"{'🔴 مسدود' if ident.is_blocked else '🟢 فعال'}\n"
                f"🔗 بله: متصل\n"
                f"🕒 آخرین ورود: {ident.last_login_at or '—'}"
            )
            self._edit_or_send(
                chat_id,
                message_id,
                text,
                kb.admin_user_keyboard(target_id, is_blocked=ident.is_blocked),
            )
        elif action == "block" and len(parts) > 2:
            BotAdminService.block_user(int(parts[2]), admin=user)
            self._edit_or_send(chat_id, message_id, "✅ کاربر مسدود شد.", kb.admin_home_keyboard())
        elif action == "unblock" and len(parts) > 2:
            BotAdminService.unblock_user(int(parts[2]), admin=user)
            self._edit_or_send(chat_id, message_id, "✅ مسدودی برداشته شد.", kb.admin_home_keyboard())
        elif action == "disconnect" and len(parts) > 2:
            BotAuthService.disconnect_bale(int(parts[2]))
            self._edit_or_send(chat_id, message_id, "✅ اتصال بله قطع شد.", kb.admin_home_keyboard())
        elif action == "sync":
            status = BotAdminService.sync_status()
            lines = [
                "🔄 وضعیت بروزرسانی",
                "",
                f"🟢 آخرین Sync موفق:\n{status['last_sync_label']}",
                "",
            ]
            labels = {
                "sale_orders": "🧾 فاکتورها",
                "sale_orders_with_stuffs": "📄 اقلام فاکتور",
                "visitor_sale": "📊 فروش",
                "account_balance": "💳 حساب‌ها",
            }
            for rep in status["reports"]:
                icon = "✅" if rep["ok"] else "❌"
                lines.append(f"{labels.get(rep['key'], rep['key'])}: {icon}")
            self._edit_or_send(chat_id, message_id, "\n".join(lines), kb.admin_home_keyboard())
        elif action == "logins":
            rows = BotAdminService.recent_logins()
            lines = ["🔐 ورودهای اخیر", ""]
            for row in rows:
                who = row.user.get_full_name() if row.user else str(row.bale_user_id)
                lines.append(f"• {who} — {row.created_at.strftime('%H:%M')}")
            self._edit_or_send(chat_id, message_id, "\n".join(lines) or "—", kb.admin_home_keyboard())
        elif action == "activity":
            rows = BotAdminService.recent_activities()
            lines = ["📜 فعالیت‌ها", ""]
            for row in rows:
                lines.append(f"• {row.action} — {row.created_at.strftime('%m/%d %H:%M')}")
            self._edit_or_send(chat_id, message_id, "\n".join(lines) or "—", kb.admin_home_keyboard())
        elif action in ("notifications", "settings", "blocked"):
            self._edit_or_send(
                chat_id,
                message_id,
                fmt.placeholder_message("🛡 مدیریت", "🚧 به‌زودی"),
                kb.admin_home_keyboard(),
            )
