# برنامه اجرای مرحله‌ای

## فاز A: تثبیت پایه ← ✅ انجام‌شده

| کار | وضعیت |
|-----|--------|
| رفع Double Count | ✅ analytics از visitor_sale فقط |
| منبع حقیقت KPI | ✅ PRIMARY_KPI_REPORT |
| Sync قابل اعتماد | ✅ SyncOrchestrator |
| Data freshness | ✅ connection_status + stale |
| تفکیک Dashboard / Data Explorer | ✅ |
| TV Mode shell | ✅ |
| Permission architecture | ✅ UserKaraIdentity |
| عدم نمایش سود بدون داده | ✅ profitability banner |
| اسناد PLAN (۱۰ خروجی) | ✅ DOCS/ |

## فاز B: کشف داده سودآوری ← ✅ تا حد شرکت

- ✅ 080501 / 080503 در Sync
- ✅ 080106 Print (LostBenefit) → `profit_and_loss`
- ✅ 080533 / 080534 مطالبات
- ⬜ سود کالایی / ranking سود (نیاز COGS تفصیلی)

## فاز C: مدل تحلیلی ← 🟡 در حال تکمیل

- ✅ Dimensions/Facts روزانه برای فروش
- ✅ CompanyProfitLossMetric / ReceivableDailyMetric
- ✅ Period comparison + trend
- ⬜ Backfill تاریخی گسترده

## فاز D: TV Mode نسخه ۱ ← ✅

- ✅ اسلاید KPI / رتبه / هشدار / جغرافیا / ماهانه / کالا
- ✅ اسلاید سودآوری وقتی 080106 sync شود
- ✅ مطالبات در API TV
- ✅ بازطراحی بصری TV (فاز UI/UX)
- ✅ TV Mode حرفه‌ای: ۹ اسلاید سینمایی، نمودار، podium، progress، کیبورد

## فاز UI/UX — پوسته محصول ← ✅

- ✅ Design tokens (ink / charcoal-teal / copper) — بدون indigo
- ✅ `base.html` + nav گروه‌بندی‌شده + تایپوگرافی IBM Plex / Vazirmatn
- ✅ داشبورد: نوار فرمان، KPI strip، charts دوستونه، رتبه، مطالبات/جغرافیا
- ✅ یکدست‌سازی صفحات analytics / my_performance / explorer / sync
- ✅ TV Mode هم‌خانواده با shell

## فاز E / F

- ✅ صفحه مطالبات `/reports/analytics/receivables/`
- ⬜ تحقق هدف 080527
- ⬜ پنل شخصی کامل با login

---

## آنچه عمداً انجام نمی‌شود (این مرحله)

- UI کامل همه گزارش‌های منو
- KPI سود کالایی حدسی
- نقشه جغرافیایی بدون داده
- هوش مصنوعی / Forecast

---

## وابستگی‌های کاربر (باقی‌مانده)

1. **080527** تحقق هدف
2. **080524** لیست ویزیت
3. **080540** فروش ویزیتور–طرف‌حساب

قالب: مانند `DOCS/api_docs.txt`
