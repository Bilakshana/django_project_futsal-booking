"""
Django settings for the Futsal Court Booking System.

All secrets and environment-specific values come from .env (see sample.env).
"""

import os
import sys
from datetime import timedelta
from pathlib import Path

from celery.schedules import crontab
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


TESTING = "test" in sys.argv

# DEBUG is off unless .env turns it on (sample.env does, for local development).
DEBUG = env_bool("DEBUG", False)
_DEV_KEY = "django-insecure-dev-only-change-me"
SECRET_KEY = os.getenv("SECRET_KEY") or _DEV_KEY
# simplejwt signs tokens with SECRET_KEY, so a guessable key means forgeable admin tokens.
if not DEBUG and not TESTING and (
    SECRET_KEY == _DEV_KEY or SECRET_KEY.startswith("change-me") or len(SECRET_KEY) < 50
):
    raise ImproperlyConfigured(
        "Set a random SECRET_KEY of 50+ characters in .env when DEBUG is off. Generate one with: "
        'python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"'
    )
ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # project apps
    "apps.accounts",
    "apps.courts",
    "apps.bookings",
    "apps.payments",
    "apps.wallet",
    # third party apps
    "rest_framework",
    "drf_spectacular",
    "django_celery_beat",
    "rest_framework_simplejwt.token_blacklist",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Database
# SQLite by default. Set database=custom_database plus the DB_* variables in .env
# to use PostgreSQL/MySQL (PostgreSQL recommended: it honours select_for_update).

if os.getenv("database") == "custom_database":
    DATABASES = {
        "default": {
            "ENGINE": os.getenv("DB_ENGINE", "django.db.backends.postgresql"),
            "NAME": os.getenv("DB_NAME"),
            "USER": os.getenv("DB_USER"),
            "PASSWORD": os.getenv("DB_PASSWORD"),
            "HOST": os.getenv("DB_HOST", "127.0.0.1"),
            "PORT": os.getenv("DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.getenv("ACCESS_TOKEN_LIFETIME", "30"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "ALGORITHM": "HS256",
    "AUTH_HEADER_TYPES": ("Bearer",),
}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Internationalization

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kathmandu"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/min",
        "user": "240/min",
        # stricter limits for abuse-prone endpoints (see apps/accounts/api/throttles.py)
        "login": "10/min",
        "register": "5/hour",
        "hold": "10/min",
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Futsal Court Booking API",
    "DESCRIPTION": "Hold a slot, pay the advance with Khalti, get a confirmed booking.",
    "VERSION": "1.0.0",
}

# Email (reminders are printed to the console in development)
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "bookings@futsal.local")


# Booking rules
SLOT_HOLD_SECONDS = int(os.getenv("SLOT_HOLD_SECONDS", "600"))  # unpaid holds are released after 10 minutes
ADVANCE_PERCENT = int(os.getenv("ADVANCE_PERCENT", "30"))  # advance = 30% of the slot price
MIN_ADVANCE_AMOUNT = 10  # Khalti's minimum payment is Rs. 10
MAX_ACTIVE_HOLDS = 2  # unpaid holds one player may have at once (stops slot hoarding)
SLOT_GENERATION_DAYS = 7
REMINDER_LEAD_MINUTES = 60


# Khalti (sandbox by default: https://dev.khalti.com)
KHALTI_TOKEN = os.getenv("KHALTI_TOKEN", "")  # the sandbox *secret key*; never commit it
KHALTI_BASE_URL = os.getenv("KHALTI_BASE_URL", "https://dev.khalti.com/api/v2").rstrip("/")
KHALTI_RETURN_URL = os.getenv("KHALTI_RETURN_URL", "http://localhost:8000/payment/callback/")
KHALTI_WEBSITE_URL = os.getenv("KHALTI_WEBSITE_URL", "http://localhost:8000/")
KHALTI_TIMEOUT = 15


# Celery (Redis broker)
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

FLOWER_URL = "http://localhost:5555"

CELERY_BEAT_SCHEDULE = {
    "generate-daily-slots": {
        "task": "apps.courts.tasks.generate_daily_slots",
        "schedule": crontab(hour=0, minute=5),  # nightly
    },
    "send-booking-reminders": {
        "task": "apps.bookings.tasks.send_booking_reminder",
        "schedule": crontab(minute="*/5"),
    },
    "mark-completed-bookings": {
        "task": "apps.bookings.tasks.mark_completed_bookings",
        "schedule": crontab(minute="*/10"),
    },
    # safety nets for lost broker messages / players who never return from Khalti
    "release-expired-holds": {
        "task": "apps.bookings.tasks.release_expired_holds",
        "schedule": crontab(minute="*"),
    },
    "reconcile-payments": {
        "task": "apps.payments.tasks.reconcile_payments",
        "schedule": crontab(minute="*/5"),
    },
    "credit-missing-wallets": {
        "task": "apps.wallet.tasks.credit_missing_wallets",
        "schedule": crontab(minute="*/15"),
    },
}

if not DEBUG and not TESTING:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    if not KHALTI_RETURN_URL.startswith("https://"):
        raise ImproperlyConfigured("KHALTI_RETURN_URL must be https:// when DEBUG is off")

if TESTING:
    # Tests must not need Redis: run tasks inline against an in-memory broker.
    CELERY_BROKER_URL = "memory://"
    CELERY_RESULT_BACKEND = "cache+memory://"
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True
    KHALTI_TOKEN = "test-token"
    # per-IP/user throttles would trip over the many requests a test run makes
    REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"].update(login="10000/min", register="10000/min", hold="10000/min")
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # fast tests
    EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
