# معماری تحلیلی — Fact و Dimension

## سه لایه داده

```
┌─────────────────────────────────────────────────────────┐
│  Analytics Layer  ← Dashboard / TV / API می‌خوانند     │
│  CompanyDailyMetric, SalespersonDailyMetric, Alerts...  │
├─────────────────────────────────────────────────────────┤
│  Normalized Layer   ← SyncOrchestrator می‌نویسد         │
│  Dimensions + Facts (typed columns)                     │
├─────────────────────────────────────────────────────────┤
│  Raw Layer          ← KaraRawResponse + KaraReportSnapshot│
│  JSON کامل برای audit و reprocess                       │
└─────────────────────────────────────────────────────────┘
```

## وضعیت فعلی (MVP)

| لایه | پیاده‌سازی | مدل‌ها |
|------|------------|--------|
| Raw | ✅ | `KaraRawResponse`, `KaraReportSnapshot` |
| Normalized | 🟡 جزئی | `VisitorSaleSnapshot`, `HeadVisitorSaleSnapshot`, `StuffGroupSaleSnapshot`, `SaleReversionSnapshot`, `DistributionReversionSnapshot` |
| Analytics | 🟡 جزئی | `DailyBusinessMetric`, `ManagementAlert` |

Dashboard فعلاً عمدتاً از `KaraReportSnapshot.raw_data` می‌خواند. هدف: مهاجرت به Analytics Layer.

---

## Dimensions (Read-only Mirror)

هر موجودیت `kara_code` به‌عنوان کلید خارجی دارد.

### Salesperson (ویزیتور)
```
kara_code          ← VisitorCode
name               ← VisitorName
supervisor_code    ← HeadVisitorCode
supervisor_name    ← HeadVisitorName
first_seen_at, last_seen_at, is_active
```

### SalesSupervisor (سرپرست)
```
kara_code          ← HeadVisitorCode (در head_visitor_sale)
name
```

### Customer (مشتری) — فاز بعد
```
kara_code          ← PartnerCode
name               ← PartnerName
group_name
city, zone
```

### Product / ProductGroup — پس از کشف 080503
```
kara_code, name, group_name
```

### City / Zone — از stuff_group_sale
```
name (فعلاً رشته؛ بعداً کد اگر Kara داشت)
```

### DistributionRoute — پس از 090405
```
kara_code, name
```

### BusinessDate
```
date_key           ← YYYY-MM-DD شمسی یا میلادی (یکسان‌سازی لازم)
```

---

## Fact Tables

### SalesFact (از visitor_sale — سطح ویزیتور/روز)
```
business_date
salesperson_code      FK → Salesperson
supervisor_code
total_sale
total_pure_sale
order_count
partner_count
distribution_reversion
sale_reversion
settlement_remainder
sync_job_id
source_snapshot_id
```

### ProductSalesFact (پس از 080503)
```
business_date, product_code, city, zone
quantity, gross_sale, discount, reversion, pure_sale
cost_amount, gross_profit, margin_pct
```

### ReversionFact (از sale_reversion / distribution)
```
reversion_type        ← sale | distribution
document_code, partner_code, amount, order_date, reversion_date
```

### TargetFact (پس از 080527)
```
period, salesperson_code, target_amount, actual_amount, achievement_pct
```

### VisitFact (پس از 080524)
```
visit_date, salesperson_code, partner_code, has_order
```

### ReceivableFact (پس از 080533/080534)
```
partner_code, balance, bucket_0_30, bucket_31_60, ...
```

---

## Analytics Layer (Precomputed)

### CompanyDailyMetric ✅ (موجود، گسترش‌پذیر)
```
metric_date, total_sale, total_pure_sale, order_count,
distribution_reversion, sale_reversion, active_visitors,
gross_profit (nullable), profit_margin (nullable)
```

### SalespersonDailyMetric (پیشنهادی)
```
metric_date, salesperson_code, total_sale, order_count, rank_sale, rank_growth
```

### SupervisorDailyMetric
```
metric_date, supervisor_code, team_sale, team_order_count, visitor_count
```

### ProductDailyMetric
```
metric_date, product_code, revenue, quantity, gross_profit
```

### RegionDailyMetric
```
metric_date, city, zone, pure_sale, order_count
```

### ManagementAlert ✅ (موجود)
```
severity, title, description, metric, entity, status
```

---

## کلیدهای یکتا و Idempotency

| Fact | کلید منطقی |
|------|------------|
| SalesFact | `(business_date, salesperson_code, source_snapshot_id)` |
| ProductSalesFact | `(business_date, product_code, city, zone)` |
| ReversionFact | `(reversion_type, document_code)` |

---

## جریان Sync

```
ReportDefinition → KaraClient.fetch_grid → KaraRawResponse
                 → KaraReportSnapshot
                 → SyncOrchestrator._persist_normalized
                 → Fact/Dimension tables
                 → AnalyticsService.recompute_daily_metrics
```

---

## قوانین KPI

1. `CompanyDailyMetric` فقط از `visitor_sale` پر شود
2. `head_visitor_sale` برای `SupervisorDailyMetric` و رتبه‌بندی تیم
3. سود فقط وقتی `gross_profit IS NOT NULL` در Analytics نمایش داده شود
