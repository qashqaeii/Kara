# فرهنگ KPI — تعاریف و منابع

هر KPI باید منبع، فرمول و وضعیت دسترسی مشخص داشته باشد. **حدس زده نمی‌شود.**

## وضعیت‌های مجاز

| وضعیت | معنی |
|--------|------|
| `Available` | قابل نمایش با داده فعلی |
| `Partially Available` | بخشی از ابعاد/فیلدها موجود است |
| `API Not Discovered` | endpoint هنوز از Network استخراج نشده |
| `Data Not Sufficient` | API هست ولی فیلد کافی نیست |
| `Blocked by Business Definition` | تعریف کسب‌وکار از سمت کارفرما مشخص نشده |

---

## KPIهای شرکت (سطح کل)

### فروش نهایی (`total_sale`)
- **تعریف:** مجموع مبلغ فروش نهایی در دوره
- **فیلد Kara:** `TotalSale` در `SumRowData`
- **منبع:** `visitor_sale` (تنها منبع KPI شرکت)
- **وضعیت:** Available
- **واحد:** ریال
- **هشدار:** جمع‌زدن با `head_visitor_sale` ممنوع (double count)

### فروش خالص (`total_pure_sale`)
- **تعریف:** فروش پس از کسر برگشت‌ها (طبق تعریف Kara)
- **فیلد:** `TotalPureSale`
- **منبع:** `visitor_sale`
- **وضعیت:** Available

### تعداد سفارش نهایی (`final_order_count`)
- **فیلد:** `OrderCountBasedOnFinalOrder`
- **منبع:** `visitor_sale`
- **وضعیت:** Available

### میانگین مبلغ سفارش (`avg_order_value`)
- **فرمول:** `total_sale / final_order_count`
- **منبع:** مشتق از `visitor_sale`
- **وضعیت:** Available

### برگشت از فروش (`sale_reversion`)
- **فیلد:** `TotalSaleReversion`
- **منبع:** `visitor_sale` (تجمیعی) + جزئیات در `sale_reversion`
- **وضعیت:** Available

### برگشت از توزیع (`distribution_reversion`)
- **فیلد:** `TotalDistributionReversion`
- **منبع:** `visitor_sale` + جزئیات در `sale_distribution_reversion`
- **وضعیت:** Available

### نرخ برگشت (`reversion_rate`)
- **فرمول:** `(sale_reversion + distribution_reversion) / total_sale × 100`
- **منبع:** مشتق
- **وضعیت:** Available
- **توجه:** دو نوع برگشت جدا نمایش داده می‌شوند

### مانده تسویه (`settlement_remainder`)
- **فیلد:** `RemainderBasedOnSettlementWithSaleReversion`
- **منبع:** `visitor_sale`
- **وضعیت:** Available

### ویزیتور فعال (`active_visitors`)
- **تعریف:** تعداد ویزیتور با `TotalSale > 0`
- **منبع:** ردیف‌های `visitor_sale`
- **وضعیت:** Available

---

## KPIهای سودآوری (فعلاً غیرفعال در UI)

### سود ناخالص (`gross_profit`)
- **تعریف کسب‌وکار:** فروش خالص − بهای تمام‌شده کالای فروش‌رفته − هزینه‌های مستقیم توزیع (در صورت وجود)
- **منبع فعلی:** `080106` گزارش سود و زیان
- **فیلد/بخش:** سرفصل `بهای تمام شده کالای فروش رفته` و جمع‌های نهایی گزارش
- **وضعیت:** Partially Available
- **نیاز باقی‌مانده:** برای سود کالا هنوز گزارش تفصیلی بهای تمام‌شده لازم است

### حاشیه سود (`profit_margin`)
- **فرمول:** `gross_profit / total_pure_sale × 100`
- **منبع فعلی:** مشتق از `080106` + فروش خالص
- **وضعیت:** Partially Available
- **توجه:** فعلاً فقط در سطح شرکت قابل اتکاست

### سود کالا (`product_gross_profit`)
- **وضعیت:** API Not Discovered

---

## KPIهای عملکرد (ویزیتور / سرپرست)

### رتبه فروش ویزیتور
- **منبع:** ردیف‌های `visitor_sale`، مرتب‌سازی بر `TotalSale`
- **وضعیت:** Available

### رتبه فروش سرپرست
- **منبع:** `head_visitor_sale` (نمای تیمی، نه KPI شرکت)
- **وضعیت:** Available

### تحقق هدف (`target_achievement`)
- **منبع احتمالی:** MenuCode `080527` + `090407`
- **وضعیت:** API Not Discovered

---

## KPIهای جغرافیایی

### فروش به تفکیک شهر (`city_sales`)
- **منبع:** `stuff_group_sale` با `WithCityDetail=true`
- **فیلد:** `City`, `PureSalePrice`
- **وضعیت:** Partially Available (بدون سود و هدف)

### فروش به تفکیک منطقه (`zone_sales`)
- **منبع:** `stuff_group_sale` با `WithZoneDetail=true`
- **وضعیت:** Partially Available

---

## KPIهای مطالبات

| KPI | MenuCode | وضعیت |
|-----|----------|--------|
| مانده حساب مشتریان | 080533 | Partially Available |
| جدول سنی معوقات | 080534 | Partially Available |

- `080533` کشف شده و مانده هر مشتری را در ستون‌های `Month01` تا `Month12` برمی‌گرداند.
- این endpoint برای snapshot و trend مطالبات مفید است، اما aging bucket استاندارد معوقات را ارائه نمی‌کند.
- `080534` کشف شده و bucketهای مطالبات را در ستون‌های `M1` تا `M12` برمی‌گرداند.
- `080534` در dump فعلی بعدهای `VisitorName`, `CityName`, `ZoneName` را دارد؛ باید معنای دقیق `M1..M12` در Kara به‌عنوان bucket سنی تثبیت شود.

---

## قوانین منبع حقیقت

1. **KPI شرکت = فقط `visitor_sale`**
2. `head_visitor_sale` = نمای سرپرست، همان `SumRowData` تجمیعی
3. برگشت فروش و برگشت توزیع **جدا** نمایش داده می‌شوند
4. عبارت «زنده/Live» استفاده نمی‌شود → «به‌روزرسانی‌شده X دقیقه قبل»
