"""Critical unit tests for Kara dashboard foundation."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from reports.constants import PRIMARY_KPI_REPORT, SyncStatus
from reports.exceptions import InvalidResponseError
from reports.models import KaraReportSnapshot
from reports.services.kara_client import KaraGridResponse
from reports.services.analytics import AnalyticsService
from reports.services.parsers import flatten_rows, parse_bool, parse_decimal, parse_number
from reports.services.payload_builder import encode_binding_arguments
from reports.services.report_fetcher import ReportFetcher
from reports.services.report_parser import ReportParser
from reports.services.report_registry import ReportRegistry
from reports.services.sync import SyncOrchestrator


class ParserTests(SimpleTestCase):
    def test_parse_decimal_with_commas(self):
        self.assertEqual(parse_decimal("386,480,000"), Decimal("386480000"))

    def test_parse_persian_digits(self):
        self.assertEqual(parse_decimal("۱,۳۵۴"), Decimal("1354"))

    def test_parse_empty_markers(self):
        self.assertIsNone(parse_decimal("---"))
        self.assertIsNone(parse_decimal("-"))
        self.assertIsNone(parse_decimal(""))
        self.assertIsNone(parse_number(None))

    def test_parse_bool_persian(self):
        self.assertTrue(parse_bool("بله"))
        self.assertFalse(parse_bool("خیر"))
        self.assertIsNone(parse_bool("---"))

    def test_flatten_rows(self):
        raw = {
            "Data": [
                {"Key": 1, "Value": {"VisitorCode": "1", "TotalSale": "100"}},
                {"Key": 2, "Value": {"VisitorCode": "2", "TotalSale": "200"}},
            ]
        }
        rows = flatten_rows(raw)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["_key"], 1)
        self.assertEqual(rows[0]["VisitorCode"], "1")


class PayloadBuilderTests(SimpleTestCase):
    def test_encode_binding_arguments(self):
        encoded = encode_binding_arguments(
            {"BDate": "", "HeadVisitorSale": "False", "TimeGrouping": "0"}
        )
        self.assertIn("BDate=", encoded)
        self.assertIn("HeadVisitorSale=False", encoded)
        self.assertTrue(encoded.endswith("&"))


class RegistryTests(SimpleTestCase):
    def test_required_reports_exist(self):
        keys = ReportRegistry.keys()
        for key in (
            "visitor_sale",
            "head_visitor_sale",
            "stuff_group_sale",
            "sale_reversion",
            "sale_distribution_reversion",
            "sale_orders",
            "sale_orders_with_stuffs",
            "sale_stuffs",
            "monthly_sale",
            "account_balance",
            "receivables_aging",
            "profit_and_loss",
            "entity_list",
        ):
            self.assertIn(key, keys)

    def test_profit_and_loss_is_print_report(self):
        config = ReportRegistry.get("profit_and_loss")
        self.assertTrue(config.is_print_report)
        self.assertEqual(config.print_path, "/Accounting/Print/LostBenefit")

    def test_primary_kpi_source_is_unique(self):
        primaries = [c for c in ReportRegistry.all().values() if c.is_primary_kpi_source]
        self.assertEqual(len(primaries), 1)
        self.assertEqual(primaries[0].key, PRIMARY_KPI_REPORT)

    def test_visitor_and_head_share_binding_method(self):
        v = ReportRegistry.get("visitor_sale")
        h = ReportRegistry.get("head_visitor_sale")
        self.assertEqual(v.binding_method, h.binding_method)
        self.assertEqual(v.default_arguments["HeadVisitorSale"], "False")
        self.assertEqual(h.default_arguments["HeadVisitorSale"], "True")

    def test_sale_orders_with_stuffs_argument_order(self):
        """BStuffCode/EStuffCode must precede ZoneId in BindingArguments."""
        args = ReportRegistry.get("sale_orders_with_stuffs").default_arguments
        keys = list(args.keys())
        self.assertLess(keys.index("BStuffCode"), keys.index("ZoneId"))
        self.assertLess(keys.index("EStuffCode"), keys.index("ZoneId"))
        encoded = encode_binding_arguments(args)
        self.assertLess(encoded.index("BStuffCode="), encoded.index("ZoneId="))


class KpiNoDoubleCountTests(TestCase):
    def test_company_kpis_use_primary_only(self):
        sum_row = {
            "TotalSale": "11,381,896,000",
            "TotalPureSale": "11,360,896,000",
            "OrderCountBasedOnFinalOrder": "311",
            "RemainderBasedOnSettlementWithSaleReversion": "6,691,456,000",
            "TotalDistributionReversion": "2,633,440,000",
            "TotalSaleReversion": "21,000,000",
        }
        # Same totals in BOTH reports — classic double-count trap
        for key, title in (
            ("visitor_sale", "ویزیتور"),
            ("head_visitor_sale", "سرپرست"),
        ):
            KaraReportSnapshot.objects.create(
                report_key=key,
                report_title=title,
                fetched_at=timezone.now(),
                raw_data={
                    "Data": [
                        {
                            "Key": 1,
                            "Value": {
                                "VisitorCode": "1",
                                "VisitorName": "A",
                                "TotalSale": "100",
                                "OrderCountBasedOnFinalOrder": "1",
                            },
                        }
                    ],
                    "SumRowData": sum_row,
                    "GridViewJSTotal": 1,
                },
                rows_count=1,
            )

        kpis = AnalyticsService.company_kpis()
        self.assertEqual(kpis["total_sale"]["numeric"], 11381896000.0)
        # Must NOT be ~22.76B
        self.assertLess(kpis["total_sale"]["numeric"], 20000000000)

        # Legacy aggregate path must also avoid double count
        aggregate = ReportFetcher.get_aggregate_kpis(ReportFetcher.get_dashboard_data())
        self.assertEqual(aggregate["total_sale"]["numeric"], 11381896000.0)


class SyncIdempotencyTests(TestCase):
    @patch("reports.services.sync.orchestrator.KaraClient")
    def test_identical_payload_is_skipped(self, mock_client_cls):
        from reports.constants import SyncStatus
        from reports.services.kara_client import KaraGridResponse
        from reports.services.sync import SyncOrchestrator

        payload_data = {
            "Data": [{"Key": 1, "Value": {"VisitorCode": "200", "VisitorName": "X", "TotalSale": "1000"}}],
            "SumRowData": {"TotalSale": "1000", "TotalPureSale": "1000", "OrderCountBasedOnFinalOrder": "1"},
            "GridViewJSTotal": 1,
        }

        response = KaraGridResponse(
            report_key="visitor_sale",
            report_name="VisitorSaleReportGrid",
            report_title="t",
            total=1,
            count=1,
            data=payload_data["Data"],
            sum_row_data=payload_data["SumRowData"],
            other_informations=[],
            page_count=1,
        )
        client = MagicMock()
        client.run_report.return_value = response
        client.get_session_info.return_value = {}
        mock_client_cls.return_value = client

        orch = SyncOrchestrator(client=client)
        job1 = orch.sync_report("visitor_sale", triggered_by="test")
        self.assertEqual(job1.status, SyncStatus.SUCCESS)
        count_after_first = KaraReportSnapshot.objects.filter(
            report_key="visitor_sale"
        ).count()
        self.assertGreaterEqual(count_after_first, 1)
        self.assertLessEqual(count_after_first, 2)

        job2 = orch.sync_report("visitor_sale", triggered_by="test")
        self.assertEqual(job2.status, SyncStatus.SUCCESS)
        self.assertEqual(job2.skipped_count, 1)
        self.assertEqual(
            KaraReportSnapshot.objects.filter(report_key="visitor_sale").count(),
            count_after_first,
        )

    def test_monthly_sale_falls_back_when_partner_columns_are_invalid(self):
        payload_data = {
            "Data": [{"Key": 1, "Value": {"StuffCode": "500", "FarvardinSale": "1000"}}],
            "SumRowData": {"FarvardinSale": "1000"},
            "GridViewJSTotal": 1,
        }
        response = KaraGridResponse(
            report_key="monthly_sale",
            report_name="MontlyReportGrid",
            report_title="monthly",
            total=1,
            count=1,
            data=payload_data["Data"],
            sum_row_data=payload_data["SumRowData"],
            other_informations=[],
            page_count=1,
        )
        client = MagicMock()
        client.run_report.side_effect = [
            InvalidResponseError(
                "خطا از سمت سرور کارا: Invalid column name 'PartnerTelephones'."
            ),
            response,
        ]
        client.get_session_info.return_value = {}

        orch = SyncOrchestrator(client=client)
        job = orch.sync_report("monthly_sale", triggered_by="test")

        self.assertEqual(job.status, SyncStatus.SUCCESS)
        self.assertEqual(client.run_report.call_count, 2)
        fallback_args = client.run_report.call_args_list[1].kwargs["arguments"]
        self.assertEqual(fallback_args["WithPartnerDetail"], "false")
        self.assertEqual(fallback_args["WithPartnerZoneDetail"], "false")
        self.assertEqual(fallback_args["WithPartnerGroupDetail"], "false")


class KpiExtractionTests(SimpleTestCase):
    def test_extract_kpis_labels_persian(self):
        from django.test import override_settings

        config = ReportRegistry.get("visitor_sale")
        with override_settings(KARA_CURRENCY_UNIT="toman"):
            kpis = ReportParser.extract_kpis(
                {"TotalSale": "1,000", "TotalPureSale": "900", "OrderCountBasedOnFinalOrder": "2"},
                config,
            )
            # 1,000 Rial → 100 Toman
            self.assertEqual(kpis["total_sale"]["formatted"], "100")
            self.assertEqual(kpis["total_sale"]["unit"], "تومان")
            self.assertIn("فروش", kpis["total_sale"]["label"])
            # counts stay unconverted
            self.assertEqual(kpis["final_order_count"]["formatted"], "2")

        with override_settings(KARA_CURRENCY_UNIT="rial"):
            kpis_rial = ReportParser.extract_kpis(
                {"TotalSale": "1,000", "TotalPureSale": "900", "OrderCountBasedOnFinalOrder": "2"},
                config,
            )
            self.assertEqual(kpis_rial["total_sale"]["formatted"], "1,000")
            self.assertEqual(kpis_rial["total_sale"]["unit"], "ریال")


class ProfitabilityHonestyTests(TestCase):
    def test_profitability_not_shown_by_default(self):
        status = AnalyticsService.profitability_status()
        self.assertFalse(status["can_show_profit"])
        self.assertTrue(
            "سود" in status["message"] or "فاکتور" in status["message"]
        )


class AccessControlTests(SimpleTestCase):
    def test_anonymous_scope_is_restricted(self):
        from django.contrib.auth.models import AnonymousUser

        from reports.services.access_control import AccessControlService

        scope = AccessControlService.resolve_scope(AnonymousUser())
        self.assertFalse(scope.unrestricted)

    def test_superuser_scope_is_unrestricted(self):
        from django.contrib.auth.models import User

        from reports.services.access_control import AccessControlService

        user = User(is_superuser=True, is_staff=True)
        scope = AccessControlService.resolve_scope(user)
        self.assertTrue(scope.unrestricted)


class PersianDisplayTests(SimpleTestCase):
    def test_report_titles_are_persian(self):
        from reports.services.display import report_title

        self.assertIn("ویزیتور", report_title("visitor_sale"))
        self.assertIn("کالا", report_title("sale_stuffs"))
        self.assertIn("سرپرست", report_title("head_visitor_sale"))
        self.assertNotEqual(report_title("visitor_sale"), "visitor_sale")

    def test_jalali_date_format(self):
        from datetime import date

        from reports.services.dates import format_jalali_datetime, gregorian_to_jalali

        label = gregorian_to_jalali(date(2026, 7, 30))
        # Must be Jalali year (~1405), not Gregorian 2026
        self.assertTrue(label.startswith("140"))
        self.assertNotIn("2026", label)

        # ISO strings from connection_status must not crash
        iso = format_jalali_datetime("2026-07-30T14:55:00+03:30")
        self.assertTrue(iso.startswith("140"))
        self.assertIn(":", iso)

    def test_sync_status_persian(self):
        from reports.services.display import sync_status_label

        self.assertEqual(sync_status_label("success"), "موفق")
        self.assertEqual(sync_status_label("failed"), "ناموفق")

    def test_currency_default_is_toman(self):
        from django.test import override_settings

        from reports.services.currency import currency_label, format_money_number

        with override_settings(KARA_CURRENCY_UNIT="toman"):
            self.assertEqual(currency_label(), "تومان")
            self.assertEqual(format_money_number("10,000"), "1,000")

        with override_settings(KARA_CURRENCY_UNIT="rial"):
            self.assertEqual(currency_label(), "ریال")
            self.assertEqual(format_money_number("10,000"), "10,000")


class SaleOrderLineSyncTests(TestCase):
    def test_upsert_sale_order_line_rows(self):
        from reports.constants import SyncStatus
        from reports.models import KaraReportSnapshot, KaraSyncJob, SaleOrderLineSnapshot

        job = KaraSyncJob.objects.create(
            report_key="sale_orders_with_stuffs", status=SyncStatus.SUCCESS
        )
        snap = KaraReportSnapshot.objects.create(
            report_key="sale_orders_with_stuffs",
            sync_job=job,
            fetched_at=timezone.now(),
            period_from="1405/01/01",
            period_to="1405/05/22",
            raw_data={},
        )
        rows = [
            {
                "_key": 1,
                "OrderCode": "42",
                "OrderPreCode": "1000042",
                "OrderDate": "1405/02/25",
                "PartnerCode": "10401001",
                "PartnerName": "مشتری تست",
                "VisitorCode": "20400028",
                "VisitorName": "ویزیتور تست",
                "StuffCode": "50000600",
                "StuffName": "آب میوه",
                "StuffGroupName": "نوشیدنی",
                "StuffSubGroupName": "آبمیوه",
                "Package": "باکس",
                "SmallPackage": "عدد",
                "Quantity": "1",
                "StuffQuantity": "32",
                "Fee": "110,000",
                "ArticleFinalPrice": "3,520,000",
                "OrderFinalPrice": "144,400,000",
                "StuffBuyPrice": "85,000",
            }
        ]
        orch = SyncOrchestrator()
        inserted, updated = orch._upsert_sale_order_line_rows(snap, job, rows)
        self.assertEqual(inserted, 1)
        self.assertEqual(updated, 0)

        line = SaleOrderLineSnapshot.objects.get(snapshot=snap, order_code="42")
        self.assertEqual(line.stuff_name, "آب میوه")
        self.assertEqual(line.stuff_quantity, 32)
        self.assertEqual(line.line_amount, Decimal("3520000"))
        self.assertEqual(line.raw_data.get("StuffBuyPrice"), "85,000")


class InvoiceServiceTests(TestCase):
    def setUp(self):
        from reports.constants import SyncStatus
        from reports.models import KaraSyncJob, SaleOrderLineSnapshot, SaleOrderSnapshot

        self.job = KaraSyncJob.objects.create(
            report_key="sale_orders", status=SyncStatus.SUCCESS
        )
        self.order_snap = KaraReportSnapshot.objects.create(
            report_key="sale_orders",
            sync_job=self.job,
            fetched_at=timezone.now(),
            period_from="1405/01/01",
            period_to="1405/05/22",
            raw_data={},
        )
        self.order = SaleOrderSnapshot.objects.create(
            snapshot=self.order_snap,
            sync_job=self.job,
            order_code="42",
            order_pre_code="1000042",
            partner_name="مشتری تست",
            visitor_code="20400028",
            order_date="1405/02/25",
            order_final_price=Decimal("144400000"),
            stuffs_quantity_sum=1,
            pre_order_status="Final",
            raw_data={
                "StuffsPriceSum": "3,520,000",
                "OrderDate": "1405/02/25",
                "WarehouseDocumentDate": "1405/02/25",
                "OrderFinalPrice": "144,400,000",
            },
        )
        line_snap = KaraReportSnapshot.objects.create(
            report_key="sale_orders_with_stuffs",
            sync_job=self.job,
            fetched_at=timezone.now(),
            period_from="1405/01/01",
            period_to="1405/05/22",
            raw_data={},
        )
        SaleOrderLineSnapshot.objects.create(
            snapshot=line_snap,
            sync_job=self.job,
            row_key="1",
            order_code="42",
            stuff_code="50000600",
            stuff_name="آب میوه",
            stuff_group_name="نوشیدنی",
            stuff_quantity=32,
            line_amount=Decimal("3520000"),
            raw_data={"StuffBuyPrice": "85,000"},
        )

    def test_line_items_and_serialization(self):
        from reports.services.invoices import InvoiceService

        items = InvoiceService.line_items_as_dicts(self.order)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["name"], "آب میوه")
        self.assertIn("8,500", items[0]["buy_price"] or "")

        payload = InvoiceService.serialize_order(self.order, include_lines=True)
        self.assertTrue(payload["has_line_items"])
        self.assertEqual(payload["line_items_total"], 1)
        self.assertEqual(payload["financial_breakdown"][0]["label"], "📦 تعداد اقلام")

    def test_filter_by_status_and_visitor(self):
        from reports.models import SaleOrderSnapshot
        from reports.services.invoices import InvoiceListFilters, InvoiceService

        SaleOrderSnapshot.objects.create(
            snapshot=self.order_snap,
            sync_job=self.job,
            order_code="99",
            order_pre_code="1000099",
            partner_name="برگشتی",
            visitor_code="20400099",
            visitor_name="ویزیتور دوم",
            order_final_price=Decimal("1000000"),
            sale_reversion_amount=Decimal("1000000"),
            stuffs_quantity_sum=2,
            pre_order_status="TotalReversion",
        )

        final_only = InvoiceListFilters(status="Final")
        orders, _, _ = InvoiceService.filter_page(None, final_only, 1)
        self.assertTrue(all(o.pre_order_status == "Final" for o in orders))

        reverted = InvoiceListFilters(status="TotalReversion")
        orders, _, _ = InvoiceService.filter_page(None, reverted, 1)
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].order_code, "99")

        by_visitor = InvoiceListFilters(visitor="20400028")
        orders, _, _ = InvoiceService.filter_page(None, by_visitor, 1)
        self.assertTrue(all(o.visitor_code == "20400028" for o in orders))

    def test_derive_pre_order_status(self):
        from reports.services.invoices import derive_pre_order_status, pre_order_status_label

        self.assertEqual(
            derive_pre_order_status(
                {
                    "OrderFinalPrice": "1,000,000",
                    "SaleReversionAmount": "1,000,000",
                }
            ),
            "TotalReversion",
        )
        self.assertEqual(
            derive_pre_order_status(
                {
                    "TotalCode": "15",
                    "DriverName": "راننده",
                    "PayeeName": "تحویل",
                    "WarehouseDocumentDate": "1405/04/09",
                    "OrderFinalPrice": "100",
                }
            ),
            "ConfirmedShipment",
        )
        self.assertEqual(pre_order_status_label("Final"), "نهایی")

    def test_sync_status_reports_counts(self):
        from reports.services.invoices import InvoiceService

        status = InvoiceService.sync_status()
        self.assertGreaterEqual(status["orders_count"], 1)
        self.assertGreaterEqual(status["line_items_count"], 1)
