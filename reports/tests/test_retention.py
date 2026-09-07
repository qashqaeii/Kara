"""Retention: keep only live snapshots, do not accumulate JSON copies."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from reports.constants import SyncStatus
from reports.models import (
    DailyBusinessMetric,
    KaraRawResponse,
    KaraReportSnapshot,
    StuffGroupSaleSnapshot,
)
from reports.services.kara_client import KaraGridResponse
from reports.services.retention import prune_database, slim_stored_payload, snapshot_kind
from reports.services.sync import SyncOrchestrator


def _grid(total_sale: str = "1000") -> KaraGridResponse:
    return KaraGridResponse(
        report_key="visitor_sale",
        report_name="VisitorSaleReportGrid",
        report_title="t",
        total=1,
        count=1,
        data=[
            {
                "Key": 1,
                "Value": {
                    "VisitorCode": "200",
                    "VisitorName": "X",
                    "TotalSale": total_sale,
                },
            }
        ],
        sum_row_data={
            "TotalSale": total_sale,
            "TotalPureSale": total_sale,
            "OrderCountBasedOnFinalOrder": "1",
        },
        other_informations=[],
        page_count=1,
    )


class SnapshotKindTests(TestCase):
    def test_full_vs_daily(self):
        self.assertEqual(snapshot_kind("1405/01/01", "1405/05/10"), "full")
        self.assertEqual(snapshot_kind("1405/05/10", "1405/05/10"), "daily")
        self.assertEqual(snapshot_kind("", ""), "daily")

    def test_slim_drops_html(self):
        slim = slim_stored_payload({"Data": [1], "html": "<huge>", "parsed": {"a": 1}})
        self.assertNotIn("html", slim)
        self.assertEqual(slim["parsed"], {"a": 1})


class PruneDatabaseTests(TestCase):
    def test_keeps_latest_full_and_latest_daily_per_report(self):
        now = timezone.now()
        for i in range(4):
            KaraReportSnapshot.objects.create(
                report_key="stuff_group_sale",
                report_title="g",
                fetched_at=now - timedelta(minutes=10 - i),
                raw_data={"Data": [], "html": "<x>"},
                rows_count=1,
                period_from="1405/01/01",
                period_to="1405/05/09",
            )
        daily_old = KaraReportSnapshot.objects.create(
            report_key="stuff_group_sale",
            report_title="g",
            fetched_at=now - timedelta(minutes=2),
            raw_data={"Data": []},
            rows_count=1,
            period_from="1405/05/09",
            period_to="1405/05/09",
        )
        daily_new = KaraReportSnapshot.objects.create(
            report_key="stuff_group_sale",
            report_title="g",
            fetched_at=now,
            raw_data={"Data": []},
            rows_count=1,
            period_from="1405/05/10",
            period_to="1405/05/10",
        )
        KaraRawResponse.objects.create(
            report_key="stuff_group_sale",
            payload={"Data": list(range(100))},
            record_count=100,
        )
        StuffGroupSaleSnapshot.objects.create(
            snapshot=daily_old,
            row_key="stale",
            raw_data={"StuffCode": "1", "blob": "x" * 100},
        )

        stats = prune_database(vacuum=False)

        snaps = list(KaraReportSnapshot.objects.filter(report_key="stuff_group_sale"))
        self.assertEqual(len(snaps), 2)
        kinds = {snapshot_kind(s.period_from, s.period_to) for s in snaps}
        self.assertEqual(kinds, {"full", "daily"})
        self.assertTrue(KaraReportSnapshot.objects.filter(pk=daily_new.pk).exists())
        self.assertFalse(KaraReportSnapshot.objects.filter(pk=daily_old.pk).exists())
        self.assertEqual(KaraRawResponse.objects.count(), 0)
        self.assertGreaterEqual(stats["snapshots"], 4)


class SyncReplaceTests(TestCase):
    @patch("reports.services.sync.orchestrator.KaraClient")
    def test_changed_payload_replaces_snapshot(self, mock_client_cls):
        client = MagicMock()
        client.run_report.return_value = _grid("1000")
        client.get_session_info.return_value = {}
        mock_client_cls.return_value = client

        orch = SyncOrchestrator(client=client)
        job1 = orch.sync_report(
            "visitor_sale",
            triggered_by="test",
            from_date="1405/05/10",
            to_date="1405/05/10",
        )
        self.assertEqual(job1.status, SyncStatus.SUCCESS)
        self.assertEqual(
            KaraReportSnapshot.objects.filter(report_key="visitor_sale").count(), 1
        )
        first_id = KaraReportSnapshot.objects.get(report_key="visitor_sale").id

        client.run_report.return_value = _grid("2000")
        job2 = orch.sync_report(
            "visitor_sale",
            triggered_by="test",
            from_date="1405/05/10",
            to_date="1405/05/10",
        )
        self.assertEqual(job2.status, SyncStatus.SUCCESS)
        snaps = KaraReportSnapshot.objects.filter(report_key="visitor_sale")
        self.assertEqual(snaps.count(), 1)
        self.assertNotEqual(snaps.get().id, first_id)
        self.assertEqual(KaraRawResponse.objects.count(), 0)

    @patch("reports.services.sync.orchestrator.KaraClient")
    def test_ytd_and_daily_can_coexist(self, mock_client_cls):
        client = MagicMock()
        client.run_report.return_value = _grid("1000")
        client.get_session_info.return_value = {}
        mock_client_cls.return_value = client

        orch = SyncOrchestrator(client=client)
        orch.sync_report(
            "visitor_sale",
            triggered_by="test",
            from_date="1405/01/01",
            to_date="1405/05/10",
        )
        orch.sync_report(
            "visitor_sale",
            triggered_by="test",
            from_date="1405/05/10",
            to_date="1405/05/10",
        )
        snaps = KaraReportSnapshot.objects.filter(report_key="visitor_sale")
        self.assertEqual(snaps.count(), 2)
        kinds = {snapshot_kind(s.period_from, s.period_to) for s in snaps}
        self.assertEqual(kinds, {"full", "daily"})

    @patch("reports.services.sync.orchestrator.KaraClient")
    def test_metrics_survive_snapshot_replace(self, mock_client_cls):
        client = MagicMock()
        client.run_report.return_value = _grid("1000")
        client.get_session_info.return_value = {}
        mock_client_cls.return_value = client

        orch = SyncOrchestrator(client=client)
        orch.sync_report(
            "visitor_sale",
            triggered_by="test",
            from_date="1405/05/10",
            to_date="1405/05/10",
        )
        self.assertGreaterEqual(DailyBusinessMetric.objects.count(), 1)
        metric_count = DailyBusinessMetric.objects.count()

        client.run_report.return_value = _grid("1100")
        orch.sync_report(
            "visitor_sale",
            triggered_by="test",
            from_date="1405/05/10",
            to_date="1405/05/10",
        )
        self.assertEqual(DailyBusinessMetric.objects.count(), metric_count)
        self.assertEqual(
            KaraReportSnapshot.objects.filter(report_key="visitor_sale").count(), 1
        )
