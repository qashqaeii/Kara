# Kara Management Dashboard — Architecture

## نقش سیستم

Kara (`app.pakhshmarket.com`) سیستم عملیاتی باقی می‌ماند.
این پروژه یک **سامانه نظارت و هوش مدیریتی فقط‌خواندنی** است — نه ERP جدید.

```
Kara → KaraClient → SyncOrchestrator → Django DB → AnalyticsService → Dashboard / TV Mode
```

داشبورد **هرگز** مستقیم به Kara وصل نمی‌شود.

## سه لایه محصول

1. **TV Mode** (`/tv/` یا `/reports/tv/`) — نمایش مدیریتی تمام‌صفحه
2. **داشبورد تحلیلی** (`/dashboard/` یا `/reports/`) — KPI، رتبه، هشدار
3. **کاوش داده** (`/reports/data-explorer/`) — جدول، Export، Debug

## قوانین مهم داده

1. **منبع KPI شرکت = فقط `visitor_sale`**
2. برگشت فروش و برگشت توزیع **جدا** نمایش داده می‌شوند
3. **سود/زیان** تا کشف API بهای تمام‌شده نمایش داده **نمی‌شود**
4. وضعیت: «به‌روزرسانی‌شده X دقیقه قبل» (نه Live)

## لایه‌های داده

| لایه | مدل‌ها |
|------|--------|
| Raw | `KaraRawResponse`, `KaraReportSnapshot` |
| Normalized | `VisitorSaleSnapshot`, `StuffGroupSaleSnapshot`, ... |
| Analytics | `DailyBusinessMetric`, `ManagementAlert` |

جزئیات: `DOCS/ANALYTICS_ARCHITECTURE.md`

## دسترسی

`UserKaraIdentity` + `AccessControlService` — آماده برای فاز F (پنل شخصی).

## اسناد PLAN

- `DOCS/PRODUCT_SCOPE.md`
- `DOCS/KPI_DICTIONARY.md`
- `DOCS/DATA_CAPABILITY_MATRIX.md`
- `DOCS/KARA_API_DISCOVERY_BACKLOG.md`
- `DOCS/EXECUTION_PLAN.md`

## دستورات

```bash
python manage.py migrate
python manage.py kara_sync --test-connection
python manage.py kara_sync --report visitor_sale
python manage.py kara_sync --all
python manage.py test reports
python manage.py runserver
```

## صفحات

| مسیر | توضیح |
|------|--------|
| `/reports/` | داشبورد مدیریتی (نمای کلی) |
| `/tv/` | TV Mode |
| `/reports/data-explorer/` | کاوش داده |
| `/reports/sync/` | مرکز همگام‌سازی |
| `/reports/api/tv/` | API TV Mode |

## امنیت

- Credentialها فقط Server-side
- Cookie کارا به مرورگر کاربر ارسال نمی‌شود
