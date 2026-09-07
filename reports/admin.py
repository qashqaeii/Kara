from django.contrib import admin

from reports.models import (
    AnalyticsPeriod,
    BackfillRun,
    BaleUserIdentity,
    BotVisitorCredential,
    CompanyProfitLossMetric,
    DashboardRefreshLog,
    DailyBusinessMetric,
    KaraConnection,
    KaraRawResponse,
    KaraReportSnapshot,
    KaraSyncJob,
    KaraSyncLog,
    ManagementAlert,
    ReceivableDailyMetric,
    RegionDailyMetric,
    SaleOrderLineSnapshot,
    SaleOrderSnapshot,
    SalespersonDailyMetric,
    SupervisorDailyMetric,
    UserKaraIdentity,
)


@admin.register(KaraConnection)
class KaraConnectionAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "base_url",
        "connection_status",
        "last_successful_sync_at",
        "is_active",
    )
    readonly_fields = ("last_login_at", "last_successful_sync_at", "last_error_at", "created_at", "updated_at")


@admin.register(KaraSyncJob)
class KaraSyncJobAdmin(admin.ModelAdmin):
    list_display = (
        "report_key",
        "status",
        "started_at",
        "received_count",
        "inserted_count",
        "skipped_count",
        "triggered_by",
    )
    list_filter = ("status", "report_key", "triggered_by")
    readonly_fields = ("started_at", "finished_at", "metadata")


@admin.register(KaraSyncLog)
class KaraSyncLogAdmin(admin.ModelAdmin):
    list_display = ("job", "level", "message", "created_at")
    list_filter = ("level",)


@admin.register(KaraRawResponse)
class KaraRawResponseAdmin(admin.ModelAdmin):
    list_display = ("report_key", "fetched_at", "record_count", "checksum")
    list_filter = ("report_key",)


@admin.register(KaraReportSnapshot)
class KaraReportSnapshotAdmin(admin.ModelAdmin):
    list_display = ("report_key", "report_title", "personnel_code", "fetched_at", "rows_count")
    list_filter = ("report_key",)
    search_fields = ("report_key", "report_title", "personnel_code", "personnel_name")
    readonly_fields = ("fetched_at", "raw_data", "rows_count", "content_checksum")


@admin.register(CompanyProfitLossMetric)
class CompanyProfitLossMetricAdmin(admin.ModelAdmin):
    list_display = (
        "business_date",
        "net_pure_sale",
        "cost_of_goods_sold",
        "operating_profit",
        "net_profit",
        "gross_margin_rate",
    )


@admin.register(ReceivableDailyMetric)
class ReceivableDailyMetricAdmin(admin.ModelAdmin):
    list_display = (
        "business_date",
        "total_outstanding",
        "partner_balance_total",
        "partner_count",
        "row_count",
    )


@admin.register(DailyBusinessMetric)
class DailyBusinessMetricAdmin(admin.ModelAdmin):
    list_display = (
        "metric_date",
        "business_date",
        "total_sale",
        "order_count",
        "active_visitors",
        "reversion_rate",
        "computed_at",
    )
    list_filter = ("source_report",)


@admin.register(ManagementAlert)
class ManagementAlertAdmin(admin.ModelAdmin):
    list_display = (
        "severity",
        "title",
        "rule_key",
        "entity_type",
        "entity_code",
        "period",
        "status",
        "detected_at",
    )
    list_filter = ("severity", "status", "rule_key", "entity_type")
    search_fields = ("title", "entity", "entity_code", "rule_key")


@admin.register(AnalyticsPeriod)
class AnalyticsPeriodAdmin(admin.ModelAdmin):
    list_display = ("report_key", "business_date", "status", "snapshot")
    list_filter = ("report_key", "status")
    readonly_fields = ("metadata",)


@admin.register(SalespersonDailyMetric)
class SalespersonDailyMetricAdmin(admin.ModelAdmin):
    list_display = (
        "business_date",
        "personnel_code",
        "personnel_name",
        "total_sale",
        "final_order_count",
        "is_active",
        "calculated_at",
    )
    list_filter = ("is_active", "business_date")
    search_fields = ("personnel_code", "personnel_name", "supervisor_code")


@admin.register(SupervisorDailyMetric)
class SupervisorDailyMetricAdmin(admin.ModelAdmin):
    list_display = (
        "business_date",
        "supervisor_code",
        "supervisor_name",
        "total_sale",
        "salesperson_count",
        "active_salesperson_count",
    )
    list_filter = ("business_date",)
    search_fields = ("supervisor_code", "supervisor_name")


@admin.register(RegionDailyMetric)
class RegionDailyMetricAdmin(admin.ModelAdmin):
    list_display = (
        "business_date",
        "dimension_type",
        "dimension_code",
        "dimension_name",
        "pure_sale",
        "order_count",
    )
    list_filter = ("dimension_type", "business_date")
    search_fields = ("dimension_code", "dimension_name")


@admin.register(BackfillRun)
class BackfillRunAdmin(admin.ModelAdmin):
    list_display = (
        "from_date",
        "to_date",
        "status",
        "current_date",
        "dry_run",
        "created_at",
        "updated_at",
    )
    list_filter = ("status", "dry_run")
    readonly_fields = ("completed_dates", "created_at", "updated_at")


@admin.register(UserKaraIdentity)
class UserKaraIdentityAdmin(admin.ModelAdmin):
    list_display = ("user", "personnel_code", "role", "supervisor_code", "is_active")
    list_filter = ("role", "is_active")
    search_fields = ("user__username", "personnel_code", "supervisor_code")


@admin.register(BotVisitorCredential)
class BotVisitorCredentialAdmin(admin.ModelAdmin):
    list_display = (
        "personnel_code",
        "display_name",
        "user",
        "is_active",
        "password_changed_at",
        "updated_at",
    )
    list_filter = ("is_active",)
    search_fields = ("personnel_code", "display_name", "user__username")
    readonly_fields = ("password", "password_changed_at", "created_at", "updated_at")
    actions = ["deactivate_credentials"]

    @admin.action(description="غیرفعال کردن دسترسی ربات")
    def deactivate_credentials(self, request, queryset):
        queryset.update(is_active=False)


@admin.register(BaleUserIdentity)
class BaleUserIdentityAdmin(admin.ModelAdmin):
    list_display = (
        "bale_user_id",
        "user",
        "is_blocked",
        "last_login_at",
        "failed_login_count",
    )
    list_filter = ("is_blocked",)
    search_fields = ("bale_user_id", "user__username", "user__kara_identity__personnel_code")
    readonly_fields = ("created_at", "updated_at")


@admin.register(SaleOrderSnapshot)
class SaleOrderSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "order_code",
        "order_pre_code",
        "order_date",
        "partner_name",
        "visitor_name",
        "order_final_price",
        "stuffs_quantity_sum",
        "line_items_count",
        "last_seen_at",
    )
    list_filter = ("order_date", "snapshot")
    search_fields = (
        "order_code",
        "order_pre_code",
        "partner_name",
        "partner_code",
        "visitor_code",
        "visitor_name",
    )
    readonly_fields = (
        "sync_job",
        "snapshot",
        "raw_data",
        "line_items_preview",
        "first_seen_at",
        "last_seen_at",
    )
    ordering = ("-order_date", "-order_code")

    @admin.display(description="تعداد اقلام")
    def line_items_count(self, obj: SaleOrderSnapshot) -> int:
        from reports.services.invoices import InvoiceService

        return InvoiceService.line_items_for_order(obj).count()

    @admin.display(description="اقلام فاکتور (از sale_orders_with_stuffs)")
    def line_items_preview(self, obj: SaleOrderSnapshot) -> str:
        from reports.services.invoices import InvoiceService

        lines = InvoiceService.line_items_for_order(obj)[:20]
        if not lines:
            return "— (همگام‌سازی sale_orders_with_stuffs را اجرا کنید)"
        rows = []
        for line in lines:
            qty = line.stuff_quantity or line.package_quantity
            rows.append(
                f"• {line.stuff_name or line.stuff_code} — {qty} — {line.line_amount}"
            )
        extra = ""
        total = InvoiceService.line_items_for_order(obj).count()
        if total > 20:
            extra = f"\n… و {total - 20} قلم دیگر"
        return "\n".join(rows) + extra


@admin.register(SaleOrderLineSnapshot)
class SaleOrderLineSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "order_code",
        "order_date",
        "stuff_code",
        "stuff_name",
        "stuff_group_name",
        "stuff_quantity",
        "line_amount",
        "visitor_name",
        "partner_name",
    )
    list_filter = ("stuff_group_name", "order_date", "snapshot")
    search_fields = (
        "order_code",
        "order_pre_code",
        "stuff_code",
        "stuff_name",
        "partner_name",
        "visitor_code",
        "visitor_name",
    )
    readonly_fields = (
        "sync_job",
        "snapshot",
        "row_key",
        "raw_data",
        "first_seen_at",
        "last_seen_at",
    )
    ordering = ("-order_date", "order_code", "stuff_name")


@admin.register(DashboardRefreshLog)
class DashboardRefreshLogAdmin(admin.ModelAdmin):
    list_display = ("started_at", "status", "reports_refreshed", "triggered_by")
    list_filter = ("status", "triggered_by")
    readonly_fields = (
        "started_at",
        "finished_at",
        "status",
        "reports_refreshed",
        "error_message",
        "triggered_by",
    )
