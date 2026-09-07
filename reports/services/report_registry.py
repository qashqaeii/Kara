"""
Central registry for Kara reports.

Add a new report by appending a ReportDefinition — no if/elif chains required.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from reports.constants import REPORT_BASED_ON_DEFAULT, SyncStrategy
from reports.exceptions import ReportNotFoundError


@dataclass(frozen=True)
class ColumnDef:
    key: str
    label: str
    numeric: bool = False
    visible: bool = True
    money: bool = False  # monetary amounts stored as Rial; converted for display


@dataclass(frozen=True)
class ReportDefinition:
    key: str
    title: str
    slug: str
    referer: str
    grid_name: str
    grid_title: str
    binding_class: str
    binding_method: str
    default_arguments: dict[str, Any]
    parser: str
    sync_strategy: str = SyncStrategy.SNAPSHOT
    enabled: bool = True
    page_size: int = 100
    columns: tuple[ColumnDef, ...] = field(default_factory=tuple)
    kpi_fields: dict[str, str] = field(default_factory=dict)
    # Primary company KPI source — only one report should be True
    is_primary_kpi_source: bool = False
    suggested_interval_minutes: int = 5
    # Backward-compat aliases used by older code paths
    head_visitor_sale: str = ""
    # grid (default) or print (HTML reports like LostBenefit)
    fetch_type: str = "grid"
    print_path: str = ""

    @property
    def referer_path(self) -> str:
        return self.referer

    @property
    def is_print_report(self) -> bool:
        return self.fetch_type == "print"


# ---------------------------------------------------------------------------
# Column sets
# ---------------------------------------------------------------------------

COMMON_SALE_COLUMNS: tuple[ColumnDef, ...] = (
    ColumnDef("VisitorName", "نام ویزیتور"),
    ColumnDef("VisitorCode", "کد ویزیتور"),
    ColumnDef("PartnerGroupName", "گروه مشتری"),
    ColumnDef("Period", "دوره"),
    ColumnDef("OrderCountBasedOnFinalOrder", "تعداد سفارش نهایی", numeric=True),
    ColumnDef("OrderCountBasedOnPreOrder", "تعداد سفارش پیش‌سفارش", numeric=True),
    ColumnDef("TotalSale", "فروش نهایی", numeric=True, money=True),
    ColumnDef("TotalPureSale", "فروش خالص", numeric=True, money=True),
    ColumnDef("TotalStuffSale", "فروش کالا", numeric=True, money=True),
    ColumnDef("TotalDistributionReversion", "برگشت از توزیع", numeric=True, money=True),
    ColumnDef("TotalSaleReversion", "برگشت از فروش", numeric=True, money=True),
    ColumnDef("TotalSetteled", "جمع تسویه", numeric=True, money=True),
    ColumnDef("RemainderBasedOnSettlementWithSaleReversion", "مانده تسویه", numeric=True, money=True),
    ColumnDef("CashSetteled", "تسویه نقد", numeric=True, money=True),
    ColumnDef("BankSetteled", "تسویه بانک", numeric=True, money=True),
    ColumnDef("ChequeSetteled", "تسویه چک", numeric=True, money=True),
    ColumnDef("TotalDiscount", "تخفیف", numeric=True, money=True),
    ColumnDef("TotalVAT", "مالیات", numeric=True, money=True),
    ColumnDef("StuffQuantitySumBasedOnFinalOrder", "تعداد کالا نهایی", numeric=True),
    ColumnDef("StuffWeightSumBasedOnFinalOrder", "وزن کالا نهایی", numeric=True),
)

VISITOR_EXTRA_COLUMNS: tuple[ColumnDef, ...] = (
    ColumnDef("HeadVisitorName", "نام سرپرست"),
    ColumnDef("HeadVisitorCode", "کد سرپرست"),
    ColumnDef("ActiveDayCountBasedOnFinalOrder", "روز فعال نهایی", numeric=True),
    ColumnDef("PartnerNumberBasedOnFinalOrder", "تعداد مشتری نهایی", numeric=True),
)

STUFF_GROUP_COLUMNS: tuple[ColumnDef, ...] = (
    ColumnDef("StuffGroupName", "گروه کالا"),
    ColumnDef("StuffCode", "کد کالا"),
    ColumnDef("StuffName", "نام کالا"),
    ColumnDef("City", "شهر"),
    ColumnDef("Zone", "منطقه"),
    ColumnDef("Route", "مسیر"),
    ColumnDef("VisitorName", "ویزیتور"),
    ColumnDef("PartnerName", "مشتری"),
    ColumnDef("OrderCount", "تعداد سفارش", numeric=True),
    ColumnDef("PartnerCount", "تعداد مشتری", numeric=True),
    ColumnDef("NotPureSalePrice", "فروش ناخالص", numeric=True, money=True),
    ColumnDef("PureSalePrice", "فروش خالص", numeric=True, money=True),
    ColumnDef("DistributionReversionPrice", "برگشت از توزیع", numeric=True, money=True),
    ColumnDef("SaleReversionPrice", "برگشت از فروش", numeric=True, money=True),
    ColumnDef("PureSaleQuantity", "تعداد خالص", numeric=True),
)

MONTHLY_SALE_COLUMNS: tuple[ColumnDef, ...] = (
    ColumnDef("PartnerCode", "کد مشتری"),
    ColumnDef("PartnerName", "نام مشتری"),
    ColumnDef("VisitorName", "نام ویزیتور"),
    ColumnDef("StuffCode", "کد کالا"),
    ColumnDef("StuffName", "نام کالا"),
    ColumnDef("StuffGroupName1", "گروه کالا"),
    ColumnDef("FarvardinSale", "فروردین", numeric=True, money=True),
    ColumnDef("OrdibeheshtSale", "اردیبهشت", numeric=True, money=True),
    ColumnDef("KhordadSale", "خرداد", numeric=True, money=True),
    ColumnDef("TirSale", "تیر", numeric=True, money=True),
    ColumnDef("MordadSale", "مرداد", numeric=True, money=True),
    ColumnDef("ShahrivarSale", "شهریور", numeric=True, money=True),
    ColumnDef("MehrSale", "مهر", numeric=True, money=True),
    ColumnDef("AbanSale", "آبان", numeric=True, money=True),
    ColumnDef("AzarSale", "آذر", numeric=True, money=True),
    ColumnDef("DeySale", "دی", numeric=True, money=True),
    ColumnDef("BahmanSale", "بهمن", numeric=True, money=True),
    ColumnDef("EsfandSale", "اسفند", numeric=True, money=True),
)

SALE_REVERSION_COLUMNS: tuple[ColumnDef, ...] = (
    ColumnDef("ReversionCode", "کد برگشت"),
    ColumnDef("OrderCode", "شماره فاکتور"),
    ColumnDef("PartnerCode", "کد مشتری"),
    ColumnDef("PartnerName", "نام مشتری"),
    ColumnDef("OrderDate", "تاریخ سفارش"),
    ColumnDef("ReversionDate", "تاریخ برگشت"),
    ColumnDef("OrderFinalPrice", "مبلغ فاکتور", numeric=True, money=True),
    ColumnDef("ReversionPrice", "مبلغ برگشت", numeric=True, money=True),
)

DISTRIBUTION_REVERSION_COLUMNS: tuple[ColumnDef, ...] = (
    ColumnDef("TotalCode", "کد حواله"),
    ColumnDef("PartnerCode", "کد مشتری"),
    ColumnDef("PartnerName", "نام مشتری"),
    ColumnDef("DriverName", "راننده"),
    ColumnDef("OrderDate", "تاریخ"),
    ColumnDef("OrderFinal", "مبلغ فاکتور", numeric=True, money=True),
    ColumnDef("OrderPrice", "مبلغ", numeric=True, money=True),
    ColumnDef("OrderQuantity", "تعداد", numeric=True),
)

SALE_ORDERS_COLUMNS: tuple[ColumnDef, ...] = (
    ColumnDef("OrderCode", "کد فاکتور"),
    ColumnDef("OrderPreCode", "شماره پیش‌فاکتور"),
    ColumnDef("OrderDate", "تاریخ فاکتور"),
    ColumnDef("PartnerCode", "کد مشتری"),
    ColumnDef("PartnerName", "نام مشتری"),
    ColumnDef("VisitorCode", "کد ویزیتور"),
    ColumnDef("VisitorName", "نام ویزیتور"),
    ColumnDef("OrderFinalPrice", "مبلغ نهایی", numeric=True, money=True),
    ColumnDef("FinalizedCostForCustomer", "بهای تمام‌شده", numeric=True, money=True),
    ColumnDef("SaleReversionAmount", "برگشت از فروش", numeric=True, money=True),
    ColumnDef("StuffsQuantitySum", "تعداد کالا", numeric=True),
)

ACCOUNT_BALANCE_COLUMNS: tuple[ColumnDef, ...] = (
    ColumnDef("PartnerCode", "کد مشتری"),
    ColumnDef("PartnerName", "نام مشتری"),
    ColumnDef("PartnerLegalName", "نام حقوقی"),
    ColumnDef("Month01", "ماه ۱", numeric=True, money=True),
    ColumnDef("Month02", "ماه ۲", numeric=True, money=True),
    ColumnDef("Month03", "ماه ۳", numeric=True, money=True),
    ColumnDef("Month04", "ماه ۴", numeric=True, money=True),
    ColumnDef("Month05", "ماه ۵", numeric=True, money=True),
    ColumnDef("Month06", "ماه ۶", numeric=True, money=True),
    ColumnDef("Month07", "ماه ۷", numeric=True, money=True),
    ColumnDef("Month08", "ماه ۸", numeric=True, money=True),
    ColumnDef("Month09", "ماه ۹", numeric=True, money=True),
    ColumnDef("Month10", "ماه ۱۰", numeric=True, money=True),
    ColumnDef("Month11", "ماه ۱۱", numeric=True, money=True),
    ColumnDef("Month12", "ماه ۱۲", numeric=True, money=True),
)

RECEIVABLES_AGING_COLUMNS: tuple[ColumnDef, ...] = (
    ColumnDef("VisitorCode", "کد ویزیتور"),
    ColumnDef("VisitorName", "نام ویزیتور"),
    ColumnDef("CityName", "شهر"),
    ColumnDef("ZoneName", "منطقه"),
    ColumnDef("M1", "ماه ۱", numeric=True, money=True),
    ColumnDef("M2", "ماه ۲", numeric=True, money=True),
    ColumnDef("M3", "ماه ۳", numeric=True, money=True),
    ColumnDef("M4", "ماه ۴", numeric=True, money=True),
    ColumnDef("M5", "ماه ۵", numeric=True, money=True),
    ColumnDef("M6", "ماه ۶", numeric=True, money=True),
    ColumnDef("M7", "ماه ۷", numeric=True, money=True),
    ColumnDef("M8", "ماه ۸", numeric=True, money=True),
    ColumnDef("M9", "ماه ۹", numeric=True, money=True),
    ColumnDef("M10", "ماه ۱۰", numeric=True, money=True),
    ColumnDef("M11", "ماه ۱۱", numeric=True, money=True),
    ColumnDef("M12", "ماه ۱۲", numeric=True, money=True),
)

SALE_STUFFS_COLUMNS: tuple[ColumnDef, ...] = (
    ColumnDef("StuffCode", "کد کالا"),
    ColumnDef("StuffName", "نام کالا"),
    ColumnDef("StuffGroupName", "گروه کالا"),
    ColumnDef("StuffSubGroupName", "زیرگروه"),
    ColumnDef("SaleStuffQuantity", "تعداد فروش", numeric=True),
    ColumnDef("SaleSum", "مبلغ فروش", numeric=True, money=True),
    ColumnDef("SaleReversionSum", "مبلغ برگشت", numeric=True, money=True),
    ColumnDef("PureSale", "فروش خالص", numeric=True, money=True),
)

DEFAULT_KPI_FIELDS: dict[str, str] = {
    "total_sale": "TotalSale",
    "total_pure_sale": "TotalPureSale",
    "final_order_count": "OrderCountBasedOnFinalOrder",
    "settlement_remainder": "RemainderBasedOnSettlementWithSaleReversion",
    "distribution_reversion": "TotalDistributionReversion",
    "sale_reversion": "TotalSaleReversion",
}

VISITOR_SALE_ARGS: dict[str, Any] = {
    "BPersonnelCode": "",
    "EPersonnelCode": "",
    "BPartnerCode": "",
    "EPartnerCode": "",
    "BOrderCode": "",
    "EOrderCode": "",
    "BDate": "",
    "EDate": "",
    "BPreOrderInsertDate": "",
    "EPreOrderInsertDate": "",
    "BoundSettlementInDate": "false",
    "TimeGrouping": "0",
    "ReportBasedOn": REPORT_BASED_ON_DEFAULT,
    "HeadVisitorCode": "0",
    "Period": "",
    "IncludeFreeProductPrices": "false",
    "HeadVisitorSale": "False",
    "WithPartnerGroup": "false",
}

# Stuff group: EntityGroupIds / PartnerGroupIds are tenant-specific.
# Empty defaults still work for many tenants; override via sync arguments if needed.
STUFF_GROUP_ARGS: dict[str, Any] = {
    "BDate": "",
    "EDate": "",
    "BPreOrderInsertDate": "",
    "EPreOrderInsertDate": "",
    "BPartnerCode": "",
    "EPartnerCode": "",
    "EntityGroupIds": "0",
    "PartnerGroupIds": "0",
    "BVisitorCode": "",
    "EVisitorCode": "",
    "ReportBasedOn": REPORT_BASED_ON_DEFAULT,
    "FreeProductIncluding": "true",
    "WithSupervisorDetail": "true",
    "WithVisitorDetail": "true",
    "WithPartnerDetail": "true",
    "WithCityDetail": "true",
    "WithZoneDetail": "true",
    "WithRouteDetail": "true",
    "WithStuffBasketDetail": "true",
    "WithGroupNameDetail": "true",
    "WithSubGroupNameDetail": "true",
    "WithStuffDetail": "true",
    "WithBatchNumberDetail": "true",
    "WithWarehouseDetail": "true",
    "PeriodType": "1",
    "PeriodTypeBasedOn": "1",
    "IncludeFreeProductPrices": "false",
    "ShowZeroResults": "false",
    "WithPartnerGroup": "true",
    "WithMachine": "true",
}

SALE_ORDERS_ARGS: dict[str, Any] = {
    "RefreshReport": "true",
    "BPersonnelCode": "",
    "EPersonnelCode": "",
    "BPartnerCode": "",
    "EPartnerCode": "",
    "ZoneId": "",
    "BDate": "",
    "EDate": "",
    "BPreOrderInsertDate": "",
    "EPreOrderInsertDate": "",
    "ReportBasedOn": REPORT_BASED_ON_DEFAULT,
    "DynamicPartnerGroups": "",
    "UpdatingOrders_OnlyNotEditteds": "",
    "PartnersWithOutGroup": "true",
    "IncludeFreeProductPrices": "false",
}

# Kara's OrdersWithDetail binder is sensitive to BindingArguments key order:
# BStuffCode/EStuffCode must appear before ZoneId (browser payload order).
SALE_ORDERS_WITH_STUFFS_ARGS: dict[str, Any] = {
    "RefreshReport": "true",
    "BPersonnelCode": "",
    "EPersonnelCode": "",
    "BPartnerCode": "",
    "EPartnerCode": "",
    "BStuffCode": "",
    "EStuffCode": "",
    "ZoneId": "",
    "BDate": "",
    "EDate": "",
    "BPreOrderInsertDate": "",
    "EPreOrderInsertDate": "",
    "ReportBasedOn": REPORT_BASED_ON_DEFAULT,
    "DynamicPartnerGroups": "",
    "UpdatingOrders_OnlyNotEditteds": "",
    "PartnersWithOutGroup": "true",
    "IncludeFreeProductPrices": "false",
}

SALE_ORDER_LINE_COLUMNS: tuple[ColumnDef, ...] = (
    ColumnDef("OrderCode", "کد فاکتور"),
    ColumnDef("OrderDate", "تاریخ فاکتور"),
    ColumnDef("PartnerName", "نام مشتری"),
    ColumnDef("VisitorCode", "کد ویزیتور"),
    ColumnDef("StuffCode", "کد کالا"),
    ColumnDef("StuffName", "نام کالا"),
    ColumnDef("StuffGroupName", "گروه کالا"),
    ColumnDef("Quantity", "تعداد بسته", numeric=True),
    ColumnDef("StuffQuantity", "تعداد", numeric=True),
    ColumnDef("Fee", "فی", numeric=True, money=True),
    ColumnDef("ArticleFinalPrice", "مبلغ ردیف", numeric=True, money=True),
    ColumnDef("OrderFinalPrice", "مبلغ فاکتور", numeric=True, money=True),
)

SALE_STUFFS_ARGS: dict[str, Any] = {
    "BDate": "",
    "EDate": "",
    "BPreOrderInsertDate": "",
    "EPreOrderInsertDate": "",
    "ZoneId": "",
    "BPartnerCode": "",
    "EPartnerCode": "",
    "BPersonnelCode": "",
    "EPersonnelCode": "",
    "BStuffCode": "",
    "EStuffCode": "",
    "ReportBasedOn": REPORT_BASED_ON_DEFAULT,
    "IncludeFreeProductPrices": "false",
}

MONTHLY_SALE_ARGS: dict[str, Any] = {
    "EntityGroupIds": "0",
    "PartnerGroupIds": "0",
    "ReportBasedOn": REPORT_BASED_ON_DEFAULT,
    "WithPartnerZoneDetail": "true",
    "WithPartnerGroupDetail": "true",
    "WithPartnerDetail": "true",
    "WithVisitorDetail": "true",
    "WithGroupNameDetail": "true",
    "WithSubGroupNameDetail": "true",
    "WithStuffDetail": "true",
}

ACCOUNT_BALANCE_ARGS: dict[str, Any] = {
    "EntityGroupIds": "0",
    "PartnerGroupIds": "0",
}

RECEIVABLES_AGING_ARGS: dict[str, Any] = {
    "BVisitorCode": "",
    "EVisitorCode": "",
    "BPartnerCode": "",
    "EPartnerCode": "",
    "BDate": "",
    "EDate": "",
    "WithVisitorDetail": "true",
    "WithPartnerDetail": "false",
    "WithCityDetail": "true",
    "WithZoneDetail": "true",
    "WithRouteDetail": "false",
    "EntityGroupIds": "0",
    "PartnerGroupIds": "0",
}

PROFIT_LOSS_ARGS: dict[str, Any] = {
    "BDate": "",
    "EDate": "",
    "ReportLevel": "2",
    "FromActualFinishedPrice": "false",
}

# Accounting · LostBenefitSeparate — product-level sale/buy/benefit.
# EntityGroupIds / PartnerGroupIds injected from tenant dumps when "0".
LOST_BENEFIT_SEPARATE_ARGS: dict[str, Any] = {
    "BDate": "",
    "EDate": "",
    "BPartnerCode": "",
    "EPartnerCode": "",
    "BVisitorCode": "",
    "EVisitorCode": "",
    "EntityGroupIds": "0",
    "PartnerGroupIds": "0",
    "WithCityDetail": "true",
    "WithZoneDetail": "true",
    "WithRouteDetail": "false",
    "WithVisitorDetail": "true",
    "WithPartnerDetail": "false",
    "WithPartnerGroupDetail": "false",
    "WithOrderDetail": "false",
    "WithGroupNameDetail": "true",
    "WithSubGroupNameDetail": "true",
    "WithStuffDetail": "true",
}

# Accounting · MonthlyStuffGroupDetailedLostBenefit — Benefit1..12 = Jalali months.
MONTHLY_GROUP_LOST_BENEFIT_ARGS: dict[str, Any] = {
    "WithSubGroupNameDetail": "true",
}

LOST_BENEFIT_SEPARATE_COLUMNS: tuple[ColumnDef, ...] = (
    ColumnDef("VisitorCode", "کد ویزیتور"),
    ColumnDef("VisitorName", "ویزیتور"),
    ColumnDef("StuffGroupName", "گروه کالا"),
    ColumnDef("StuffSubGroupName", "زیرگروه"),
    ColumnDef("StuffCode", "کد کالا"),
    ColumnDef("StuffName", "نام کالا"),
    ColumnDef("City", "شهر"),
    ColumnDef("Zone", "منطقه"),
    ColumnDef("SalePriceQuantityFinal", "فروش نهایی", numeric=True, money=True),
    ColumnDef("SalePrice", "مبلغ فروش", numeric=True, money=True),
    ColumnDef("BuyPrice", "بهای تمام‌شده", numeric=True, money=True),
    ColumnDef("BenefitLostPrice", "سود/زیان", numeric=True, money=True),
    ColumnDef("BenefitLostPercent", "حاشیه ٪", numeric=True),
    ColumnDef("Discount", "تخفیف", numeric=True, money=True),
    ColumnDef("ReversionPrice", "برگشت", numeric=True, money=True),
)

MONTHLY_GROUP_LOST_BENEFIT_COLUMNS: tuple[ColumnDef, ...] = (
    ColumnDef("StuffGroupName", "گروه کالا"),
    ColumnDef("StuffSubGroupName", "زیرگروه"),
    ColumnDef("TotalBenefit", "جمع سود", numeric=True, money=True),
    *(
        ColumnDef(f"Benefit{i}", f"سود ماه {i}", numeric=True, money=True)
        for i in range(1, 13)
    ),
)


REPORT_DEFINITIONS: dict[str, ReportDefinition] = {
    "visitor_sale": ReportDefinition(
        key="visitor_sale",
        title="گزارش صورت وضعیت ویزیتور",
        slug="visitor-sale",
        referer="/Sale/Report/VisitorsSale",
        grid_name="VisitorSaleReportGrid",
        grid_title="گزارش صورت وضعیت ویزیتور",
        binding_class="Kara.BLL.Sale.Report",
        binding_method="GetReportBinding_VisitorsSale",
        default_arguments=VISITOR_SALE_ARGS,
        parser="visitor_sale",
        sync_strategy=SyncStrategy.SNAPSHOT,
        columns=(*VISITOR_EXTRA_COLUMNS[:2], *COMMON_SALE_COLUMNS),
        kpi_fields=DEFAULT_KPI_FIELDS,
        is_primary_kpi_source=True,
        head_visitor_sale="False",
    ),
    "head_visitor_sale": ReportDefinition(
        key="head_visitor_sale",
        title="گزارش صورت وضعیت سرپرست فروش",
        slug="head-visitor-sale",
        referer="/Sale/Report/HeadVisitorsSale",
        grid_name="HeadVisitorSaleReportGrid",
        grid_title="گزارش صورت وضعیت سرپرست",
        binding_class="Kara.BLL.Sale.Report",
        binding_method="GetReportBinding_VisitorsSale",
        default_arguments={**VISITOR_SALE_ARGS, "HeadVisitorSale": "True"},
        parser="head_visitor_sale",
        sync_strategy=SyncStrategy.SNAPSHOT,
        columns=COMMON_SALE_COLUMNS,
        kpi_fields=DEFAULT_KPI_FIELDS,
        is_primary_kpi_source=False,
        head_visitor_sale="True",
    ),
    "stuff_group_sale": ReportDefinition(
        key="stuff_group_sale",
        title="گزارش تفکیکی فروش گروه کالا",
        slug="stuff-group-sale",
        referer="/Sale/Report/StuffGroup",
        grid_name="SaleReport_StuffGroupsGrid",
        grid_title="گزارش تفکیکی فروش",
        binding_class="Kara.BLL.Sale.Report",
        binding_method="GetReportBinding_StuffGroupsSale",
        default_arguments=STUFF_GROUP_ARGS,
        parser="stuff_group_sale",
        sync_strategy=SyncStrategy.FULL,
        page_size=100,
        columns=STUFF_GROUP_COLUMNS,
        kpi_fields={
            "total_sale": "PureSalePrice",
            "distribution_reversion": "DistributionReversionPrice",
            "sale_reversion": "SaleReversionPrice",
            "final_order_count": "OrderCount",
        },
        suggested_interval_minutes=15,
    ),
    "sale_reversion": ReportDefinition(
        key="sale_reversion",
        title="گزارش برگشت از فروش",
        slug="sale-reversion",
        referer="/Sale/Report/Reversions",
        grid_name="SaleReversionReportGrid",
        grid_title="گزارش برگشت از فروش",
        binding_class="Kara.BLL.Sale.Report",
        binding_method="GetReportBinding_SaleReversion",
        default_arguments={
            "BPartnerCode": "",
            "EPartnerCode": "",
            "BOrderDate": "",
            "EOrderDate": "",
            "BReversionDate": "",
            "EReversionDate": "",
            "BPersonnelCode": "",
            "EPersonnelCode": "",
            "BStuffCode": "",
            "EStuffCode": "",
            "ShowStuffs": "false",
            "IncludeFreeProducts": "false",
        },
        parser="sale_reversion",
        sync_strategy=SyncStrategy.FULL,
        columns=SALE_REVERSION_COLUMNS,
        kpi_fields={},
        suggested_interval_minutes=15,
    ),
    "sale_distribution_reversion": ReportDefinition(
        key="sale_distribution_reversion",
        title="گزارش برگشت از توزیع",
        slug="sale-distribution-reversion",
        referer="/Sale/Report/SaleDistributionReversion",
        grid_name="SaleDistributionReversionReportGrid",
        grid_title="گزارش برگشت از توزیع",
        binding_class="Kara.BLL.Sale.Report",
        binding_method="GetReportBinding_SaleDistributionReversion",
        default_arguments={
            "BStuffCode": "",
            "EStuffCode": "",
            "BPersonnelCode": "",
            "EPersonnelCode": "",
            "BPartnerCode": "",
            "EPartnerCode": "",
            "BPayeeCode": "",
            "EPayeeCode": "",
            "BDriverCode": "",
            "EDriverCode": "",
            "BDate": "",
            "EDate": "",
            "BPreOrderInsertDate": "",
            "EPreOrderInsertDate": "",
            "ShowStuffs": "false",
            "IncludeFreeProductPrices": "false",
        },
        parser="sale_distribution_reversion",
        sync_strategy=SyncStrategy.FULL,
        columns=DISTRIBUTION_REVERSION_COLUMNS,
        kpi_fields={},
        suggested_interval_minutes=15,
    ),
    "sale_orders": ReportDefinition(
        key="sale_orders",
        title="گزارش فاکتور",
        slug="sale-orders",
        referer="/Sale/Report/Orders",
        grid_name="SaleOrdersReportGrid",
        grid_title="گزارش فاکتور",
        binding_class="Kara.BLL.Sale.Report",
        binding_method="GetReportBinding_Orders",
        default_arguments=SALE_ORDERS_ARGS,
        parser="sale_orders",
        sync_strategy=SyncStrategy.FULL,
        columns=SALE_ORDERS_COLUMNS,
        kpi_fields={
            "invoice_revenue": "OrderFinalPrice",
            "finalized_cost": "FinalizedCostForCustomer",
            "sale_reversion": "SaleReversionAmount",
        },
        suggested_interval_minutes=30,
    ),
    "sale_orders_with_stuffs": ReportDefinition(
        key="sale_orders_with_stuffs",
        title="گزارش فاکتور با ریز اقلام",
        slug="sale-orders-with-stuffs",
        referer="/Sale/Report/Orders",
        grid_name="SaleOrdersWithStuffsReportGrid",
        grid_title="گزارش فاکتور با ریز اقلام",
        binding_class="Kara.BLL.Sale.Report",
        binding_method="GetReportBinding_OrdersWithDetail",
        default_arguments=SALE_ORDERS_WITH_STUFFS_ARGS,
        parser="sale_orders",
        sync_strategy=SyncStrategy.FULL,
        page_size=100,
        columns=SALE_ORDER_LINE_COLUMNS,
        kpi_fields={},
        suggested_interval_minutes=60,
    ),
    "sale_stuffs": ReportDefinition(
        key="sale_stuffs",
        title="گزارش فروش کالا",
        slug="sale-stuffs",
        referer="/Sale/Report/Stuffs",
        grid_name="SaleReportStuffsGrid",
        grid_title="گزارش فروش کالا",
        binding_class="Kara.BLL.Sale.Report",
        binding_method="GetReportBinding_Stuffs",
        default_arguments=SALE_STUFFS_ARGS,
        parser="sale_stuffs",
        sync_strategy=SyncStrategy.SNAPSHOT,
        columns=SALE_STUFFS_COLUMNS,
        kpi_fields={
            "sale_amount": "SaleSum",
            "sale_reversion": "SaleReversionSum",
            "pure_sale": "PureSale",
        },
        suggested_interval_minutes=30,
    ),
    "monthly_sale": ReportDefinition(
        key="monthly_sale",
        title="گزارش ماهانه فروش",
        slug="monthly-sale",
        referer="/Sale/Report/MontlyReport",
        grid_name="MontlyReportGrid",
        grid_title="گزارش ماهانه فروش",
        binding_class="Kara.BLL.Sale.Report",
        binding_method="GetReportBinding_MonthlySale",
        default_arguments=MONTHLY_SALE_ARGS,
        parser="monthly_sale",
        sync_strategy=SyncStrategy.FULL,
        page_size=100,
        columns=MONTHLY_SALE_COLUMNS,
        kpi_fields={},
        suggested_interval_minutes=60,
    ),
    "account_balance": ReportDefinition(
        key="account_balance",
        title="مانده حساب مشتریان ماهانه",
        slug="account-balance",
        referer="/Sale/Report/AccountBallance_PartnerandPersonnel",
        grid_name="AccountBallance_PartnersAndPersonnels",
        grid_title="گزارش مانده حساب مشتریان ماهانه",
        binding_class="Kara.BLL.Sale.Report",
        binding_method="GetReportBinding_AccountBallance_PartnersAndPersonnels",
        default_arguments=ACCOUNT_BALANCE_ARGS,
        parser="account_balance",
        sync_strategy=SyncStrategy.FULL,
        page_size=100,
        columns=ACCOUNT_BALANCE_COLUMNS,
        kpi_fields={},
        suggested_interval_minutes=60,
    ),
    "receivables_aging": ReportDefinition(
        key="receivables_aging",
        title="جدول سنی معوقات",
        slug="receivables-aging",
        referer="/Sale/Report/SaleOrderRemainPrice",
        grid_name="SaleOrderRemainPriceGrid",
        grid_title="گزارش جدول سنی معوقات",
        binding_class="Kara.BLL.Sale.Report",
        binding_method="GetReportBinding_MonthlyUnsettledSaleOrders",
        default_arguments=RECEIVABLES_AGING_ARGS,
        parser="receivables_aging",
        sync_strategy=SyncStrategy.FULL,
        page_size=100,
        columns=RECEIVABLES_AGING_COLUMNS,
        kpi_fields={},
        suggested_interval_minutes=60,
    ),
    "profit_and_loss": ReportDefinition(
        key="profit_and_loss",
        title="گزارش سود و زیان",
        slug="profit-and-loss",
        referer="/Accounting/Report/LostBenefit",
        grid_name="",
        grid_title="گزارش سود و زیان",
        binding_class="",
        binding_method="",
        default_arguments=PROFIT_LOSS_ARGS,
        parser="profit_and_loss",
        sync_strategy=SyncStrategy.SNAPSHOT,
        fetch_type="print",
        print_path="/Accounting/Print/LostBenefit",
        columns=(),
        kpi_fields={
            "net_pure_sale": "NetPureSale",
            "cost_of_goods_sold": "CostOfGoodsSold",
            "gross_profit": "GrossProfit",
            "operating_profit": "OperatingProfit",
            "net_profit": "NetProfit",
            "gross_margin_rate": "GrossMarginRate",
        },
        suggested_interval_minutes=120,
    ),
    "lost_benefit_separate": ReportDefinition(
        key="lost_benefit_separate",
        title="گزارش سود و زیان تفکیکی",
        slug="lost-benefit-separate",
        referer="/Accounting/Report/LostBenefitSeparate",
        grid_name="LostBenefitSeparateFormGrid",
        grid_title="گزارش سود و زیان تفکیکی",
        binding_class="Kara.BLL.Accounting.Report",
        binding_method="GetReportBinding_LostBenefitSeparate",
        default_arguments=LOST_BENEFIT_SEPARATE_ARGS,
        parser="lost_benefit_separate",
        sync_strategy=SyncStrategy.FULL,
        page_size=100,
        columns=LOST_BENEFIT_SEPARATE_COLUMNS,
        kpi_fields={
            "gross_profit": "BenefitLostPrice",
            "invoice_revenue": "SalePrice",
            "finalized_cost": "BuyPrice",
        },
        suggested_interval_minutes=120,
    ),
    "monthly_stuff_group_lost_benefit": ReportDefinition(
        key="monthly_stuff_group_lost_benefit",
        title="گزارش سود و زیان ماهانه گروه کالا",
        slug="monthly-stuff-group-lost-benefit",
        referer="/Accounting/Report/MonthlyStuffGroupDetailedLostBenefit",
        grid_name="MonthlyStuffGroupDetailedLostBenefitGrid",
        grid_title="گزارش سود و زیان ماهانه گروه کالا",
        binding_class="Kara.BLL.Accounting.Report",
        binding_method="GetReportBinding_MonthlyStuffGroupDetailedLostBenefit",
        default_arguments=MONTHLY_GROUP_LOST_BENEFIT_ARGS,
        parser="monthly_stuff_group_lost_benefit",
        sync_strategy=SyncStrategy.SNAPSHOT,
        page_size=100,
        columns=MONTHLY_GROUP_LOST_BENEFIT_COLUMNS,
        kpi_fields={
            "gross_profit": "TotalBenefit",
        },
        suggested_interval_minutes=120,
    ),
    "entity_list": ReportDefinition(
        key="entity_list",
        title="جستجوی موجودیت‌ها",
        slug="entity-list",
        referer="/Sale/Report/VisitorsSale",
        grid_name="",
        grid_title="",
        binding_class="",
        binding_method="",
        default_arguments={"EntityGlobalType": "10203"},
        parser="entity_list",
        sync_strategy=SyncStrategy.INCREMENTAL,
        enabled=True,
        columns=(
            ColumnDef("code", "کد"),
            ColumnDef("name", "نام"),
        ),
        kpi_fields={},
        suggested_interval_minutes=60,
    ),
}


# Backward-compatible alias
ReportConfig = ReportDefinition


class ReportRegistry:
    @staticmethod
    def all(*, enabled_only: bool = False) -> dict[str, ReportDefinition]:
        items = REPORT_DEFINITIONS.copy()
        if enabled_only:
            return {k: v for k, v in items.items() if v.enabled and v.binding_method}
        return items

    @staticmethod
    def syncable() -> dict[str, ReportDefinition]:
        """Reports that sync from Kara (grid or print; excludes entity search-only)."""
        return {
            k: v
            for k, v in REPORT_DEFINITIONS.items()
            if v.enabled and (v.binding_method or v.is_print_report)
        }

    @staticmethod
    def get(key: str) -> ReportDefinition:
        config = REPORT_DEFINITIONS.get(key)
        if config is None:
            raise ReportNotFoundError(f"گزارش '{key}' در registry تعریف نشده است.")
        return config

    @staticmethod
    def get_by_slug(slug: str) -> ReportDefinition:
        for config in REPORT_DEFINITIONS.values():
            if config.slug == slug:
                return config
        raise ReportNotFoundError(f"گزارش با slug '{slug}' یافت نشد.")

    @staticmethod
    def keys(*, syncable_only: bool = False) -> list[str]:
        source = ReportRegistry.syncable() if syncable_only else REPORT_DEFINITIONS
        return list(source.keys())

    @staticmethod
    def primary_kpi_report() -> ReportDefinition:
        for config in REPORT_DEFINITIONS.values():
            if config.is_primary_kpi_source:
                return config
        return ReportRegistry.get("visitor_sale")

    @staticmethod
    def with_personnel(config: ReportDefinition, personnel_code: str) -> ReportDefinition:
        """Return a copy whose default args filter by personnel code."""
        args = dict(config.default_arguments)
        if "BPersonnelCode" in args:
            args["BPersonnelCode"] = personnel_code
            args["EPersonnelCode"] = personnel_code
        return replace(config, default_arguments=args)


def get_report_config(key: str) -> ReportDefinition:
    return ReportRegistry.get(key)
