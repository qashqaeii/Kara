# ماتریس قابلیت داده (Data Capability Matrix)

وضعیت هر قابلیت مدیریتی نسبت به داده فعلی Kara.

**راهنما:** Available | Partially Available | API Not Discovered | Data Not Sufficient | Blocked by Business Definition

---

## سطح مدیریت ارشد

| قابلیت | KPI | تعریف | منبع Kara | فیلدها | وضعیت API | کیفیت داده | Sync | محاسبه فعلی | ابهام |
|--------|-----|--------|-----------|--------|-----------|------------|------|-------------|-------|
| فروش کل | total_sale | فروش نهایی دوره | visitor_sale / 080510 | TotalSale | Available | خوب | ۵ دقیقه | بله | — |
| فروش خالص | total_pure_sale | فروش پس از برگشت | visitor_sale | TotalPureSale | Available | خوب | ۵ دقیقه | بله | تعریف دقیق Kara |
| سفارش | final_order_count | تعداد سفارش نهایی | visitor_sale | OrderCountBasedOnFinalOrder | Available | خوب | ۵ دقیقه | بله | — |
| برگشت فروش | sale_reversion | مبلغ برگشت فروش | visitor_sale + sale_reversion | TotalSaleReversion | Available | خوب | ۵/۱۵ دقیقه | بله | — |
| برگشت توزیع | distribution_reversion | مبلغ برگشت توزیع | visitor_sale + sale_distribution_reversion | TotalDistributionReversion | Available | خوب | ۵/۱۵ دقیقه | بله | — |
| نرخ برگشت | reversion_rate | نسبت برگشت به فروش | مشتق | — | Available | خوب | — | بله | آستانه هشدار |
| سود ناخالص | gross_profit | فروش خالص − بهای تمام‌شده | 080106 / حسابداری | تجمیعی | Available | متوسط | ۱۲۰ دقیقه | بله (سطح شرکت) | — |
| حاشیه سود | profit_margin | سود/فروش خالص | 080106 + مشتق | تجمیعی | Available | متوسط | ۱۲۰ دقیقه | بله (سطح شرکت) | — |
| مقایسه دوره | period_comparison | رشد/افت نسبت به قبل | DailyBusinessMetric | — | Partially Available | ضعیف | روزانه | خیر | نیاز backfill تاریخی |
| وضعیت کلی | health_status | مطلوب/توجه/بحرانی | قوانین روی KPI | — | Partially Available | — | — | بله (ساده) | وزن قوانین |

---

## سطح مدیر فروش

| قابلیت | KPI | منبع | وضعیت | یادداشت |
|--------|-----|------|--------|---------|
| رتبه ویزیتور (فروش) | visitor_ranking | visitor_sale | Available | — |
| رتبه سرپرست | supervisor_ranking | head_visitor_sale | Available | جدا از KPI شرکت |
| رتبه سود | profit_ranking | lost_benefit_separate | Available | SalePrice − BuyPrice = BenefitLostPrice |
| رتبه رشد | growth_ranking | مقایسه دوره | Partially Available | نیاز تاریخ |
| رتبه تحقق هدف | target_ranking | 080527 | API Not Discovered | — |
| فروش شهر | city_sales | stuff_group_sale | Partially Available | City در raw |
| فروش منطقه | zone_sales | stuff_group_sale | Partially Available | Zone در raw |
| پرفروش‌ترین کالا (مبلغ) | top_product_revenue | 080503 | Available | sale_stuffs |
| پرفروش‌ترین کالا (تعداد) | top_product_qty | 080503 | Available | sale_stuffs |
| پرسودترین کالا | top_product_profit | lost_benefit_separate | Available | BenefitLostPrice / حاشیه ٪ |
| سود ماهانه گروه کالا | monthly_group_benefit | monthly_stuff_group_lost_benefit | Available | Benefit1..12 = ماه‌های شمسی |
| تحلیل Quadrant کالا | product_quadrant | lost_benefit_separate | Partially Available | داده موجود؛ UI بعدی |
| علت افت فروش | change_attribution | چند منبع | Partially Available | rule-based فاز E |
| معوقات مشتری | receivables_aging | 080533/080534 | Partially Available | sync + صفحه مطالبات |

---

## سطح ویزیتور / سرپرست (فاز F)

| قابلیت | وضعیت | پیش‌نیاز |
|--------|--------|----------|
| پنل شخصی ویزیتور | Blocked by Business Definition | UserKaraIdentity + فیلتر personnel |
| پنل تیمی سرپرست | Blocked by Business Definition | نقش + supervisor_code |
| رتبه در تیم | Partially Available | visitor_sale + access control |

---

## گزارش‌های Sync شده فعلی

| کلید | MenuCode | Grid | وضعیت |
|------|----------|------|--------|
| visitor_sale | 080510 | VisitorSaleReportGrid | Available |
| head_visitor_sale | 080511 | HeadVisitorSaleReportGrid | Available |
| stuff_group_sale | 080504 | SaleReport_StuffGroupsGrid | Available |
| sale_reversion | 080507 | SaleReversionReportGrid | Available |
| sale_distribution_reversion | 080508 | SaleDistributionReversionReportGrid | Available |
| sale_orders | 080501 | SaleOrdersReportGrid | Available |
| sale_stuffs | 080503 | SaleReportStuffsGrid | Available |
| monthly_sale | 080536 | MontlyReportGrid | Available |
| profit_and_loss | 080106 | LostBenefit (Print) | Partially Available |
| account_balance | 080533 | AccountBallance_PartnersAndPersonnels | Partially Available |
| receivables_aging | 080534 | SaleOrderRemainPriceGrid | Partially Available |
| entity_list | — | جستجوی موجودیت | Available (جستجو) |

---

## اولویت کشف API بعدی

### اولویت ۱ — سودآوری
- نرمال‌سازی خروجی `080106` برای استخراج KPIهای مالی شرکت
- `080501` گزارش فاکتور
- `080503` گزارش فروش کالا
- گزارش ترازنامه حسابداری (`080107`)

### اولویت ۲ — هدف و ویزیت
- `080527` تحقق هدف
- `080524` لیست ویزیت مشتریان
- `080540` فروش ویزیتور–طرف‌حساب

### اولویت ۳ — مطالبات
- تکمیل mapping و نرمال‌سازی `080533` برای `Month01..Month12`
- تکمیل mapping و تفسیر bucketهای `080534` برای `M1..M12`

---

## اقدام فوری UI

تا تکمیل نرمال‌سازی کامل `080106`:
- TV Mode و Dashboard می‌توانند سود عملیاتی/خالص سطح شرکت را نشان دهند اگر Sync موفق باشد
- سود کالایی و ranking سود همچنان غیرفعال می‌ماند
