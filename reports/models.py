from __future__ import annotations

from django.db import models
from django.utils import timezone

from django.contrib.auth.models import User

from reports.constants import (
    ALERT_SEVERITY_LABELS,
    ALERT_STATUS_LABELS,
    KARA_ROLE_LABELS,
    SYNC_STATUS_LABELS,
    AlertSeverity,
    AlertStatus,
    ConnectionStatus,
    KaraRole,
    SyncStatus,
)


class KaraConnection(models.Model):
    title = models.CharField(max_length=120, default="اتصال اصلی کارا")
    base_url = models.URLField(max_length=255)
    username = models.CharField(max_length=120, blank=True, default="")
    # Never store plaintext; use env/secret ref. Field kept for UI reference only.
    secret_reference = models.CharField(
        max_length=255,
        blank=True,
        default="env:KARA_PASSWORD",
        help_text="مرجع رمز؛ مثلاً env:KARA_PASSWORD",
    )
    is_active = models.BooleanField(default=True)
    connection_status = models.CharField(
        max_length=32,
        default=ConnectionStatus.UNKNOWN,
        db_index=True,
    )
    last_login_at = models.DateTimeField(null=True, blank=True)
    last_successful_sync_at = models.DateTimeField(null=True, blank=True)
    last_error_at = models.DateTimeField(null=True, blank=True)
    last_error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "اتصال کارا"
        verbose_name_plural = "اتصالات کارا"

    def __str__(self) -> str:
        return self.title

    @classmethod
    def get_active(cls) -> KaraConnection | None:
        return cls.objects.filter(is_active=True).order_by("-updated_at").first()


class KaraSyncJob(models.Model):
    report_key = models.CharField(max_length=100, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=[(s.value, SYNC_STATUS_LABELS[s]) for s in SyncStatus],
        default=SyncStatus.PENDING,
        db_index=True,
    )
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    requested_from_date = models.CharField(max_length=20, blank=True, default="")
    requested_to_date = models.CharField(max_length=20, blank=True, default="")
    page_count = models.PositiveIntegerField(default=0)
    received_count = models.PositiveIntegerField(default=0)
    inserted_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True, default="")
    triggered_by = models.CharField(max_length=50, default="manual")
    metadata = models.JSONField(default=dict, blank=True)
    duration_ms = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "وظیفه همگام‌سازی"
        verbose_name_plural = "وظایف همگام‌سازی"
        indexes = [
            models.Index(fields=["report_key", "-started_at"]),
            models.Index(fields=["status", "-started_at"]),
        ]

    def __str__(self) -> str:
        from reports.services.display import report_title, sync_status_label

        return f"{report_title(self.report_key)} [{sync_status_label(self.status)}]"

    @property
    def friendly_error(self) -> str:
        msg = (self.error_message or "").lower()
        if "منقضی" in self.error_message or "login" in msg or "html" in msg:
            return "نشست کارا منقضی شده است"
        if "ورود" in self.error_message or "auth" in msg:
            return "ورود به کارا ناموفق بود"
        if (
            "شبکه" in self.error_message
            or "ارتباط با سرور" in self.error_message
            or "connection" in msg
            or "timeout" in msg
        ):
            return "ارتباط با سرور کارا برقرار نشد"
        if "پردازش" in self.error_message or "json" in msg or "data" in msg:
            return "پاسخ گزارش قابل پردازش نبود"
        if self.status == SyncStatus.PARTIAL:
            return "همگام‌سازی ناقص انجام شد"
        return self.error_message or ""


class KaraSyncLog(models.Model):
    job = models.ForeignKey(
        KaraSyncJob, on_delete=models.CASCADE, related_name="logs"
    )
    level = models.CharField(max_length=20, default="info")
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    context = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["created_at"]


class KaraRawResponse(models.Model):
    job = models.ForeignKey(
        KaraSyncJob,
        on_delete=models.CASCADE,
        related_name="raw_responses",
        null=True,
        blank=True,
    )
    report_key = models.CharField(max_length=100, db_index=True)
    fetched_at = models.DateTimeField(default=timezone.now, db_index=True)
    payload = models.JSONField()
    record_count = models.PositiveIntegerField(default=0)
    checksum = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        ordering = ["-fetched_at"]
        verbose_name = "پاسخ خام کارا"
        verbose_name_plural = "پاسخ‌های خام کارا"


class KaraReportSnapshot(models.Model):
    """Normalized snapshot of a report fetch — primary read source for dashboard."""

    report_key = models.CharField(max_length=100, db_index=True, verbose_name="کلید گزارش")
    report_title = models.CharField(max_length=255, verbose_name="عنوان گزارش")
    fetched_at = models.DateTimeField(db_index=True, verbose_name="زمان دریافت")
    raw_data = models.JSONField(verbose_name="داده خام")
    rows_count = models.PositiveIntegerField(default=0, verbose_name="تعداد ردیف")
    personnel_code = models.CharField(
        max_length=50, blank=True, default="", db_index=True, verbose_name="کد پرسنلی"
    )
    personnel_name = models.CharField(
        max_length=255, blank=True, default="", verbose_name="نام پرسنلی"
    )
    sync_job = models.ForeignKey(
        KaraSyncJob,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="snapshots",
    )
    content_checksum = models.CharField(max_length=64, blank=True, default="", db_index=True)
    period_from = models.CharField(max_length=20, blank=True, default="")
    period_to = models.CharField(max_length=20, blank=True, default="")

    class Meta:
        ordering = ["-fetched_at"]
        verbose_name = "اسنپ‌شات گزارش کارا"
        verbose_name_plural = "اسنپ‌شات‌های گزارش کارا"
        indexes = [
            models.Index(fields=["report_key", "personnel_code", "-fetched_at"]),
        ]

    def __str__(self) -> str:
        from reports.services.dates import format_jalali_datetime

        suffix = f" — {self.personnel_name}" if self.personnel_code else ""
        return f"{self.report_title}{suffix} ({format_jalali_datetime(self.fetched_at)})"

    @property
    def sum_row_data(self) -> dict | None:
        data = self.raw_data.get("SumRowData")
        if isinstance(data, dict):
            return data
        return None

    @property
    def grid_total(self) -> int:
        return int(self.raw_data.get("GridViewJSTotal", 0) or 0)

    @property
    def is_filtered(self) -> bool:
        return bool(self.personnel_code)


class VisitorSaleSnapshot(models.Model):
    """Normalized visitor row — deduplicated by logical key."""

    sync_job = models.ForeignKey(
        KaraSyncJob, on_delete=models.SET_NULL, null=True, blank=True
    )
    report_date = models.CharField(max_length=20, blank=True, default="", db_index=True)
    visitor_code = models.CharField(max_length=50, db_index=True)
    visitor_name = models.CharField(max_length=255, blank=True, default="")
    head_visitor_code = models.CharField(max_length=50, blank=True, default="", db_index=True)
    head_visitor_name = models.CharField(max_length=255, blank=True, default="")
    total_sale = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    total_pure_sale = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    order_count = models.IntegerField(default=0)
    partner_count = models.IntegerField(default=0)
    distribution_reversion = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    sale_reversion = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    settlement_remainder = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    raw_data = models.JSONField(default=dict, blank=True)
    source_key = models.CharField(max_length=50, blank=True, default="")
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    last_sync_job = models.ForeignKey(
        KaraSyncJob,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="visitor_rows",
    )
    snapshot = models.ForeignKey(
        KaraReportSnapshot,
        on_delete=models.CASCADE,
        related_name="visitor_rows",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "اسنپ‌شات فروش ویزیتور"
        verbose_name_plural = "اسنپ‌شات‌های فروش ویزیتور"
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot", "visitor_code"],
                name="uniq_visitor_sale_per_snapshot",
            )
        ]
        indexes = [
            models.Index(fields=["visitor_code", "-last_seen_at"]),
            models.Index(fields=["head_visitor_code", "-last_seen_at"]),
        ]


class HeadVisitorSaleSnapshot(models.Model):
    sync_job = models.ForeignKey(
        KaraSyncJob, on_delete=models.SET_NULL, null=True, blank=True
    )
    report_date = models.CharField(max_length=20, blank=True, default="", db_index=True)
    head_visitor_code = models.CharField(max_length=50, db_index=True)
    head_visitor_name = models.CharField(max_length=255, blank=True, default="")
    total_sale = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    total_pure_sale = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    order_count = models.IntegerField(default=0)
    distribution_reversion = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    sale_reversion = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    settlement_remainder = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    raw_data = models.JSONField(default=dict, blank=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    snapshot = models.ForeignKey(
        KaraReportSnapshot,
        on_delete=models.CASCADE,
        related_name="head_visitor_rows",
        null=True,
        blank=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot", "head_visitor_code"],
                name="uniq_head_visitor_sale_per_snapshot",
            )
        ]


class StuffGroupSaleSnapshot(models.Model):
    sync_job = models.ForeignKey(
        KaraSyncJob, on_delete=models.SET_NULL, null=True, blank=True
    )
    row_key = models.CharField(max_length=120, blank=True, default="", db_index=True)
    group_name = models.CharField(max_length=255, blank=True, default="", db_index=True)
    sub_group_name = models.CharField(max_length=255, blank=True, default="")
    stuff_code = models.CharField(max_length=50, blank=True, default="", db_index=True)
    stuff_name = models.CharField(max_length=255, blank=True, default="")
    partner_code = models.CharField(max_length=50, blank=True, default="", db_index=True)
    partner_name = models.CharField(max_length=255, blank=True, default="")
    visitor_code = models.CharField(max_length=50, blank=True, default="", db_index=True)
    visitor_name = models.CharField(max_length=255, blank=True, default="")
    city = models.CharField(max_length=120, blank=True, default="")
    zone = models.CharField(max_length=120, blank=True, default="")
    route = models.CharField(max_length=255, blank=True, default="")
    pure_sale = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    not_pure_sale = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    pure_sale_quantity = models.IntegerField(default=0)
    order_count = models.IntegerField(default=0)
    partner_count = models.IntegerField(default=0)
    distribution_reversion = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    sale_reversion = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    raw_data = models.JSONField(default=dict, blank=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    snapshot = models.ForeignKey(
        KaraReportSnapshot,
        on_delete=models.CASCADE,
        related_name="stuff_group_rows",
        null=True,
        blank=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot", "row_key"],
                name="uniq_stuff_group_row_per_snapshot",
            )
        ]
        indexes = [
            models.Index(fields=["group_name", "-last_seen_at"]),
            models.Index(fields=["stuff_code", "-last_seen_at"]),
        ]


class MonthlyCompanySales(models.Model):
    """Company-wide monthly sales from MontlyReportGrid SumRowData."""

    fiscal_year = models.PositiveIntegerField(unique=True, db_index=True)
    monthly_totals = models.JSONField(default=dict, blank=True)
    total_ytd = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    snapshot = models.ForeignKey(
        KaraReportSnapshot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="monthly_company_sales",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "فروش ماهانه شرکت"
        verbose_name_plural = "فروش ماهانه شرکت"
        ordering = ["-fiscal_year"]

    def __str__(self) -> str:
        return f"فروش ماهانه {self.fiscal_year}"


class MonthlySaleDetailSnapshot(models.Model):
    """Drill-down row from MontlyReportGrid — partner × visitor × stuff × 12 months."""

    fiscal_year = models.PositiveIntegerField(db_index=True)
    row_key = models.CharField(max_length=120, db_index=True)
    partner_code = models.CharField(max_length=50, blank=True, default="")
    partner_name = models.CharField(max_length=255, blank=True, default="")
    visitor_code = models.CharField(max_length=50, blank=True, default="")
    visitor_name = models.CharField(max_length=255, blank=True, default="")
    stuff_code = models.CharField(max_length=50, blank=True, default="", db_index=True)
    stuff_name = models.CharField(max_length=255, blank=True, default="")
    stuff_group_name = models.CharField(max_length=255, blank=True, default="")
    stuff_sub_group_name = models.CharField(max_length=255, blank=True, default="")
    partner_zone_route = models.CharField(max_length=512, blank=True, default="")
    monthly_totals = models.JSONField(default=dict, blank=True)
    raw_data = models.JSONField(default=dict, blank=True)
    snapshot = models.ForeignKey(
        KaraReportSnapshot,
        on_delete=models.CASCADE,
        related_name="monthly_sale_rows",
        null=True,
        blank=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot", "row_key"],
                name="uniq_monthly_sale_row_per_snapshot",
            )
        ]
        indexes = [
            models.Index(fields=["fiscal_year", "stuff_code"]),
        ]


class SaleReversionSnapshot(models.Model):
    sync_job = models.ForeignKey(
        KaraSyncJob, on_delete=models.SET_NULL, null=True, blank=True
    )
    reversion_code = models.CharField(max_length=50, blank=True, default="", db_index=True)
    order_code = models.CharField(max_length=50, blank=True, default="", db_index=True)
    partner_code = models.CharField(max_length=50, blank=True, default="", db_index=True)
    partner_name = models.CharField(max_length=255, blank=True, default="")
    reversion_amount = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    order_date = models.CharField(max_length=20, blank=True, default="")
    reversion_date = models.CharField(max_length=20, blank=True, default="")
    raw_data = models.JSONField(default=dict, blank=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    snapshot = models.ForeignKey(
        KaraReportSnapshot,
        on_delete=models.CASCADE,
        related_name="sale_reversion_rows",
        null=True,
        blank=True,
    )


class DistributionReversionSnapshot(models.Model):
    sync_job = models.ForeignKey(
        KaraSyncJob, on_delete=models.SET_NULL, null=True, blank=True
    )
    total_code = models.CharField(max_length=50, blank=True, default="", db_index=True)
    partner_code = models.CharField(max_length=50, blank=True, default="", db_index=True)
    partner_name = models.CharField(max_length=255, blank=True, default="")
    driver_name = models.CharField(max_length=255, blank=True, default="")
    amount = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    order_date = models.CharField(max_length=20, blank=True, default="")
    raw_data = models.JSONField(default=dict, blank=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    snapshot = models.ForeignKey(
        KaraReportSnapshot,
        on_delete=models.CASCADE,
        related_name="distribution_reversion_rows",
        null=True,
        blank=True,
    )


class SaleOrderSnapshot(models.Model):
    """Normalized invoice row from sale_orders (080501)."""

    sync_job = models.ForeignKey(
        KaraSyncJob, on_delete=models.SET_NULL, null=True, blank=True
    )
    order_code = models.CharField(max_length=50, db_index=True)
    order_pre_code = models.CharField(max_length=50, blank=True, default="")
    order_date = models.CharField(max_length=20, blank=True, default="")
    partner_code = models.CharField(max_length=50, blank=True, default="", db_index=True)
    partner_name = models.CharField(max_length=255, blank=True, default="")
    visitor_code = models.CharField(max_length=50, blank=True, default="", db_index=True)
    visitor_name = models.CharField(max_length=255, blank=True, default="")
    order_final_price = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    finalized_cost = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    sale_reversion_amount = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    stuffs_quantity_sum = models.IntegerField(default=0)
    pre_order_status = models.CharField(max_length=40, blank=True, default="", db_index=True)
    raw_data = models.JSONField(default=dict, blank=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    snapshot = models.ForeignKey(
        KaraReportSnapshot,
        on_delete=models.CASCADE,
        related_name="sale_order_rows",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "فاکتور"
        verbose_name_plural = "فاکتورها"
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot", "order_code"],
                name="uniq_sale_order_per_snapshot",
            )
        ]
        indexes = [
            models.Index(fields=["visitor_code", "-last_seen_at"]),
            models.Index(fields=["order_date"]),
        ]

    def __str__(self) -> str:
        label = self.order_pre_code or self.order_code
        partner = (self.partner_name or "").strip() or "—"
        return f"فاکتور {label} — {partner}"


class SaleOrderLineSnapshot(models.Model):
    """Per-product line from sale_orders_with_stuffs (OrdersWithDetail grid)."""

    sync_job = models.ForeignKey(
        KaraSyncJob, on_delete=models.SET_NULL, null=True, blank=True
    )
    snapshot = models.ForeignKey(
        KaraReportSnapshot,
        on_delete=models.CASCADE,
        related_name="sale_order_line_rows",
        null=True,
        blank=True,
    )
    row_key = models.CharField(max_length=160, db_index=True)
    order_code = models.CharField(max_length=50, db_index=True)
    order_pre_code = models.CharField(max_length=50, blank=True, default="")
    order_date = models.CharField(max_length=20, blank=True, default="")
    partner_code = models.CharField(max_length=50, blank=True, default="", db_index=True)
    partner_name = models.CharField(max_length=255, blank=True, default="")
    visitor_code = models.CharField(max_length=50, blank=True, default="", db_index=True)
    visitor_name = models.CharField(max_length=255, blank=True, default="")
    stuff_code = models.CharField(max_length=50, blank=True, default="", db_index=True)
    stuff_name = models.CharField(max_length=255, blank=True, default="")
    stuff_group_name = models.CharField(max_length=255, blank=True, default="")
    stuff_sub_group_name = models.CharField(max_length=255, blank=True, default="")
    package_name = models.CharField(max_length=120, blank=True, default="")
    unit_name = models.CharField(max_length=120, blank=True, default="")
    package_quantity = models.IntegerField(default=0)
    stuff_quantity = models.IntegerField(default=0)
    unit_fee = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    line_amount = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    order_final_price = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    raw_data = models.JSONField(default=dict, blank=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot", "row_key"],
                name="uniq_sale_order_line_per_snapshot",
            )
        ]
        indexes = [
            models.Index(fields=["order_code", "snapshot"]),
            models.Index(fields=["visitor_code", "order_code"]),
        ]
        verbose_name = "ردیف اقلام فاکتور"
        verbose_name_plural = "ردیف‌های اقلام فاکتور"

    def __str__(self) -> str:
        stuff = (self.stuff_name or self.stuff_code or "—").strip()
        return f"{self.order_code} / {stuff}"


class SaleStuffSnapshot(models.Model):
    """Normalized product row from sale_stuffs (080503)."""

    sync_job = models.ForeignKey(
        KaraSyncJob, on_delete=models.SET_NULL, null=True, blank=True
    )
    stuff_code = models.CharField(max_length=50, db_index=True)
    stuff_name = models.CharField(max_length=255, blank=True, default="")
    stuff_group_name = models.CharField(max_length=255, blank=True, default="", db_index=True)
    stuff_sub_group_name = models.CharField(max_length=255, blank=True, default="")
    sale_quantity = models.IntegerField(default=0)
    sale_amount = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    sale_reversion_quantity = models.IntegerField(default=0)
    sale_reversion_amount = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    pure_sale = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    raw_data = models.JSONField(default=dict, blank=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    snapshot = models.ForeignKey(
        KaraReportSnapshot,
        on_delete=models.CASCADE,
        related_name="sale_stuff_rows",
        null=True,
        blank=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot", "stuff_code"],
                name="uniq_sale_stuff_per_snapshot",
            )
        ]
        indexes = [
            models.Index(fields=["stuff_group_name", "-last_seen_at"]),
        ]


class ProfitDailyMetric(models.Model):
    """Gross profit from sale_orders — separate from visitor_sale company KPIs."""

    business_date = models.DateField(db_index=True, unique=True)
    invoice_count = models.IntegerField(default=0)
    invoice_revenue = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    finalized_cost = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    sale_reversion_amount = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    gross_profit = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    gross_margin_rate = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    snapshot = models.ForeignKey(
        KaraReportSnapshot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="profit_daily_metrics",
    )
    calculated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-business_date"]
        verbose_name = "شاخص سود روزانه"
        verbose_name_plural = "شاخص‌های سود روزانه"


class CompanyProfitLossMetric(models.Model):
    """Company P&L from accounting LostBenefit print report (080106)."""

    period_from = models.CharField(max_length=20, blank=True, default="")
    period_to = models.CharField(max_length=20, blank=True, default="", db_index=True)
    business_date = models.DateField(db_index=True, unique=True)
    net_pure_sale = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    cost_of_goods_sold = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    gross_profit = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    operating_profit = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    net_profit = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    gross_margin_rate = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    line_items = models.JSONField(default=dict, blank=True)
    snapshot = models.ForeignKey(
        KaraReportSnapshot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="profit_loss_metrics",
    )
    calculated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-business_date", "-period_to"]
        verbose_name = "شاخص سود و زیان شرکت"
        verbose_name_plural = "شاخص‌های سود و زیان شرکت"


class AccountBalanceSnapshot(models.Model):
    """Partner monthly balance from AccountBallance_PartnersAndPersonnels (080533)."""

    sync_job = models.ForeignKey(
        KaraSyncJob, on_delete=models.SET_NULL, null=True, blank=True
    )
    snapshot = models.ForeignKey(
        KaraReportSnapshot,
        on_delete=models.CASCADE,
        related_name="account_balance_rows",
        null=True,
        blank=True,
    )
    partner_code = models.CharField(max_length=50, db_index=True)
    partner_name = models.CharField(max_length=255, blank=True, default="")
    partner_legal_name = models.CharField(max_length=255, blank=True, default="")
    monthly_balances = models.JSONField(default=dict, blank=True)
    total_balance = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    raw_data = models.JSONField(default=dict, blank=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot", "partner_code"],
                name="uniq_account_balance_per_snapshot",
            )
        ]
        indexes = [
            models.Index(fields=["partner_code", "-last_seen_at"]),
        ]
        verbose_name = "مانده حساب مشتری"
        verbose_name_plural = "مانده‌های حساب مشتری"


class ReceivableAgingSnapshot(models.Model):
    """Aging bucket row from SaleOrderRemainPriceGrid (080534)."""

    sync_job = models.ForeignKey(
        KaraSyncJob, on_delete=models.SET_NULL, null=True, blank=True
    )
    snapshot = models.ForeignKey(
        KaraReportSnapshot,
        on_delete=models.CASCADE,
        related_name="receivable_aging_rows",
        null=True,
        blank=True,
    )
    row_key = models.CharField(max_length=120, db_index=True)
    visitor_code = models.CharField(max_length=50, blank=True, default="", db_index=True)
    visitor_name = models.CharField(max_length=255, blank=True, default="")
    partner_code = models.CharField(max_length=50, blank=True, default="")
    partner_name = models.CharField(max_length=255, blank=True, default="")
    city_name = models.CharField(max_length=120, blank=True, default="", db_index=True)
    zone_name = models.CharField(max_length=120, blank=True, default="", db_index=True)
    route_name = models.CharField(max_length=255, blank=True, default="")
    bucket_amounts = models.JSONField(default=dict, blank=True)
    total_outstanding = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    raw_data = models.JSONField(default=dict, blank=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot", "row_key"],
                name="uniq_receivable_aging_per_snapshot",
            )
        ]
        indexes = [
            models.Index(fields=["visitor_code", "-last_seen_at"]),
            models.Index(fields=["city_name", "-last_seen_at"]),
        ]
        verbose_name = "ردیف سنی معوقات"
        verbose_name_plural = "ردیف‌های سنی معوقات"


class ReceivableDailyMetric(models.Model):
    """Aggregated receivables aging buckets for dashboard/TV."""

    business_date = models.DateField(db_index=True, unique=True)
    bucket_totals = models.JSONField(default=dict, blank=True)
    total_outstanding = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    row_count = models.IntegerField(default=0)
    partner_balance_total = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    partner_count = models.IntegerField(default=0)
    snapshot = models.ForeignKey(
        KaraReportSnapshot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="receivable_daily_metrics",
    )
    calculated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-business_date"]
        verbose_name = "شاخص روزانه مطالبات"
        verbose_name_plural = "شاخص‌های روزانه مطالبات"


class ProductDailyMetric(models.Model):
    """Product-level sales from sale_stuffs — no per-product COGS."""

    business_date = models.DateField(db_index=True)
    stuff_code = models.CharField(max_length=50, db_index=True)
    stuff_name = models.CharField(max_length=255, blank=True, default="")
    stuff_group_name = models.CharField(max_length=255, blank=True, default="")
    sale_quantity = models.IntegerField(default=0)
    sale_amount = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    sale_reversion_quantity = models.IntegerField(default=0)
    sale_reversion_amount = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    pure_sale = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    snapshot = models.ForeignKey(
        KaraReportSnapshot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="product_daily_metrics",
    )
    calculated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("business_date", "stuff_code")]
        ordering = ["-business_date", "-pure_sale"]
        verbose_name = "شاخص روزانه کالا"
        verbose_name_plural = "شاخص‌های روزانه کالا"


class DailyBusinessMetric(models.Model):
    """Precomputed daily company metrics from primary KPI source (CompanyDailyMetric)."""

    metric_date = models.CharField(max_length=20, db_index=True)
    business_date = models.DateField(null=True, blank=True, db_index=True)
    source_report = models.CharField(max_length=100, default="visitor_sale")
    total_sale = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    total_pure_sale = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    order_count = models.IntegerField(default=0)
    distribution_reversion = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    sale_reversion = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    settlement_remainder = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    total_reversion = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    reversion_rate = models.DecimalField(
        max_digits=8, decimal_places=2, default=0
    )
    average_order_value = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    active_visitors = models.IntegerField(default=0)
    computed_at = models.DateTimeField(auto_now=True)
    snapshot = models.ForeignKey(
        KaraReportSnapshot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        unique_together = [("metric_date", "source_report")]
        ordering = ["-metric_date", "-business_date"]
        verbose_name = "شاخص روزانه کسب‌وکار"
        verbose_name_plural = "شاخص‌های روزانه کسب‌وکار"

    @property
    def active_salespersons(self) -> int:
        return self.active_visitors


class AnalyticsPeriod(models.Model):
    """Tracks analytics computation status per report and business date."""

    report_key = models.CharField(max_length=100, db_index=True)
    business_date = models.DateField(db_index=True)
    status = models.CharField(
        max_length=20,
        choices=[(s.value, SYNC_STATUS_LABELS[s]) for s in SyncStatus],
        default=SyncStatus.PENDING,
        db_index=True,
    )
    snapshot = models.ForeignKey(
        KaraReportSnapshot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="analytics_periods",
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = [("report_key", "business_date")]
        ordering = ["-business_date", "report_key"]
        verbose_name = "دوره تحلیلی"
        verbose_name_plural = "دوره‌های تحلیلی"

    def __str__(self) -> str:
        return f"{self.report_key} @ {self.business_date}"


class SalespersonDailyMetric(models.Model):
    business_date = models.DateField(db_index=True)
    personnel_code = models.CharField(max_length=50, db_index=True)
    personnel_name = models.CharField(max_length=255, blank=True, default="")
    supervisor_code = models.CharField(max_length=50, blank=True, default="", db_index=True)
    supervisor_name = models.CharField(max_length=255, blank=True, default="")
    total_sale = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    total_pure_sale = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    final_order_count = models.IntegerField(default=0)
    preorder_count = models.IntegerField(default=0)
    average_order_value = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    sale_reversion = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    distribution_reversion = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    reversion_rate = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    snapshot = models.ForeignKey(
        KaraReportSnapshot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="salesperson_daily_metrics",
    )
    calculated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("business_date", "personnel_code")]
        ordering = ["-business_date", "-total_sale"]
        verbose_name = "شاخص روزانه فروشنده"
        verbose_name_plural = "شاخص‌های روزانه فروشنده"

    def __str__(self) -> str:
        return f"{self.personnel_code} @ {self.business_date}"


class SupervisorDailyMetric(models.Model):
    business_date = models.DateField(db_index=True)
    supervisor_code = models.CharField(max_length=50, db_index=True)
    supervisor_name = models.CharField(max_length=255, blank=True, default="")
    total_sale = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    total_pure_sale = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    final_order_count = models.IntegerField(default=0)
    salesperson_count = models.IntegerField(default=0)
    active_salesperson_count = models.IntegerField(default=0)
    average_sale_per_person = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    reversion_rate = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    snapshot = models.ForeignKey(
        KaraReportSnapshot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supervisor_daily_metrics",
    )

    class Meta:
        unique_together = [("business_date", "supervisor_code")]
        ordering = ["-business_date", "-total_sale"]
        verbose_name = "شاخص روزانه سرپرست"
        verbose_name_plural = "شاخص‌های روزانه سرپرست"

    def __str__(self) -> str:
        return f"{self.supervisor_code} @ {self.business_date}"


class RegionDailyMetric(models.Model):
    DIMENSION_CITY = "city"
    DIMENSION_ZONE = "zone"
    DIMENSION_PRODUCT_GROUP = "product_group"
    DIMENSION_TYPE_CHOICES = [
        (DIMENSION_CITY, DIMENSION_CITY),
        (DIMENSION_ZONE, DIMENSION_ZONE),
        (DIMENSION_PRODUCT_GROUP, DIMENSION_PRODUCT_GROUP),
    ]

    business_date = models.DateField(db_index=True)
    dimension_type = models.CharField(max_length=32, choices=DIMENSION_TYPE_CHOICES, db_index=True)
    dimension_code = models.CharField(max_length=120, db_index=True)
    dimension_name = models.CharField(max_length=255, blank=True, default="")
    total_sale = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    pure_sale = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    order_count = models.IntegerField(default=0)
    reversion_amount = models.DecimalField(max_digits=20, decimal_places=0, default=0)
    snapshot = models.ForeignKey(
        KaraReportSnapshot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="region_daily_metrics",
    )

    class Meta:
        unique_together = [("business_date", "dimension_type", "dimension_code")]
        ordering = ["-business_date", "-pure_sale"]
        verbose_name = "شاخص روزانه منطقه"
        verbose_name_plural = "شاخص‌های روزانه منطقه"

    def __str__(self) -> str:
        return f"{self.dimension_type}:{self.dimension_code} @ {self.business_date}"


class BackfillRun(models.Model):
    from_date = models.DateField()
    to_date = models.DateField()
    reports = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[(s.value, SYNC_STATUS_LABELS[s]) for s in SyncStatus],
        default=SyncStatus.PENDING,
        db_index=True,
    )
    current_date = models.DateField(null=True, blank=True)
    completed_dates = models.JSONField(default=list, blank=True)
    dry_run = models.BooleanField(default=False)
    delay_seconds = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "اجرای بک‌فیل"
        verbose_name_plural = "اجراهای بک‌فیل"

    def __str__(self) -> str:
        return f"Backfill {self.from_date} → {self.to_date} [{self.status}]"


class ManagementAlert(models.Model):
    severity = models.CharField(
        max_length=20,
        choices=[(s.value, ALERT_SEVERITY_LABELS[s]) for s in AlertSeverity],
        default=AlertSeverity.INFO,
        db_index=True,
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    metric = models.CharField(max_length=100, blank=True, default="")
    current_value = models.CharField(max_length=100, blank=True, default="")
    expected_value = models.CharField(max_length=100, blank=True, default="")
    entity = models.CharField(max_length=255, blank=True, default="")
    rule_key = models.CharField(max_length=100, blank=True, default="", db_index=True)
    entity_type = models.CharField(max_length=50, blank=True, default="", db_index=True)
    entity_code = models.CharField(max_length=120, blank=True, default="", db_index=True)
    period = models.CharField(max_length=50, blank=True, default="", db_index=True)
    detected_at = models.DateTimeField(auto_now_add=True, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=[(s.value, ALERT_STATUS_LABELS[s]) for s in AlertStatus],
        default=AlertStatus.OPEN,
        db_index=True,
    )
    detail_url = models.CharField(max_length=255, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-detected_at"]
        verbose_name = "هشدار مدیریتی"
        verbose_name_plural = "هشدارهای مدیریتی"
        unique_together = [("rule_key", "entity_type", "entity_code", "period")]


class UserKaraIdentity(models.Model):
    """
    Links a Django user to Kara personnel for row-level access control.

    Enforcement happens in query layer (AccessControlService), not UI-only.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="kara_identity",
    )
    personnel_code = models.CharField(max_length=50, blank=True, default="", db_index=True)
    role = models.CharField(
        max_length=32,
        choices=[(r.value, KARA_ROLE_LABELS[r]) for r in KaraRole],
        default=KaraRole.VIEWER,
        db_index=True,
    )
    supervisor_code = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="برای سرپرست: کد سرپرست در کارا",
    )
    allowed_city_codes = models.JSONField(default=list, blank=True)
    allowed_zone_codes = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "هویت کاربر در کارا"
        verbose_name_plural = "هویت‌های کاربر در کارا"

    def __str__(self) -> str:
        from reports.services.display import role_label

        return f"{self.user.username} ({role_label(self.role)})"

    @property
    def is_executive(self) -> bool:
        return self.role in {
            KaraRole.SYSTEM_ADMIN,
            KaraRole.EXECUTIVE_MANAGER,
            KaraRole.SALES_MANAGER,
        }

    @property
    def is_tv_display(self) -> bool:
        return self.role == KaraRole.TV_DISPLAY


class DashboardPreference(models.Model):
    key = models.CharField(max_length=100, unique=True)
    value = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class DashboardRefreshLog(models.Model):
    """Legacy refresh log — kept for backward compatibility with auto_refresh."""

    STATUS_IDLE = "idle"
    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_ERROR = "error"
    STATUS_CHOICES = [
        (STATUS_IDLE, "آماده"),
        (STATUS_RUNNING, "در حال اجرا"),
        (STATUS_SUCCESS, "موفق"),
        (STATUS_ERROR, "خطا"),
    ]

    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_IDLE)
    reports_refreshed = models.PositiveSmallIntegerField(default=0)
    error_message = models.TextField(blank=True, default="")
    triggered_by = models.CharField(max_length=50, default="auto", verbose_name="منبع")

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "لاگ بروزرسانی"
        verbose_name_plural = "لاگ‌های بروزرسانی"

    @classmethod
    def latest(cls) -> DashboardRefreshLog | None:
        return cls.objects.first()


class BaleUserIdentity(models.Model):
    """Links a Bale messenger user to a Django account."""

    bale_user_id = models.BigIntegerField(unique=True, db_index=True)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="bale_identity",
    )
    is_blocked = models.BooleanField(default=False)
    failed_login_count = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_login_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "هویت بله"
        verbose_name_plural = "هویت‌های بله"

    def __str__(self) -> str:
        return f"Bale {self.bale_user_id} → {self.user.username}"


class BotVisitorCredential(models.Model):
    """
    Dedicated bot login — independent from any dashboard login.

    Visitors authenticate with personnel_code + bot password.
    Password is stored hashed (Django hashers); never logged or shown after set.
    """

    personnel_code = models.CharField(max_length=50, unique=True, db_index=True)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="bot_credential",
    )
    password = models.CharField(max_length=128)
    display_name = models.CharField(max_length=255, blank=True, default="")
    is_active = models.BooleanField(default=True)
    must_change_password = models.BooleanField(default=False)
    password_changed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "اعتبار ورود ربات ویزیتور"
        verbose_name_plural = "اعتبارهای ورود ربات ویزیتور"

    def __str__(self) -> str:
        return f"{self.personnel_code} ({self.display_name or self.user.username})"

    def set_password(self, raw_password: str) -> None:
        from django.contrib.auth.hashers import make_password

        self.password = make_password(raw_password)
        self.password_changed_at = timezone.now()
        self.must_change_password = False

    def check_password(self, raw_password: str) -> bool:
        from django.contrib.auth.hashers import check_password

        return check_password(raw_password, self.password)


class BotConversationState(models.Model):
    """Persistent UI/flow state for Bale bot (no secrets)."""

    bale_user_id = models.BigIntegerField(unique=True, db_index=True)
    flow_state = models.CharField(max_length=50, blank=True, default="")
    nav_stack = models.JSONField(default=list, blank=True)
    menu_message_id = models.BigIntegerField(null=True, blank=True)
    menu_chat_id = models.BigIntegerField(null=True, blank=True)
    context = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "وضعیت گفتگوی ربات"
        verbose_name_plural = "وضعیت‌های گفتگوی ربات"


class BotActivityLog(models.Model):
    bale_user_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bot_activity_logs",
    )
    action = models.CharField(max_length=50, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "لاگ فعالیت ربات"
        verbose_name_plural = "لاگ‌های فعالیت ربات"


class BotNotificationEvent(models.Model):
    event_type = models.CharField(max_length=50, db_index=True)
    entity_type = models.CharField(max_length=50, db_index=True)
    entity_code = models.CharField(max_length=100, db_index=True)
    visitor_code = models.CharField(max_length=50, blank=True, default="", db_index=True)
    old_value = models.CharField(max_length=255, blank=True, default="")
    new_value = models.CharField(max_length=255, blank=True, default="")
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event_type", "entity_type", "entity_code", "new_value"],
                name="uniq_bot_notification_event",
            )
        ]
        verbose_name = "رویداد اعلان ربات"
        verbose_name_plural = "رویدادهای اعلان ربات"


class BotInvoiceWatchState(models.Model):
    """Tracks last known invoice state for change notifications."""

    order_code = models.CharField(max_length=50, unique=True, db_index=True)
    visitor_code = models.CharField(max_length=50, blank=True, default="", db_index=True)
    status_key = models.CharField(max_length=100, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "ردیاب وضعیت فاکتور"
        verbose_name_plural = "ردیابی وضعیت فاکتورها"


class BotUserNotification(models.Model):
    """Per-user notification inbox for the Bale bot."""

    CATEGORY_INVOICE = "invoice"
    CATEGORY_SYNC = "sync"
    CATEGORY_SETTLEMENT = "settlement"
    CATEGORY_SYSTEM = "system"

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="bot_notifications",
        null=True,
        blank=True,
    )
    bale_user_id = models.BigIntegerField(db_index=True)
    category = models.CharField(max_length=30, db_index=True)
    event_type = models.CharField(max_length=50, db_index=True)
    title = models.CharField(max_length=255)
    body = models.TextField()
    entity_type = models.CharField(max_length=50, blank=True, default="")
    entity_code = models.CharField(max_length=100, blank=True, default="", db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    pushed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["bale_user_id", "is_read", "-created_at"]),
            models.Index(fields=["bale_user_id", "category", "is_read"]),
        ]
        verbose_name = "اعلان کاربر ربات"
        verbose_name_plural = "اعلان‌های کاربران ربات"
