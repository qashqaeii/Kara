# طراحی TV Mode

## مسیر

```
/tv/
```

صفحه مستقل، بدون Sidebar، تمام‌صفحه، مناسب 1920×1080.

## اصول UX

- اعداد بزرگ، خوانا از فاصله
- بدون جدول طولانی و Scroll در هر اسلاید
- بروزرسانی AJAX بدون Reload کامل
- نمایش زمان آخرین Sync
- هشدار واضح اگر داده قدیمی (`stale`)
- چرخش خودکار ۱۵–۳۰ ثانیه (قابل تنظیم از `TV_SLIDE_INTERVAL_SECONDS`)
- دکمه توقف/ادامه چرخش
- دکمه Fullscreen
- **بدون** لینک «جزئیات گزارش Kara»
- **بدون** نمایش سود/زیان تا `FEATURE_PROFITABILITY=true`

---

## اسلایدها

### اسلاید ۱: نبض کسب‌وکار

| عنصر | منبع داده | وضعیت فاز D |
|------|-----------|-------------|
| فروش خالص (دوره جاری) | visitor_sale SumRowData | ✅ |
| تعداد سفارش نهایی | visitor_sale | ✅ |
| برگشت (فروش + توزیع) | visitor_sale | ✅ |
| نرخ برگشت | مشتق | ✅ |
| سود ناخالص | — | ❌ بنر «داده سودآوری کامل نیست» |
| حاشیه سود | — | ❌ |
| مقایسه دوره قبل | DailyBusinessMetric | 🟡 فاز C |
| وضعیت کلی (مطلوب/توجه/بحرانی) | قوانین alert | 🟡 |
| نمودار روند ۷ روز | DailyBusinessMetric | 🟡 فاز C |

### اسلاید ۲: عملکرد فروش

| عنصر | منبع | وضعیت |
|------|------|--------|
| ۵ ویزیتور برتر (فروش) | visitor_sale rows | ✅ |
| ۵ سرپرست برتر | head_visitor_sale | ✅ |
| بیشترین رشد | مقایسه دوره | 🟡 |
| بیشترین افت | مقایسه دوره | 🟡 |
| تحقق هدف | 080527 | ❌ |
| نیروهای بدون فروش | visitor_sale | ✅ (alert) |

### اسلاید ۳: جغرافیا

| عنصر | منبع | وضعیت |
|------|------|--------|
| بهترین شهرها | stuff_group_sale + City | 🟡 Partial |
| بهترین مناطق | stuff_group_sale + Zone | 🟡 Partial |
| سهم فروش | تجمیع stuff_group | 🟡 |
| نقشه | — | ❌ تا mapping معتبر → Bar Chart |

### اسلاید ۴: کالا و سودآوری

| عنصر | وضعیت |
|------|--------|
| پرفروش (مبلغ/تعداد) | ❌ نیاز 080503 |
| پرسود | ❌ |
| Quadrant | ❌ |
| **جایگزین فاز D:** پیام «بخش سودآوری پس از کشف API فعال می‌شود» | ✅ |

### اسلاید ۵: هشدارهای مدیریتی

| هشدار | منبع | وضعیت |
|-------|------|--------|
| تأخیر Sync | connection_status | ✅ |
| ویزیتور بدون فروش | evaluate_alerts | ✅ |
| نرخ بالای برگشت توزیع | evaluate_alerts | ✅ |
| افت فروش غیرعادی | — | 🟡 فاز C |
| Sync ناموفق | KaraSyncJob | ✅ |

---

## کامپوننت‌ها (پیاده‌سازی)

```
tv_base.html          — قالب تمام‌صفحه بدون nav
tv_mode.html          — container اسلایدها
static/css/tv-mode.css
static/js/tv-mode.js  — چرخش، fullscreen، poll API
TvModeView            — render shell
TvModeAPIView           — JSON برای اسلایدها
```

## ساختار پاسخ API `/reports/api/tv/`

```json
{
  "connection": { "last_sync_label": "...", "status": "connected" },
  "profitability": {
    "status": "api_not_discovered",
    "message": "داده سودآوری هنوز کامل نیست"
  },
  "pulse": { "total_pure_sale": "...", "order_count": "...", "reversion_rate": "..." },
  "top_visitors": [...],
  "top_supervisors": [...],
  "geo": { "available": false, "cities": [] },
  "alerts": [...],
  "slide_interval_seconds": 20
}
```

## تنظیمات

| متغیر env | پیش‌فرض | توضیح |
|-----------|---------|--------|
| `TV_SLIDE_INTERVAL_SECONDS` | 20 | مدت هر اسلاید |
| `TV_AUTO_REFRESH_SECONDS` | 60 | بازخوانی API |
