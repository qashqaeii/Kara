"""Analytics layer tests."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from reports.models import (
    DailyBusinessMetric,
    KaraReportSnapshot,
    ManagementAlert,
    MonthlyCompanySales,
    ProductDailyMetric,
    ProfitDailyMetric,
    SalespersonDailyMetric,
)
from reports.services.analytics_query import AnalyticsQueryService
from reports.services.analytics_pipeline import AnalyticsPipeline
from reports.services.alert_engine import AlertEngine
from reports.services.period_comparison import PeriodComparisonService


class AnalyticsPipelineTests(TestCase):
    def _visitor_snapshot(self, bdate: date) -> KaraReportSnapshot:
        return KaraReportSnapshot.objects.create(
            report_key="visitor_sale",
            report_title="t",
            fetched_at=timezone.now(),
            period_to=f"{bdate.year}/{bdate.month:02d}/{bdate.day:02d}",
            raw_data={
                "Data": [
                    {
                        "Key": 1,
                        "Value": {
                            "VisitorCode": "100",
                            "VisitorName": "Ali",
                            "HeadVisitorCode": "9",
                            "HeadVisitorName": "Boss",
                            "TotalSale": "1000",
                            "TotalPureSale": "900",
                            "OrderCountBasedOnFinalOrder": "2",
                            "TotalDistributionReversion": "50",
                            "TotalSaleReversion": "50",
                        },
                    }
                ],
                "SumRowData": {
                    "TotalSale": "1000",
                    "TotalPureSale": "900",
                    "OrderCountBasedOnFinalOrder": "2",
                    "TotalDistributionReversion": "50",
                    "TotalSaleReversion": "50",
                },
                "GridViewJSTotal": 1,
            },
            rows_count=1,
        )

    def test_pipeline_upserts_company_and_salesperson_metrics(self):
        snap = self._visitor_snapshot(date(2026, 7, 28))
        self.assertTrue(AnalyticsPipeline.process_snapshot(snap))
        self.assertEqual(DailyBusinessMetric.objects.count(), 1)
        self.assertEqual(SalespersonDailyMetric.objects.count(), 1)

    def test_pipeline_idempotent(self):
        snap = self._visitor_snapshot(date(2026, 7, 28))
        AnalyticsPipeline.process_snapshot(snap)
        AnalyticsPipeline.process_snapshot(snap)
        self.assertEqual(DailyBusinessMetric.objects.count(), 1)


class SaleOrdersPipelineTests(TestCase):
    def test_sale_orders_profit_metric(self):
        snap = KaraReportSnapshot.objects.create(
            report_key="sale_orders",
            report_title="orders",
            fetched_at=timezone.now(),
            period_to="2026/07/28",
            raw_data={
                "Data": [
                    {
                        "Key": 1,
                        "Value": {
                            "OrderCode": "1",
                            "OrderFinalPrice": "100,000",
                            "FinalizedCostForCustomer": "40,000",
                            "SaleReversionAmount": "5,000",
                        },
                    }
                ],
                "SumRowData": {
                    "OrderFinalPrice": "100,000",
                    "FinalizedCostForCustomer": "40,000",
                    "SaleReversionAmount": "5,000",
                },
                "GridViewJSTotal": 1,
            },
            rows_count=1,
        )
        self.assertTrue(AnalyticsPipeline.process_snapshot(snap))
        metric = ProfitDailyMetric.objects.get()
        self.assertEqual(metric.gross_profit, 55000)
        self.assertEqual(metric.invoice_count, 1)


class SaleStuffsPipelineTests(TestCase):
    def test_sale_stuffs_product_metric(self):
        snap = KaraReportSnapshot.objects.create(
            report_key="sale_stuffs",
            report_title="stuffs",
            fetched_at=timezone.now(),
            period_to="2026/07/28",
            raw_data={
                "Data": [
                    {
                        "Key": 1,
                        "Value": {
                            "StuffCode": "50000900",
                            "StuffName": "تن ماهی",
                            "StuffGroupName": "کنسرو",
                            "SaleStuffQuantity": "10",
                            "SaleSum": "1,000,000",
                            "SaleReversionSum": "100,000",
                            "PureSale": "900,000",
                        },
                    }
                ],
                "SumRowData": {"PureSale": "900,000"},
                "GridViewJSTotal": 1,
            },
            rows_count=1,
        )
        self.assertTrue(AnalyticsPipeline.process_snapshot(snap))
        product = ProductDailyMetric.objects.get()
        self.assertEqual(product.pure_sale, 900000)
        self.assertEqual(product.stuff_name, "تن ماهی")

    def test_return_only_does_not_wipe_stuff_group_sales(self):
        from reports.models import ProductDailyMetric
        from reports.services.dates import snapshot_business_date

        fetched = timezone.now()
        period = "2026/07/28"
        bdate = snapshot_business_date(period_to=period, fetched_at=fetched)
        ProductDailyMetric.objects.create(
            business_date=bdate,
            stuff_code="50000900",
            stuff_name="تن ماهی",
            stuff_group_name="کنسرو",
            sale_amount=5_000_000,
            pure_sale=4_800_000,
            sale_reversion_amount=0,
        )
        snap = KaraReportSnapshot.objects.create(
            report_key="sale_stuffs",
            report_title="stuffs",
            fetched_at=fetched,
            period_to=period,
            raw_data={
                "Data": [
                    {
                        "Key": 1,
                        "Value": {
                            "StuffCode": "50000900",
                            "StuffName": "تن ماهی",
                            "StuffGroupName": "کنسرو",
                            "SaleStuffQuantity": "0",
                            "SaleSum": "0",
                            "SaleReversionSum": "210,000",
                            "PureSale": "-210,000",
                        },
                    }
                ],
                "SumRowData": {},
                "GridViewJSTotal": 1,
            },
            rows_count=1,
        )
        self.assertTrue(AnalyticsPipeline.process_snapshot(snap))
        product = ProductDailyMetric.objects.get(
            stuff_code="50000900", business_date=bdate
        )
        self.assertEqual(product.sale_amount, 5_000_000)
        self.assertEqual(product.pure_sale, 4_800_000)
        self.assertEqual(product.sale_reversion_amount, 210_000)

    def test_product_ranking_skips_negative_pure_sale(self):
        from reports.models import ProductDailyMetric
        from reports.services.dates import DateRange

        bdate = timezone.localdate()
        ProductDailyMetric.objects.create(
            business_date=bdate,
            stuff_code="NEG",
            stuff_name="فقط برگشت",
            pure_sale=-1_000_000,
            sale_amount=0,
            sale_reversion_amount=1_000_000,
        )
        ProductDailyMetric.objects.create(
            business_date=bdate,
            stuff_code="POS",
            stuff_name="پرفروش",
            pure_sale=2_000_000,
            sale_amount=2_200_000,
            sale_reversion_amount=50_000,
        )
        top = AnalyticsQueryService.product_ranking(
            dr=DateRange(bdate, bdate), limit=5
        )
        self.assertEqual(len(top), 1)
        self.assertEqual(top[0]["code"], "POS")
        self.assertGreater(top[0]["pure_sale"], 0)
        rev = AnalyticsQueryService.product_ranking(
            dr=DateRange(bdate, bdate), limit=5, rank_by="sale_reversion_amount"
        )
        self.assertTrue(all(r["sale_reversion_amount"] > 0 for r in rev))


class StuffGroupProductPipelineTests(TestCase):
    def test_stuff_group_builds_product_metrics(self):
        from reports.models import ProductDailyMetric

        snap = KaraReportSnapshot.objects.create(
            report_key="stuff_group_sale",
            report_title="groups",
            fetched_at=timezone.now(),
            period_to="2026/07/28",
            raw_data={
                "Data": [
                    {
                        "Key": 1,
                        "Value": {
                            "StuffCode": "500001",
                            "StuffName": "کالای الف",
                            "StuffGroupName": "گروه ۱",
                            "City": "تهران",
                            "Zone": "منطقه ۱",
                            "PureSalePrice": "1,000,000",
                            "NotPureSalePrice": "1,100,000",
                            "SaleReversionPrice": "50,000",
                            "PureSaleQuantity": "10",
                            "OrderCount": "2",
                        },
                    },
                    {
                        "Key": 2,
                        "Value": {
                            "StuffCode": "500001",
                            "StuffName": "کالای الف",
                            "StuffGroupName": "گروه ۱",
                            "City": "کرج",
                            "Zone": "منطقه ۲",
                            "PureSalePrice": "500,000",
                            "NotPureSalePrice": "550,000",
                            "SaleReversionPrice": "0",
                            "PureSaleQuantity": "5",
                            "OrderCount": "1",
                        },
                    },
                ],
                "SumRowData": {},
                "GridViewJSTotal": 2,
            },
            rows_count=2,
        )
        self.assertTrue(AnalyticsPipeline.process_snapshot(snap))
        product = ProductDailyMetric.objects.get(stuff_code="500001")
        self.assertEqual(product.pure_sale, 1_500_000)
        self.assertEqual(product.sale_amount, 1_650_000)
        self.assertEqual(product.sale_reversion_amount, 50_000)


class MonthlySalePipelineTests(TestCase):
    def test_monthly_sale_company_metric(self):
        snap = KaraReportSnapshot.objects.create(
            report_key="monthly_sale",
            report_title="monthly",
            fetched_at=timezone.now(),
            raw_data={
                "Data": [
                    {
                        "Key": 1,
                        "Value": {
                            "PartnerCode": "1",
                            "StuffCode": "500",
                            "FarvardinSale": "100",
                            "OrdibeheshtSale": "200",
                        },
                    }
                ],
                "SumRowData": {
                    "FarvardinSale": "1,000,000",
                    "OrdibeheshtSale": "2,000,000",
                    "KhordadSale": "0",
                    "TirSale": "0",
                    "MordadSale": "0",
                    "ShahrivarSale": "0",
                    "MehrSale": "0",
                    "AbanSale": "0",
                    "AzarSale": "0",
                    "DeySale": "0",
                    "BahmanSale": "0",
                    "EsfandSale": "0",
                },
                "GridViewJSTotal": 1,
            },
            rows_count=1,
        )
        self.assertTrue(AnalyticsPipeline.process_snapshot(snap))
        record = MonthlyCompanySales.objects.get()
        self.assertEqual(record.total_ytd, 3000000)
        series = AnalyticsQueryService.monthly_sales_series()
        self.assertTrue(series["available"])
        self.assertEqual(len(series["series"]), 12)
        self.assertEqual(series["series"][0]["value"], 100000.0)  # 1,000,000 Rial → Toman


class PeriodComparisonTests(TestCase):
    def test_compare_with_zero_previous(self):
        today = timezone.localdate()
        DailyBusinessMetric.objects.create(
            metric_date=today.isoformat(),
            business_date=today,
            total_pure_sale=1000,
            order_count=1,
        )
        result = PeriodComparisonService.compare_field("total_pure_sale", "today")
        self.assertTrue(result.is_comparable or result.note)

    def test_absurd_percent_not_comparable(self):
        today = timezone.localdate()
        # Current week-ish window needs enough days; seed last_7_days heavily
        # vs tiny prior window.
        for i in range(7):
            d = today - timedelta(days=i)
            DailyBusinessMetric.objects.create(
                metric_date=d.isoformat(),
                business_date=d,
                source_report=f"visitor_sale_{i}",
                total_pure_sale=1_000_000_000,
                order_count=1,
            )
        # One tiny day in prior window
        prior = today - timedelta(days=10)
        DailyBusinessMetric.objects.create(
            metric_date=prior.isoformat(),
            business_date=prior,
            source_report="visitor_sale_prior",
            total_pure_sale=1000,
            order_count=1,
        )
        result = PeriodComparisonService.compare_field("total_pure_sale", "last_7_days")
        self.assertFalse(result.is_comparable)
        self.assertIsNone(result.percent_change)


class AlertDedupTests(TestCase):
    def test_alert_dedup_by_rule_key(self):
        AlertEngine._ensure(
            rule_key="stale_data",
            entity_type="system",
            entity_code="sync",
            period="2026-07-28",
            severity="warning",
            title="داده قدیمی",
            description="test",
        )
        AlertEngine._ensure(
            rule_key="stale_data",
            entity_type="system",
            entity_code="sync",
            period="2026-07-28",
            severity="warning",
            title="داده قدیمی",
            description="test2",
        )
        self.assertEqual(
            ManagementAlert.objects.filter(rule_key="stale_data").count(), 1
        )

    def test_sync_failed_closes_after_recovery(self):
        from reports.constants import AlertStatus, SyncStatus
        from reports.models import KaraSyncJob

        failed = KaraSyncJob.objects.create(
            report_key="receivables_aging",
            status=SyncStatus.FAILED,
            error_message="Schema changed after the target table was created. Rerun the Select Into query.",
        )
        AlertEngine._rule_sync_failed()
        self.assertEqual(
            ManagementAlert.objects.filter(
                rule_key="sync_failed",
                entity_code="receivables_aging",
                status=AlertStatus.OPEN,
            ).count(),
            1,
        )

        success = KaraSyncJob.objects.create(
            report_key="receivables_aging",
            status=SyncStatus.SUCCESS,
        )
        # Ensure success is ordered after the failure for recovery detection.
        KaraSyncJob.objects.filter(pk=success.pk).update(
            started_at=failed.started_at + timedelta(minutes=2)
        )
        AlertEngine._rule_sync_failed()
        self.assertEqual(
            ManagementAlert.objects.filter(
                rule_key="sync_failed",
                entity_code="receivables_aging",
                status=AlertStatus.OPEN,
            ).count(),
            0,
        )

    def test_stale_data_closes_when_connected(self):
        from unittest.mock import patch

        from reports.constants import AlertStatus, ConnectionStatus

        AlertEngine._ensure(
            rule_key="stale_data",
            entity_type="system",
            entity_code="sync",
            period=timezone.localdate().isoformat(),
            severity="warning",
            title="داده قدیمی",
            description="قدیمی",
        )
        with patch(
            "reports.services.alert_engine._connection_status",
            return_value={
                "status": ConnectionStatus.CONNECTED,
                "last_sync_label": "1 دقیقه قبل",
            },
        ):
            AlertEngine._rule_stale_data()
        self.assertEqual(
            ManagementAlert.objects.filter(
                rule_key="stale_data", status=AlertStatus.OPEN
            ).count(),
            0,
        )


class ProfitLossParserTests(TestCase):
    def test_parse_lost_benefit_sample(self):
        from reports.services.parsers.profit_loss import parse_lost_benefit_html

        html = """
        <table>
            <tr><td>فروش خالص</td><td>فروش</td><td></td><td>20,440,486,000</td></tr>
            <tr><td colspan="2">جمع:</td><td></td><td>20,412,786,000</td></tr>
            <tr><td>بهای تمام شده کالای فروش رفته</td><td>خرید</td><td>0</td><td></td></tr>
            <tr><td colspan="2">جمع:</td><td>(37,099,150,241)</td><td></td></tr>
            <tr><td colspan="2">سود(زیان) عملیاتی:</td><td></td><td>57,511,936,241</td></tr>
            <tr><td colspan="2">سود(زیان) خالص:</td><td></td><td>46,473,726,451</td></tr>
        </table>
        """
        parsed = parse_lost_benefit_html(html)
        self.assertEqual(parsed["net_pure_sale"], "20412786000")
        # COGS keeps Kara's signed total (parentheses = negative inventory effect).
        self.assertEqual(parsed["cost_of_goods_sold"], "-37099150241")
        self.assertEqual(parsed["gross_profit"], "57511936241")
        self.assertEqual(parsed["operating_profit"], "57511936241")
        self.assertEqual(parsed["net_profit"], "46473726451")

    def test_pipeline_profit_and_loss(self):
        from reports.models import CompanyProfitLossMetric

        snap = KaraReportSnapshot.objects.create(
            report_key="profit_and_loss",
            report_title="pnl",
            fetched_at=timezone.now(),
            period_to="1405/05/08",
            period_from="1405/01/01",
            raw_data={
                "parsed": {
                    "net_pure_sale": "20412786000",
                    "cost_of_goods_sold": "37099150241",
                    "gross_profit": "-16686364241",
                    "operating_profit": "57511936241",
                    "net_profit": "46473726451",
                    "gross_margin_rate": "0",
                    "line_items": {},
                },
                "SumRowData": {
                    "NetPureSale": "20412786000",
                    "OperatingProfit": "57511936241",
                    "NetProfit": "46473726451",
                },
                "Data": [],
            },
            rows_count=0,
        )
        self.assertTrue(AnalyticsPipeline.process_snapshot(snap))
        metric = CompanyProfitLossMetric.objects.get()
        self.assertEqual(metric.operating_profit, 57511936241)
        self.assertTrue(AnalyticsQueryService.has_company_pnl())


class ReceivablesPipelineTests(TestCase):
    def test_aging_and_balance_metrics(self):
        from reports.models import ReceivableDailyMetric

        aging = KaraReportSnapshot.objects.create(
            report_key="receivables_aging",
            report_title="aging",
            fetched_at=timezone.now(),
            period_to="2026/07/28",
            raw_data={
                "Data": [
                    {
                        "Key": 1,
                        "Value": {
                            "VisitorCode": "20000001",
                            "VisitorName": "A",
                            "CityName": "تهران",
                            "ZoneName": "منطقه 20",
                            "M1": "0",
                            "M5": "46,000,000",
                            "M12": "10,000,000",
                        },
                    }
                ],
                "SumRowData": {},
                "GridViewJSTotal": 1,
            },
            rows_count=1,
        )
        balance = KaraReportSnapshot.objects.create(
            report_key="account_balance",
            report_title="balance",
            fetched_at=timezone.now(),
            period_to="2026/07/28",
            raw_data={
                "Data": [
                    {
                        "Key": 1,
                        "Value": {
                            "PartnerCode": "10003001",
                            "PartnerName": "X",
                            "Month01": "0",
                            "Month02": "(1,000,000)",
                            "Month03": "0",
                            "Month04": "0",
                            "Month05": "0",
                            "Month06": "0",
                            "Month07": "0",
                            "Month08": "0",
                            "Month09": "0",
                            "Month10": "0",
                            "Month11": "0",
                            "Month12": "0",
                        },
                    }
                ],
                "SumRowData": {},
                "GridViewJSTotal": 1,
            },
            rows_count=1,
        )
        self.assertTrue(AnalyticsPipeline.process_snapshot(aging))
        self.assertTrue(AnalyticsPipeline.process_snapshot(balance))
        metric = ReceivableDailyMetric.objects.get()
        self.assertEqual(metric.total_outstanding, 56000000)
        self.assertEqual(metric.partner_balance_total, -1000000)
        summary = AnalyticsQueryService.receivables_summary()
        self.assertTrue(summary["available"])


class RegionMetricIdempotencyTests(TestCase):
    def test_stuff_group_region_not_accumulate_on_resync(self):
        from reports.models import RegionDailyMetric

        bdate = date(2026, 7, 28)
        payload = {
            "Data": [
                {
                    "Key": 1,
                    "Value": {
                        "City": "Tehran",
                        "Zone": "Z1",
                        "StuffGroupName": "Can",
                        "StuffCode": "1",
                        "StuffName": "Tuna",
                        "PureSalePrice": "1000000",
                        "NotPureSalePrice": "1100000",
                        "SaleReversionPrice": "0",
                        "DistributionReversionPrice": "0",
                        "OrderCount": "1",
                    },
                }
            ],
            "SumRowData": {},
            "GridViewJSTotal": 1,
        }
        snap = KaraReportSnapshot.objects.create(
            report_key="stuff_group_sale",
            report_title="sg",
            fetched_at=timezone.now(),
            period_to=bdate.isoformat(),
            raw_data=payload,
            rows_count=1,
        )
        AnalyticsPipeline.process_snapshot(snap)
        AnalyticsPipeline.process_snapshot(snap)
        city = RegionDailyMetric.objects.get(
            business_date=bdate,
            dimension_type=RegionDailyMetric.DIMENSION_CITY,
            dimension_code="تهران",
        )
        self.assertEqual(city.pure_sale, Decimal("1000000"))
        group = RegionDailyMetric.objects.get(
            business_date=bdate,
            dimension_type=RegionDailyMetric.DIMENSION_PRODUCT_GROUP,
            dimension_code="Can",
        )
        self.assertEqual(group.pure_sale, Decimal("1000000"))


class ActiveVisitorDistinctTests(TestCase):
    def test_active_visitors_are_distinct_not_person_days(self):
        from reports.services.dates import DateRange

        today = timezone.localdate()
        for i in range(3):
            d = today - timedelta(days=i)
            DailyBusinessMetric.objects.create(
                metric_date=d.isoformat(),
                business_date=d,
                source_report=f"v_{i}",
                total_sale=1000,
                total_pure_sale=900,
                order_count=1,
                active_visitors=10,
            )
            SalespersonDailyMetric.objects.create(
                business_date=d,
                personnel_code="100",
                personnel_name="Ali",
                total_sale=1000,
                is_active=True,
            )
            SalespersonDailyMetric.objects.create(
                business_date=d,
                personnel_code="200",
                personnel_name="Sara",
                total_sale=500,
                is_active=True,
            )
        dr = DateRange(today - timedelta(days=2), today)
        kpis = AnalyticsQueryService.company_kpis_for_range(dr)
        self.assertEqual(kpis["active_visitors"]["numeric"], 2.0)
