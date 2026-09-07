"""
Django settings for kara_dashboard project.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

_DEV_SECRET_KEY = "django-insecure-dev-only-change-in-production"

DEBUG = os.environ.get("DJANGO_DEBUG", "True").lower() in ("true", "1", "yes")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", _DEV_SECRET_KEY)
if not DEBUG and (not SECRET_KEY or SECRET_KEY == _DEV_SECRET_KEY):
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be set to a unique value when DJANGO_DEBUG=False."
    )

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get(
        "DJANGO_ALLOWED_HOSTS",
        "localhost,127.0.0.1,portal.pakhshmarket.com,85.198.10.243",
    ).split(",")
    if host.strip()
]

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "DJANGO_CSRF_TRUSTED_ORIGINS",
        "https://portal.pakhshmarket.com",
    ).split(",")
    if origin.strip()
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

DATABASE_ENGINE = os.environ.get("DATABASE_ENGINE", "").strip().lower()
if DATABASE_ENGINE in ("postgresql", "postgres") or os.environ.get("POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("POSTGRES_DB", "kara"),
            "USER": os.environ.get("POSTGRES_USER", "kara"),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
            "HOST": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": int(os.environ.get("DB_CONN_MAX_AGE", "60")),
            "OPTIONS": {
                "connect_timeout": int(os.environ.get("DB_CONNECT_TIMEOUT", "10")),
            },
        }
    }
else:
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

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = Path(os.environ.get("DJANGO_STATIC_ROOT", str(BASE_DIR / "staticfiles")))

MEDIA_URL = "/media/"
MEDIA_ROOT = Path(os.environ.get("DJANGO_MEDIA_ROOT", str(BASE_DIR / "media")))

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

# Cache — locmem for dev; file/redis for production multi-process.
_CACHE_DIR = Path(os.environ.get("KARA_CACHE_DIR", str(BASE_DIR / "data" / "cache")))
if os.environ.get("REDIS_URL"):
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": os.environ["REDIS_URL"],
        }
    }
elif not DEBUG:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
            "LOCATION": str(_CACHE_DIR),
        }
    }
else:
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
BALE_CONNECT_TIMEOUT = int(os.environ.get("BALE_CONNECT_TIMEOUT", "10"))
BALE_READ_TIMEOUT = int(os.environ.get("BALE_READ_TIMEOUT", "30"))

from django.contrib.messages import constants as message_constants

MESSAGE_TAGS = {
    message_constants.ERROR: "danger",
}

# --- Production security (behind Nginx + TLS) ---
def _env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).lower() in ("true", "1", "yes")


if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = _env_bool("DJANGO_USE_X_FORWARDED_HOST", True)
    # Phase 1 (pre-Certbot): keep False. Phase 2 (post-Certbot): set True in .env
    SECURE_SSL_REDIRECT = _env_bool("DJANGO_SECURE_SSL_REDIRECT", False)
    SESSION_COOKIE_SECURE = _env_bool("DJANGO_SESSION_COOKIE_SECURE", True)
    CSRF_COOKIE_SECURE = _env_bool("DJANGO_CSRF_COOKIE_SECURE", True)
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = "DENY"
    if SECURE_SSL_REDIRECT:
        SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", "31536000"))
        SECURE_HSTS_INCLUDE_SUBDOMAINS = True
        SECURE_HSTS_PRELOAD = _env_bool("DJANGO_HSTS_PRELOAD", True)
    else:
        SECURE_HSTS_SECONDS = 0
        SECURE_HSTS_INCLUDE_SUBDOMAINS = False
        SECURE_HSTS_PRELOAD = False

# --- Logging ---
_LOG_DIR = Path(os.environ.get("KARA_LOG_DIR", str(BASE_DIR / "logs")))
_LOG_LEVEL = os.environ.get("KARA_LOG_LEVEL", "INFO" if not DEBUG else "DEBUG")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "sensitive": {
            "()": "reports.logging_utils.SensitiveDataFilter",
        },
    },
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["sensitive"],
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": _LOG_LEVEL,
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO" if not DEBUG else "DEBUG",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "reports": {
            "handlers": ["console"],
            "level": _LOG_LEVEL,
            "propagate": False,
        },
    },
}

if not DEBUG:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    LOGGING["handlers"]["file"] = {
        "class": "logging.handlers.RotatingFileHandler",
        "filename": str(_LOG_DIR / "kara.log"),
        "maxBytes": 10 * 1024 * 1024,
        "backupCount": 5,
        "filters": ["sensitive"],
        "formatter": "verbose",
    }
    LOGGING["root"]["handlers"].append("file")
    for logger_name in ("django", "django.request", "reports"):
        LOGGING["loggers"][logger_name]["handlers"].append("file")
