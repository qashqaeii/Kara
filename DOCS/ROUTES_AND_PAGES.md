# مسیرها و صفحات

## نقشه URL نهایی

| مسیر | نام | وضعیت | توضیح |
|------|-----|--------|--------|
| `/` | ریدایرکت | ✅ | → داشبورد |
| `/dashboard/` | نمای کلی | ✅ | alias به `/reports/` |
| `/tv/` | TV Mode | ✅ shell | نمایش تمام‌صفحه مدیریتی |
| `/reports/` | داشبورد مدیریتی | ✅ | KPI، رتبه، هشدار |
| `/reports/data-explorer/` | کاوش داده | ✅ | گزارش‌های Sync + جدول |
| `/reports/visitor-sale/` | جزئیات ویزیتور | ✅ | Data Explorer |
| `/reports/head-visitor-sale/` | جزئیات سرپرست | ✅ | Data Explorer |
| `/reports/sale-reversion/` | برگشت فروش | ✅ | Data Explorer |
| `/reports/sale-distribution-reversion/` | برگشت توزیع | ✅ | Data Explorer |
| `/reports/stuff-group-sale/` | تفکیک گروه کالا | ✅ | Data Explorer |
| `/reports/sync/` | همگام‌سازی | ✅ | وضعیت Sync + لیست گزارش‌ها |
| `/reports/sales/` | فروش | 🔒 Feature Flag | فاز E |
| `/reports/cities/` | شهرها و مناطق | 🔒 | نیاز Analytics |
| `/reports/products/` | کالاها | 🔒 | نیاز 080503 |
| `/reports/targets/` | اهداف | 🔒 | نیاز 080527 |
| `/reports/alerts/` | هشدارها | 🟡 | بخشی در داشبورد |
| `/reports/settings/` | تنظیمات | 🔒 | فاز بعد |

## API

| مسیر | کاربرد |
|------|--------|
| `/reports/api/dashboard/` | داده داشبورد |
| `/reports/api/tv/` | داده TV Mode |
| `/reports/api/dashboard/visitor-ranking/` | رتبه ویزیتور |
| `/reports/api/dashboard/alerts/` | هشدارها |
| `/reports/api/sync/run/` | اجرای Sync |
| `/reports/api/sync/status/` | وضعیت Sync |

## ناوبری اصلی (Header)

```
نمای کلی | TV Mode | ویزیتورها | سرپرستان | کاوش داده | همگام‌سازی
```

آیتم‌های غیرفعال (با Feature Flag) در منو نمایش داده نمی‌شوند:
- فروش، شهرها، کالاها، اهداف (تا کشف API)

## سلسله Drill-down (فاز E)

```
شرکت → شهر → منطقه → سرپرست → ویزیتور → مشتری/کالا
```

Breadcrumb در صفحات تحلیلی؛ فعلاً فقط رتبه‌بندی سطح شرکت.

## تفکیک محصول vs Data Explorer

| محصول اصلی | Data Explorer |
|------------|---------------|
| KPI تجمیعی | ردیف‌های خام |
| رتبه و روند | جدول کامل |
| هشدار | Export CSV/Excel |
| تصمیم سریع | تطبیق با Kara |

**قانون:** کارت «گزارش‌های همگام‌شده» فقط در Sync Center و Data Explorer، نه داشبورد اصلی.
