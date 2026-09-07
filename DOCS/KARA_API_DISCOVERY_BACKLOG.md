# بک‌لاگ کشف API کارا

`GetMenuShortKeys` فقط کاتالوگ است. برای هر گزارش باید از Network tab استخراج شود:

- `Referer` (مسیر صفحه)
- `GridName`, `GridTitle`
- `BindingClass`, `BindingMethod`
- `BindingArguments` (پارامترها و مقادیر پیش‌فرض)
- نمونه پاسخ JSON (ستون‌ها و SumRowData)

**قالب تحویل:** مانند `DOCS/api_docs.txt`

---

## اولویت صفر — تکمیل گزارش‌های فعلی

| # | کلید | MenuCode | Referer (شناخته‌شده) | وضعیت |
|---|------|----------|----------------------|--------|
| 1 | visitor_sale | 080510 | `/Sale/Report/VisitorsSale` | ✅ مستند در api_docs |
| 2 | head_visitor_sale | 080511 | `/Sale/Report/HeadVisitorsSale` | ✅ |
| 3 | stuff_group_sale | 080504 | `/Sale/Report/StuffGroup` | ✅ |
| 4 | sale_reversion | 080507 | `/Sale/Report/Reversions` | ✅ |
| 5 | sale_distribution_reversion | 080508 | `/Sale/Report/SaleDistributionReversion` | ✅ |

**اقدام:** اطمینان از پایداری Sync و نرمال‌سازی؛ بدون گسترش scope.

---

## اولویت ۱ — سودآوری (نیاز فوری برای KPI مالی)

| # | MenuCode | عنوان | هدف | وضعیت | درخواست از کاربر |
|---|----------|--------|-----|--------|------------------|
| 1 | 080501 | گزارش فاکتور | تخفیف، مبلغ فاکتور، جزئیات | 🟡 endpoint کشف شد؛ فاقد COGS | خیر |
| 2 | 080503 | گزارش فروش کالا | تعداد، مبلغ، احتمالاً COGS | 🟡 endpoint کشف شد؛ فاقد COGS | خیر |
| 3 | 080106 | گزارش سود و زیان | سود عملیاتی و سود خالص شرکت | ✅ Print + sync (`profit_and_loss`) | خیر |
| 4 | — | سود و زیان تفکیکی | COGS + سود کالا/ویزیتور/منطقه | ✅ Grid ثبت شد (`lost_benefit_separate`) | همگام‌سازی ۱۲۰د |
| 5 | — | سود ماهانه گروه کالا | Benefit1..12 شمسی | ✅ Grid ثبت شد (`monthly_stuff_group_lost_benefit`) | همگام‌سازی ۱۲۰د |
| 6 | 080107 | گزارش ترازنامه | دارایی/بدهی (فاز بعد) | ⚪ اختیاری | — |

**فیلدهای هدف برای سود کالا (از LostBenefitSeparate):**
```
SalePrice, BuyPrice, BenefitLostPrice, BenefitLostPercent,
StuffCode, StuffName, StuffGroupName, VisitorCode, City, Zone
```

**منبع قبلی «فقط تجمیعی» دیگر برای سود کالا لازم نیست** — پس از sync گزارش تفکیکی، `product_profit_available=True` می‌شود.

**وضعیت کشف فعلی:**
- `080501` کشف شد: `Referer=/Sale/Report/Orders`، `GridName=SaleOrdersReportGrid`، `BindingMethod=GetReportBinding_Orders`
- فیلدهای مهم `080501`: `OrderFinalPrice`, `StuffsPriceSum`, `StuffsDiscountSum`, `OrderDiscountAmount`, `SaleReversionAmount`, `VisitorCode`, `PartnerCode`
- `080503` کشف شد: `Referer=/Sale/Report/Stuffs`، `GridName=SaleReportStuffsGrid`، `BindingMethod=GetReportBinding_Stuffs`
- فیلدهای مهم `080503`: `SaleStuffQuantity`, `SalePrice`, `SaleDiscountAmount`, `SaleReversionPrice`, `PureSale`, `StuffGroupName`, `StuffCode`
- `080106` کشف شد: `Referer=/Accounting/Report/LostBenefit` و خروجی چاپی از `GET /Accounting/Print/LostBenefit`
- فیلدها/بخش‌های مهم `080106`: `فروش خالص`, `بهای تمام شده کالای فروش رفته`, `سود(زیان) عملیاتی`, `سود(زیان) خالص`, سرفصل‌های اصلی هزینه
- `LostBenefitSeparate` کشف و ثبت شد: سود کالا با `BuyPrice` + `BenefitLostPrice`
- `MonthlyStuffGroupDetailedLostBenefit` کشف و ثبت شد: سری ماهانه `Benefit1..12`
---

## اولویت ۲ — هدف و پوشش

| # | MenuCode | عنوان | هدف | وضعیت |
|---|----------|--------|-----|--------|
| 1 | 080527 | تحقق هدف | KPI هدف vs واقعی | 🔴 کشف‌نشده |
| 2 | 090407 | اهداف فروش (پایه) | تعریف هدف | 🔴 کشف‌نشده |
| 3 | 080524 | لیست ویزیت مشتریان | پوشش ویزیت | 🔴 کشف‌نشده |
| 4 | 080540 | فروش ویزیتور–طرف‌حساب | تفکیک مشتری | 🔴 کشف‌نشده |
| 5 | 090410 | دوره ویزیت | تقویم ویزیت | 🔴 کشف‌نشده |
| 6 | 090405 | مسیر توزیع | عملکرد مسیر | 🔴 کشف‌نشده |

---

## اولویت ۳ — مطالبات و ریسک

| # | MenuCode | عنوان | هدف | وضعیت |
|---|----------|--------|-----|--------|
| 1 | 080533 | مانده حساب مشتریان ماهانه | مطالبات | 🟡 endpoint کشف شد |
| 2 | 080534 | جدول سنی معوقات | ریسک اعتباری | 🟡 endpoint کشف شد |
| 3 | 080518/080522 | تسویه فاکتور | جریان نقدی | 🔴 کشف‌نشده |
| 4 | 080203/080204 | چک دریافتی/پرداختی | ریسک چک | ⚪ فاز بعد |

**وضعیت کشف فعلی:**
- `080533` کشف شد: `Referer=/Sale/Report/AccountBallance_PartnerandPersonnel`، `GridName=AccountBallance_PartnersAndPersonnels`، `BindingMethod=GetReportBinding_AccountBallance_PartnersAndPersonnels`
- فیلدهای اصلی: `PartnerCode`, `PartnerName`, `PartnerLegalName`, `Month01` تا `Month12`, `PartnerId`
- `SumRowData` نیز جمع مانده هر ماه را برمی‌گرداند؛ برای KPI مطالبات ماهانه و ترند بدهی مشتری قابل استفاده است
- `080534` کشف شد: `Referer=/Sale/Report/SaleOrderRemainPrice`، `GridName=SaleOrderRemainPriceGrid`، `BindingMethod=GetReportBinding_MonthlyUnsettledSaleOrders`
- فیلدهای اصلی `080534`: `VisitorCode`, `VisitorName`, `CityName`, `ZoneName`, `M1` تا `M12`
- نتیجه: `080533` برای snapshot مانده ماهانه مشتری و `080534` برای bucketهای معوقه/مطالبات سررسیدگذشته مکمل هم هستند

---

## گزارش‌های مکمل (اولویت پایین)

| MenuCode | عنوان | کاربرد |
|----------|--------|--------|
| 080501 | گزارش فاکتور | جزئیات فاکتور |
| 080505 | فروش به طرف حساب | تحلیل مشتری |
| 080506 | عدم سفارش | فرصت از دست‌رفته |
| 080536 | مقایسه زمانی فروش / گزارش ماهانه فروش | روند |
| 080537 | فرکانس ویزیت مناطق | پوشش |

**کشف مکمل انجام‌شده:**
- `080536` نیز کشف شده است: `Referer=/Sale/Report/MontlyReport`، `GridName=MontlyReportGrid`، `BindingMethod=GetReportBinding_MonthlySale`
- این endpoint برای trend و seasonality مفید است، نه برای محاسبه مستقیم سود کالا
- `080106` اگرچه Grid نیست، اما به‌عنوان خروجی چاپی HTML برای KPIهای مالی سطح شرکت ارزش بالایی دارد

---

## چک‌لیست استخراج Network

برای هر گزارش جدید این موارد را در `api_docs.txt` ثبت کنید:

```text
# [عنوان گزارش] — MenuCode XXXXXX
Request URL: .../Common/GridBinding/_GridAjaxBinding
Referer: http://app.pakhshmarket.com/...
Payload: GridName=...&BindingClass=...&BindingMethod=...&BindingArguments=...
Sample response: { Data: [...], SumRowData: {...} }
```

---

## Feature Flags مرتبط

تا کشف API، این بخش‌های UI غیرفعال می‌مانند:

| Flag | بخش |
|------|-----|
| `FEATURE_PROFITABILITY` | سود، حاشیه، Quadrant کالا |
| `FEATURE_TARGETS` | تحقق هدف |
| `FEATURE_RECEIVABLES` | مطالبات و معوقات |
| `FEATURE_GEO_MAP` | نقشه (فقط Bar Chart تا mapping معتبر) |
| `FEATURE_PERSONAL_PANEL` | پنل ویزیتور/سرپرست |
