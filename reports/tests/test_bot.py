"""Tests for Bale visitor bot."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from reports.constants import KaraRole, SyncStatus
from reports.models import (
    BaleUserIdentity,
    BotInvoiceWatchState,
    BotNotificationEvent,
    BotVisitorCredential,
    KaraReportSnapshot,
    KaraSyncJob,
    SaleOrderSnapshot,
    SalespersonDailyMetric,
    UserKaraIdentity,
)
from reports.bot.notifications.tracker import InvoiceNotificationTracker
from reports.bot.permissions import is_bot_admin
from reports.bot.services.auth import AuthError, BotAuthService, LockedError
from reports.bot.services.credentials import BotCredentialService
from reports.bot.services.invoices import BotInvoiceService, derive_order_status
from reports.bot.services.navigation import BotNavigationService


def _provision_visitor(
    personnel_code: str, password: str, *, username: str | None = None
) -> User:
    user = User.objects.create_user(username or f"v_{personnel_code}", password="unused")
    UserKaraIdentity.objects.create(
        user=user,
        personnel_code=personnel_code,
        role=KaraRole.SALESPERSON,
    )
    cred = BotVisitorCredential(
        personnel_code=personnel_code,
        user=user,
        display_name="تست",
        is_active=True,
    )
    cred.set_password(password)
    cred.save()
    return user


def _provision_supervisor(
    personnel_code: str, password: str, *, username: str | None = None
) -> User:
    user = User.objects.create_user(username or f"sv_{personnel_code}", password="unused")
    UserKaraIdentity.objects.create(
        user=user,
        personnel_code=personnel_code,
        supervisor_code=personnel_code,
        role=KaraRole.SALES_SUPERVISOR,
    )
    cred = BotVisitorCredential(
        personnel_code=personnel_code,
        user=user,
        display_name="سرپرست تست",
        is_active=True,
    )
    cred.set_password(password)
    cred.save()
    return user


class BotAuthTests(TestCase):
    def setUp(self):
        self.user_a = _provision_visitor("101", "secret-a", username="visitor_a")
        self.user_b = _provision_visitor("202", "secret-b", username="visitor_b")
        self.admin = User.objects.create_superuser("admin", password="admin-pass")
        UserKaraIdentity.objects.create(
            user=self.admin,
            personnel_code="999",
            role=KaraRole.SYSTEM_ADMIN,
        )

    def test_login_success(self):
        user = BotAuthService.authenticate(1001, "101", "secret-a")
        self.assertEqual(user.pk, self.user_a.pk)
        self.assertTrue(BaleUserIdentity.objects.filter(bale_user_id=1001).exists())

    def test_login_failure_wrong_password(self):
        with self.assertRaises(AuthError):
            BotAuthService.authenticate(1002, "101", "wrong")
        self.assertFalse(BaleUserIdentity.objects.filter(bale_user_id=1002).exists())

    def test_login_failure_unknown_code(self):
        with self.assertRaises(AuthError):
            BotAuthService.authenticate(1002, "99999", "secret-a")

    def test_blocked_user(self):
        BaleUserIdentity.objects.create(
            bale_user_id=1003, user=self.user_a, is_blocked=True
        )
        from reports.bot.services.auth import BlockedError

        with self.assertRaises(BlockedError):
            BotAuthService.ensure_not_locked(1003)

    def test_login_lockout(self):
        with self.settings(BALE_LOGIN_MAX_ATTEMPTS=3, BALE_LOGIN_LOCK_MINUTES=15):
            for _ in range(3):
                with self.assertRaises(AuthError):
                    BotAuthService.authenticate(1004, "101", "wrong")
            with self.assertRaises(LockedError):
                BotAuthService.authenticate(1004, "101", "secret-a")

    def test_provision_credential(self):
        result = BotCredentialService.provision("303", display_name="ویزیتور جدید")
        self.assertTrue(result.created)
        self.assertEqual(result.password, "303")
        self.assertTrue(BotCredentialService.credential_exists("303"))
        user = BotAuthService.authenticate(9001, "303", "303")
        self.assertEqual(user.kara_identity.personnel_code, "303")


class BotInvoiceAccessTests(TestCase):
    def setUp(self):
        self.user_a = _provision_visitor("101", "x", username="va")
        self.user_b = _provision_visitor("202", "x", username="vb")
        job = KaraSyncJob.objects.create(report_key="sale_orders", status=SyncStatus.SUCCESS)
        self.snap = KaraReportSnapshot.objects.create(
            report_key="sale_orders",
            sync_job=job,
            fetched_at=timezone.now(),
            raw_data={},
        )
        SaleOrderSnapshot.objects.create(
            snapshot=self.snap,
            sync_job=job,
            order_code="100",
            partner_name="فروشگاه احمدی",
            visitor_code="101",
            order_final_price=Decimal("100000"),
        )
        SaleOrderSnapshot.objects.create(
            snapshot=self.snap,
            sync_job=job,
            order_code="200",
            partner_name="فروشگاه رضایی",
            visitor_code="202",
            order_final_price=Decimal("200000"),
        )

    def test_visitor_invoice_list(self):
        items, page, pages = BotInvoiceService.list_page(self.user_a, 1)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].order_code, "100")

    def test_visitor_cannot_view_other_invoice(self):
        self.assertFalse(BotInvoiceService.can_access_order(self.user_a, "200"))
        self.assertIsNone(BotInvoiceService.get_order(self.user_a, "200"))

    def test_search_by_number(self):
        order = BotInvoiceService.search_by_number(self.user_a, "100")
        self.assertIsNotNone(order)
        self.assertEqual(order.order_code, "100")

    def test_search_by_customer(self):
        orders, _, _ = BotInvoiceService.search_by_customer(self.user_a, "احمدی")
        self.assertEqual(len(orders), 1)

    def test_invoice_detail(self):
        order = BotInvoiceService.get_order(self.user_a, "100")
        self.assertIsNotNone(order)
        summary = BotInvoiceService.to_summary(order)
        self.assertIn("احمدی", summary.partner_name)

    def test_pagination(self):
        job = self.snap.sync_job
        for i in range(10):
            SaleOrderSnapshot.objects.create(
                snapshot=self.snap,
                sync_job=job,
                order_code=f"ORD{i}",
                partner_name=f"مشتری {i}",
                visitor_code="101",
                order_final_price=Decimal("1000"),
            )
        items, page, pages = BotInvoiceService.list_page(self.user_a, 1)
        self.assertEqual(len(items), BotInvoiceService.PAGE_SIZE)
        self.assertGreater(pages, 1)

    def test_prefers_full_snapshot_over_empty_daily(self):
        """Daily snapshot is newer but empty; bot must read YTD full snapshot."""
        job = self.snap.sync_job
        full_snap = KaraReportSnapshot.objects.create(
            report_key="sale_orders",
            sync_job=job,
            fetched_at=timezone.now(),
            period_from="1405/01/01",
            period_to="1405/05/22",
            raw_data={},
        )
        SaleOrderSnapshot.objects.create(
            snapshot=full_snap,
            sync_job=job,
            order_code="300",
            partner_name="فروشگاه کامل",
            visitor_code="101",
            order_final_price=Decimal("300000"),
        )
        daily_snap = KaraReportSnapshot.objects.create(
            report_key="sale_orders",
            sync_job=job,
            fetched_at=timezone.now() + timezone.timedelta(seconds=5),
            period_from="1405/05/23",
            period_to="1405/05/23",
            raw_data={},
        )
        self.assertEqual(SaleOrderSnapshot.objects.filter(snapshot=daily_snap).count(), 0)

        items, _, _ = BotInvoiceService.list_page(self.user_a, 1)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].order_code, "300")

    def test_line_items_from_snapshot(self):
        from reports.models import SaleOrderLineSnapshot

        job = self.snap.sync_job
        line_snap = KaraReportSnapshot.objects.create(
            report_key="sale_orders_with_stuffs",
            sync_job=job,
            fetched_at=timezone.now(),
            period_from="1405/01/01",
            period_to="1405/05/22",
            raw_data={},
        )
        SaleOrderLineSnapshot.objects.create(
            snapshot=line_snap,
            sync_job=job,
            row_key="100|500|32|1000",
            order_code="100",
            visitor_code="101",
            stuff_code="500",
            stuff_name="کالای تست",
            stuff_quantity=10,
            line_amount=Decimal("100000"),
        )
        order = SaleOrderSnapshot.objects.get(order_code="100")
        items = BotInvoiceService.line_items_from_order(order)
        self.assertEqual(len(items), 1)
        self.assertIn("کالای تست", items[0]["name"])

    def test_line_items_page(self):
        job = self.snap.sync_job
        order = SaleOrderSnapshot.objects.create(
            snapshot=self.snap,
            sync_job=job,
            order_code="ITEMS",
            partner_name="تست",
            visitor_code="101",
            order_final_price=Decimal("50000"),
            raw_data={
                "items": [
                    {"StuffName": f"کالا {i}", "SaleStuffQuantity": i, "SaleSum": "1000"}
                    for i in range(1, 8)
                ]
            },
        )
        items, page, pages, total = BotInvoiceService.line_items_page(order, 1)
        self.assertEqual(len(items), BotInvoiceService.ITEMS_PAGE_SIZE)
        self.assertEqual(total, 7)
        self.assertEqual(pages, 2)

    def test_customer_list(self):
        from reports.bot.services.customers import BotCustomerService

        overview = BotCustomerService.overview(self.user_a)
        self.assertEqual(overview["customer_count"], 1)
        customers, page, pages = BotCustomerService.list_page(self.user_a, 1)
        self.assertEqual(len(customers), 1)
        self.assertIn("احمدی", customers[0].partner_name)


class BotSupervisorAccessTests(TestCase):
    def setUp(self):
        self.supervisor = _provision_supervisor("501", "sv-pass", username="supervisor")
        self.user_a = _provision_visitor("101", "x", username="va")
        self.user_b = _provision_visitor("202", "x", username="vb")
        SalespersonDailyMetric.objects.create(
            business_date=timezone.localdate(),
            personnel_code="101",
            personnel_name="ویزیتور الف",
            supervisor_code="501",
        )
        SalespersonDailyMetric.objects.create(
            business_date=timezone.localdate(),
            personnel_code="202",
            personnel_name="ویزیتور ب",
            supervisor_code="999",
        )
        job = KaraSyncJob.objects.create(report_key="sale_orders", status=SyncStatus.SUCCESS)
        self.snap = KaraReportSnapshot.objects.create(
            report_key="sale_orders",
            sync_job=job,
            fetched_at=timezone.now(),
            raw_data={},
        )
        SaleOrderSnapshot.objects.create(
            snapshot=self.snap,
            sync_job=job,
            order_code="100",
            partner_name="فروشگاه احمدی",
            visitor_code="101",
            order_final_price=Decimal("100000"),
        )
        SaleOrderSnapshot.objects.create(
            snapshot=self.snap,
            sync_job=job,
            order_code="200",
            partner_name="فروشگاه رضایی",
            visitor_code="202",
            order_final_price=Decimal("200000"),
        )

    def test_supervisor_sees_team_invoices_only(self):
        items, _, _ = BotInvoiceService.list_page(self.supervisor, 1)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].order_code, "100")

    def test_supervisor_cannot_view_other_team_invoice(self):
        self.assertFalse(BotInvoiceService.can_access_order(self.supervisor, "200"))

    def test_supervisor_team_roster(self):
        from reports.bot.services.team import BotTeamService

        members = BotTeamService.roster(self.supervisor)
        self.assertEqual(len(members), 1)
        self.assertEqual(members[0].personnel_code, "101")

    def test_supervisor_performance(self):
        from reports.bot.services.performance import BotPerformanceService

        data = BotPerformanceService.snapshot(self.supervisor)
        self.assertEqual(data.get("mode"), "supervisor")
        self.assertTrue(data.get("has_data"))

    def test_provision_supervisor_credential(self):
        result = BotCredentialService.provision_supervisor("601", display_name="سرپرست جدید")
        self.assertTrue(result.created)
        user = BotAuthService.authenticate(9100, "601", "601")
        self.assertEqual(user.kara_identity.role, KaraRole.SALES_SUPERVISOR)
        self.assertEqual(user.kara_identity.supervisor_code, "601")

    def test_supervisor_never_admin(self):
        with self.settings(BALE_ADMIN_IDS=[555]):
            BaleUserIdentity.objects.create(bale_user_id=555, user=self.supervisor)
            self.assertFalse(is_bot_admin(self.supervisor, 555))


class BotSettlementTests(TestCase):
    def setUp(self):
        self.user = _provision_visitor("101", "x", username="va")
        job = KaraSyncJob.objects.create(
            report_key="receivables_aging", status=SyncStatus.SUCCESS
        )
        snap = KaraReportSnapshot.objects.create(
            report_key="receivables_aging",
            sync_job=job,
            fetched_at=timezone.now(),
            period_from="1405/01/01",
            period_to="1405/05/22",
            raw_data={},
        )
        from reports.models import ReceivableAgingSnapshot

        ReceivableAgingSnapshot.objects.create(
            snapshot=snap,
            sync_job=job,
            row_key="101|104|teh|z1",
            visitor_code="101",
            partner_code="104",
            partner_name="فروشگاه تست",
            city_name="تهران",
            total_outstanding=Decimal("500000"),
            bucket_amounts={"M1": "500000"},
        )

    def test_settlement_overview(self):
        from reports.bot.services.settlement import BotSettlementService

        data = BotSettlementService.overview(self.user)
        self.assertTrue(data["has_data"])
        self.assertEqual(data["partner_count"], 1)


class BotAdminTests(TestCase):
    def test_admin_permission(self):
        admin = User.objects.create_superuser("adm", password="p")
        regular = User.objects.create_user("reg", password="p")
        UserKaraIdentity.objects.create(
            user=regular, personnel_code="1", role=KaraRole.SALESPERSON
        )
        with self.settings(BALE_ADMIN_IDS=[]):
            self.assertTrue(is_bot_admin(admin, 1))
            self.assertFalse(is_bot_admin(regular, 2))

    def test_non_admin_denied(self):
        user = User.objects.create_user("u", password="p")
        UserKaraIdentity.objects.create(
            user=user, personnel_code="5", role=KaraRole.SALESPERSON
        )
        with self.settings(BALE_ADMIN_IDS=[]):
            self.assertFalse(is_bot_admin(user, 99))

    def test_salesperson_never_admin_even_with_bale_admin_id(self):
        user = User.objects.create_user("visitor", password="p")
        UserKaraIdentity.objects.create(
            user=user, personnel_code="20400006", role=KaraRole.SALESPERSON
        )
        with self.settings(BALE_ADMIN_IDS=[744087615]):
            self.assertFalse(is_bot_admin(user, 744087615))


class BotInboxTests(TestCase):
    def setUp(self):
        self.user = _provision_visitor("101", "x", username="inbox_user")
        BaleUserIdentity.objects.create(bale_user_id=9001, user=self.user)

    def test_format_badge(self):
        from reports.bot.services.notifications import format_badge

        self.assertEqual(format_badge("اعلان", 0), "اعلان")
        self.assertEqual(format_badge("اعلان", 3), "اعلان(3)")
        self.assertEqual(format_badge("اعلان", 150), "اعلان(+99)")

    def test_create_and_unread(self):
        from reports.bot.services.notifications import BotNotificationService
        from reports.models import BotUserNotification

        BotNotificationService.create(
            bale_user_id=9001,
            user=self.user,
            category=BotUserNotification.CATEGORY_INVOICE,
            event_type="INVOICE_STATUS",
            title="تست",
            body="متن تست",
            push=False,
        )
        self.assertEqual(BotNotificationService.unread_count(9001), 1)
        badges = BotNotificationService.menu_badges(9001)
        self.assertEqual(badges["notifications"], 1)
        self.assertEqual(badges["invoices"], 1)

    def test_mark_all_read(self):
        from reports.bot.services.notifications import BotNotificationService
        from reports.models import BotUserNotification

        for i in range(3):
            BotNotificationService.create(
                bale_user_id=9001,
                user=self.user,
                category=BotUserNotification.CATEGORY_SYNC,
                event_type="SYNC_COMPLETE",
                title=f"تست {i}",
                body="...",
                push=False,
            )
        self.assertEqual(BotNotificationService.unread_count(9001), 3)
        BotNotificationService.mark_all_read(9001)
        self.assertEqual(BotNotificationService.unread_count(9001), 0)


class BotNotificationTests(TestCase):
    def test_notification_idempotency(self):
        job = KaraSyncJob.objects.create(report_key="sale_orders", status=SyncStatus.SUCCESS)
        snap = KaraReportSnapshot.objects.create(
            report_key="sale_orders", sync_job=job, fetched_at=timezone.now(), raw_data={}
        )
        order = SaleOrderSnapshot(
            snapshot=snap,
            sync_job=job,
            order_code="555",
            visitor_code="101",
            partner_name="تست",
            order_final_price=Decimal("1000"),
            sale_reversion_amount=Decimal("0"),
        )
        BotInvoiceWatchState.objects.create(
            order_code="555", visitor_code="101", status_key="Final"
        )
        order.sale_reversion_amount = Decimal("1000")
        order.pre_order_status = "TotalReversion"
        pending = InvoiceNotificationTracker.process_orders([order])
        self.assertEqual(len(pending), 1)
        with patch.object(InvoiceNotificationTracker, "send_pending", return_value=1):
            InvoiceNotificationTracker.send_pending(pending)
        BotNotificationEvent.objects.create(
            event_type="INVOICE_STATUS",
            entity_type="invoice",
            entity_code="555",
            visitor_code="101",
            old_value="نهایی",
            new_value="TotalReversion",
        )
        pending2 = InvoiceNotificationTracker.process_orders([order])
        self.assertEqual(len(pending2), 0)
        self.assertEqual(
            BotNotificationEvent.objects.filter(
                entity_code="555", new_value="TotalReversion"
            ).count(),
            1,
        )

    def test_derive_status_reverted(self):
        job = KaraSyncJob.objects.create(report_key="sale_orders", status=SyncStatus.SUCCESS)
        snap = KaraReportSnapshot.objects.create(
            report_key="sale_orders", sync_job=job, fetched_at=timezone.now(), raw_data={}
        )
        order = SaleOrderSnapshot(
            snapshot=snap,
            sync_job=job,
            order_code="1",
            order_final_price=Decimal("100"),
            sale_reversion_amount=Decimal("100"),
        )
        key, label = derive_order_status(order)
        self.assertEqual(key, "TotalReversion")
        self.assertEqual(label, "کاملا مرجوعی")


class BotNavigationTests(TestCase):
    def test_back_navigation(self):
        uid = 5000
        BotNavigationService.push_screen(uid, "main")
        BotNavigationService.push_screen(uid, "invoices:1")
        BotNavigationService.push_screen(uid, "invoice:100")
        screen = BotNavigationService.pop_screen(uid)
        self.assertEqual(screen, "invoices:1")

    def test_two_step_login_state(self):
        uid = 6000
        BotNavigationService.set_flow(uid, "WAITING_PASSWORD", personnel_code="101")
        ctx = BotNavigationService.get_context(uid)
        self.assertEqual(ctx["personnel_code"], "101")
