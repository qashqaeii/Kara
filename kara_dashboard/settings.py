"""
Django settings for kara_dashboard project.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-dev-only-change-in-production",
)

DEBUG = os.environ.get("DJANGO_DEBUG", "True").lower() in ("true", "1", "yes")

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "reports",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "reports.middleware.ReportsLoginRequiredMiddleware",
]

ROOT_URLCONF = "kara_dashboard.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "reports.context_processors.currency_context",
                "reports.context_processors.kara_nav_context",
            ],
        },
    },
]

WSGI_APPLICATION = "kara_dashboard.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {
            # Wait for concurrent writers (runserver + sync + CLI)
            "timeout": 30,
        },
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "fa-ir"
TIME_ZONE = "Asia/Tehran"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/reports/login/"
LOGIN_REDIRECT_URL = "/reports/"
LOGOUT_REDIRECT_URL = "/reports/login/"
WEB_LOGIN_MAX_ATTEMPTS = int(os.environ.get("WEB_LOGIN_MAX_ATTEMPTS", "5"))
WEB_LOGIN_LOCK_MINUTES = int(os.environ.get("WEB_LOGIN_LOCK_MINUTES", "15"))

# Kara integration settings
KARA_BASE_URL = os.environ.get("KARA_BASE_URL", "http://app.pakhshmarket.com")
KARA_USERNAME = os.environ.get("KARA_USERNAME", "")
KARA_PASSWORD = os.environ.get("KARA_PASSWORD", "")
KARA_COOKIE = os.environ.get("KARA_COOKIE", "")
KARA_CREDENTIALS_FILE = os.environ.get(
    "KARA_CREDENTIALS_FILE", str(BASE_DIR / "credentials.txt")
)
KARA_COOKIE_FILE = os.environ.get("KARA_COOKIE_FILE", str(BASE_DIR / "cookies.txt"))
KARA_REQUEST_TIMEOUT = int(os.environ.get("KARA_REQUEST_TIMEOUT", "60"))

# Session recovery
KARA_SESSION_AUTO_RECOVER = os.environ.get("KARA_SESSION_AUTO_RECOVER", "True").lower() in ("true", "1", "yes")
KARA_PERSIST_COOKIES = os.environ.get("KARA_PERSIST_COOKIES", "True").lower() in ("true", "1", "yes")

# Auto-refresh settings — each report uses its own suggested_interval_minutes;
# AUTO_REFRESH_INTERVAL_MINUTES remains a UI / stale-connection pulse for primary KPIs.
AUTO_REFRESH_ENABLED = os.environ.get("AUTO_REFRESH_ENABLED", "True").lower() in ("true", "1", "yes")
AUTO_REFRESH_INTERVAL_MINUTES = int(os.environ.get("AUTO_REFRESH_INTERVAL_MINUTES", "5"))
AUTO_REFRESH_STAGGER_SECONDS = int(os.environ.get("AUTO_REFRESH_STAGGER_SECONDS", "50"))

# TV Mode
TV_SLIDE_INTERVAL_SECONDS = int(os.environ.get("TV_SLIDE_INTERVAL_SECONDS", "20"))
TV_AUTO_REFRESH_SECONDS = int(os.environ.get("TV_AUTO_REFRESH_SECONDS", "60"))

# Currency display — storage remains Rial; UI default is Toman.
# Override with env KARA_CURRENCY_UNIT=rial|toman
KARA_CURRENCY_UNIT = os.environ.get("KARA_CURRENCY_UNIT", "toman").strip().lower()

# Feature flags — see DOCS/KARA_API_DISCOVERY_BACKLOG.md
KARA_FEATURE_PROFITABILITY = os.environ.get("KARA_FEATURE_PROFITABILITY", "False").lower() in (
    "true",
    "1",
    "yes",
)

# Optional: pipe-separated partner group UUIDs for sale_orders (080501)
KARA_SALE_ORDERS_DYNAMIC_PARTNER_GROUPS = os.environ.get(
    "KARA_SALE_ORDERS_DYNAMIC_PARTNER_GROUPS", ""
)

# Comma-separated UUID lists for stuff_group_sale / monthly_sale (from Network dump)
KARA_ENTITY_GROUP_IDS = os.environ.get("KARA_ENTITY_GROUP_IDS", "")
KARA_PARTNER_GROUP_IDS = os.environ.get("KARA_PARTNER_GROUP_IDS", "")

# Storage retention — keep live snapshots only; daily metrics stay in analytics tables.
SNAPSHOT_KEEP_FULL = int(os.environ.get("SNAPSHOT_KEEP_FULL", "1"))
SNAPSHOT_KEEP_DAILY = int(os.environ.get("SNAPSHOT_KEEP_DAILY", "1"))
SYNC_JOB_RETENTION_DAYS = int(os.environ.get("SYNC_JOB_RETENTION_DAYS", "14"))
REFRESH_LOG_KEEP = int(os.environ.get("REFRESH_LOG_KEEP", "100"))

# Cache used for sync locks (use Redis in multi-worker production)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "kara-dashboard",
    }
}

KARA_USER_AGENT = os.environ.get(
    "KARA_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
)

# Bale messenger bot (Telegram-compatible API)
BALE_BOT_TOKEN = os.environ.get("BALE_BOT_TOKEN", "")
BALE_BOT_ENABLED = os.environ.get("BALE_BOT_ENABLED", "False").lower() in (
    "true",
    "1",
    "yes",
)
BALE_ADMIN_IDS = [
    int(x.strip())
    for x in os.environ.get("BALE_ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
]
BALE_LOGIN_MAX_ATTEMPTS = int(os.environ.get("BALE_LOGIN_MAX_ATTEMPTS", "5"))
BALE_LOGIN_LOCK_MINUTES = int(os.environ.get("BALE_LOGIN_LOCK_MINUTES", "15"))
BALE_API_URL = os.environ.get("BALE_API_URL", "https://tapi.bale.ai/bot{0}/{1}")

from django.contrib.messages import constants as message_constants

MESSAGE_TAGS = {
    message_constants.ERROR: "danger",
}
