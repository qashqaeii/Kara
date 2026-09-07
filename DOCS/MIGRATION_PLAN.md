# برنامه مهاجرت — Snapshot MVP به Analytics Layer

## وضعیت فعلی

```
Kara → KaraClient → KaraReportSnapshot (JSON کامل)
                  → VisitorSaleSnapshot و ... (جزئی)
                  → AnalyticsService → خواندن مستقیم از snapshot.raw_data
```

**مشکلات:**
- Dashboard به `raw_data` وابسته است
- مقایسه دوره‌ای محدود (`DailyBusinessMetric` ناقص)
- Query سنگین روی JSON
- سخت‌بودن فیلتر سطح ردیف (شهر، کالا، مشتری)

## وضعیت هدف

```
Kara → Sync → Raw → Normalized Facts → Daily Metrics → Dashboard/TV
```

---

## فاز ۱ — تثبیت (فاز A — انجام/در حال انجام)

- [x] منبع حقیقت KPI = `visitor_sale` فقط
- [x] جلوگیری از double count
- [x] تفکیک Dashboard / Data Explorer
- [x] TV Mode shell
- [x] `UserKaraIdentity` برای permission
- [ ] تکمیل `evaluate_alerts` پس از Sync
- [ ] تست یکپارچگی Sync

## فاز ۲ — نرمال‌سازی کامل (فاز C)

1. **پس از هر Sync موفق `visitor_sale`:**
   - Upsert `Salesperson` از ردیف‌ها
   - Upsert `SalesFact` per visitor per sync date
   - Recompute `CompanyDailyMetric` برای `metric_date`

2. **پس از `stuff_group_sale`:**
   - Upsert `RegionDailyMetric` (city/zone aggregates)

3. **پس از reversion reports:**
   - Upsert `ReversionFact`

4. **Backfill:**
   - `python manage.py kara_backfill_metrics --days 30` (دستور آینده)
   - خواندن snapshots تاریخی از DB

## فاز ۳ — Analytics Service Refactor

```python
# قبل
kpis = ReportParser.extract_kpis(snapshot.sum_row_data)

# بعد
kpis = CompanyDailyMetric.objects.filter(metric_date=today).first()
# fallback به snapshot اگر metric نبود
```

## فاز ۴ — Dashboard/TV روی Analytics

- KPI cards از `CompanyDailyMetric`
- رتبه از `SalespersonDailyMetric` یا query روی `SalesFact`
- مقایسه دوره: join با metric_date قبلی
- TV نمودار روند از ۷ روز `CompanyDailyMetric`

## فاز ۵ — گزارش‌های جدید

هر `ReportDefinition` جدید:
1. Raw snapshot (همیشه)
2. Normalizer اختصاصی
3. Fact table
4. ورود به Capability Matrix
5. Feature Flag فعال

---

## سازگاری عقب‌رو

| مؤلفه | سیاست |
|--------|--------|
| `KaraReportSnapshot` | حفظ — منبع audit |
| Data Explorer | همچنان raw_data |
| API dashboard | فیلدهای فعلی + فیلدهای جدید optional |
| Export CSV/Excel | بدون تغییر |

## ریسک‌ها

| ریسک | کاهش |
|------|------|
| Schema تغییر Kara | Raw layer + checksum |
| تاریخ شمسی/میلادی | یکسان‌سازی در `BusinessDate` |
| حجم داده | index روی fact keys، archive snapshots قدیمی |

## معیار اتمام مهاجرت

- [ ] Dashboard بدون parse مستقیم JSON (به‌جز fallback)
- [ ] TV روند ۷ روزه از metrics
- [ ] مقایسه دوره در KPI cards
- [ ] تست: KPI dashboard = SumRowData visitor_sale
