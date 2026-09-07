from django.urls import path

from reports.views.analytics_views import (
    AnalyticsReceivablesView,
    AnalyticsRegionsView,
    AnalyticsReversionsView,
    AnalyticsSalespersonDetailView,
    AnalyticsSalespersonsView,
    AnalyticsSupervisorDetailView,
    AnalyticsSupervisorsView,
    MyPerformanceView,
)
from reports.views.api_analytics import (
    AnalyticsAlertsAPIView,
    AnalyticsMonthlyAPIView,
    AnalyticsOverviewAPIView,
    AnalyticsProductGroupsAPIView,
    AnalyticsProductsAPIView,
    AnalyticsReceivablesAPIView,
    AnalyticsRegionsAPIView,
    AnalyticsSalespersonsAPIView,
    AnalyticsSupervisorsAPIView,
    AnalyticsTrendAPIView,
    MyPerformanceAPIView,
    TvSlidesAPIView,
)
from reports.views.api_invoices import (
    InvoiceDetailAPIView,
    InvoiceListAPIView,
    InvoiceSearchAPIView,
    InvoiceStatsAPIView,
)
from reports.views.api_views import (
    AlertsAPIView,
    DashboardAPIView,
    PersonnelSearchAPIView,
    RefreshAllAPIView,
    SyncRunAPIView,
    SyncStatusAPIView,
    TestConnectionAPIView,
    VisitorRankingAPIView,
)
from reports.views.auth_views import LoginView, LogoutView
from reports.views.invoice_views import InvoiceDetailView, InvoiceListView
from reports.views.report_views import (
    DashboardView,
    ReportDetailView,
    ReportExportView,
    ReportRefreshView,
    SyncCenterView,
)
from reports.views.tv_views import DataExplorerView, TvModeAPIView, TvModeView

app_name = "reports"

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("invoices/", InvoiceListView.as_view(), name="invoices"),
    path("invoices/<str:order_code>/", InvoiceDetailView.as_view(), name="invoice_detail"),
    path("", DashboardView.as_view(), name="dashboard"),
    path("my-performance/", MyPerformanceView.as_view(), name="my_performance"),
    path("data-explorer/", DataExplorerView.as_view(), name="data_explorer"),
    path("tv/", TvModeView.as_view(), name="tv_mode"),
    path("api/tv/", TvModeAPIView.as_view(), name="api_tv"),
    path("api/tv/slides/", TvSlidesAPIView.as_view(), name="api_tv_slides"),
    path("sync/", SyncCenterView.as_view(), name="sync_center"),
    # Analytics pages
    path("analytics/salespersons/", AnalyticsSalespersonsView.as_view(), name="analytics_salespersons"),
    path(
        "analytics/salespersons/<str:personnel_code>/",
        AnalyticsSalespersonDetailView.as_view(),
        name="analytics_salesperson_detail",
    ),
    path("analytics/supervisors/", AnalyticsSupervisorsView.as_view(), name="analytics_supervisors"),
    path(
        "analytics/supervisors/<str:personnel_code>/",
        AnalyticsSupervisorDetailView.as_view(),
        name="analytics_supervisor_detail",
    ),
    path("analytics/regions/", AnalyticsRegionsView.as_view(), name="analytics_regions"),
    path("analytics/reversions/", AnalyticsReversionsView.as_view(), name="analytics_reversions"),
    path("analytics/receivables/", AnalyticsReceivablesView.as_view(), name="analytics_receivables"),
    # Analytics APIs
    path("api/analytics/overview/", AnalyticsOverviewAPIView.as_view(), name="api_analytics_overview"),
    path("api/analytics/trend/", AnalyticsTrendAPIView.as_view(), name="api_analytics_trend"),
    path("api/analytics/salespersons/", AnalyticsSalespersonsAPIView.as_view(), name="api_analytics_salespersons"),
    path("api/analytics/supervisors/", AnalyticsSupervisorsAPIView.as_view(), name="api_analytics_supervisors"),
    path("api/analytics/regions/", AnalyticsRegionsAPIView.as_view(), name="api_analytics_regions"),
    path("api/analytics/product-groups/", AnalyticsProductGroupsAPIView.as_view(), name="api_analytics_product_groups"),
    path("api/analytics/products/", AnalyticsProductsAPIView.as_view(), name="api_analytics_products"),
    path("api/analytics/monthly/", AnalyticsMonthlyAPIView.as_view(), name="api_analytics_monthly"),
    path("api/analytics/receivables/", AnalyticsReceivablesAPIView.as_view(), name="api_analytics_receivables"),
    path("api/analytics/alerts/", AnalyticsAlertsAPIView.as_view(), name="api_analytics_alerts"),
    path("api/my-performance/", MyPerformanceAPIView.as_view(), name="api_my_performance"),
    # Legacy dashboard APIs
    path("api/invoices/", InvoiceListAPIView.as_view(), name="api_invoices"),
    path("api/invoices/stats/", InvoiceStatsAPIView.as_view(), name="api_invoices_stats"),
    path("api/invoices/search/", InvoiceSearchAPIView.as_view(), name="api_invoices_search"),
    path(
        "api/invoices/<str:order_code>/",
        InvoiceDetailAPIView.as_view(),
        name="api_invoice_detail",
    ),
    path("api/dashboard/", DashboardAPIView.as_view(), name="api_dashboard"),
    path("api/dashboard/overview/", DashboardAPIView.as_view(), name="api_overview"),
    path("api/dashboard/visitor-ranking/", VisitorRankingAPIView.as_view(), name="api_visitor_ranking"),
    path("api/dashboard/alerts/", AlertsAPIView.as_view(), name="api_alerts"),
    path("api/refresh-all/", RefreshAllAPIView.as_view(), name="api_refresh_all"),
    path("api/sync/status/", SyncStatusAPIView.as_view(), name="api_sync_status"),
    path("api/sync/run/", SyncRunAPIView.as_view(), name="api_sync_run"),
    path("api/sync/test-connection/", TestConnectionAPIView.as_view(), name="api_test_connection"),
    path("api/personnel/search/", PersonnelSearchAPIView.as_view(), name="api_personnel_search"),
    path("head-visitor-sale/", ReportDetailView.as_view(), {"slug": "head-visitor-sale"}, name="head_visitor_sale"),
    path("visitor-sale/", ReportDetailView.as_view(), {"slug": "visitor-sale"}, name="visitor_sale"),
    path("<str:report_key>/refresh/", ReportRefreshView.as_view(), name="refresh"),
    path("<str:report_key>/export/excel/", ReportExportView.as_view(), {"export_format": "excel"}, name="export_excel"),
    path("<str:report_key>/export/csv/", ReportExportView.as_view(), {"export_format": "csv"}, name="export_csv"),
    path("<slug:slug>/", ReportDetailView.as_view(), name="report_detail"),
]
