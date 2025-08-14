"""
Django settings for lmn_payment_gateways project.

Production-ready configuration with environment variables and security.
"""

import os
from pathlib import Path
from decouple import config
import dj_database_url

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Security Settings
SECRET_KEY = config('SECRET_KEY', default='Af31Id8bbNnM8RlZwRQPmJ2185KHf2dF')
DEBUG = config('DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1,lumenario.pythonanywhere.com,lmn.co.ke,lumenario.pythonanywhere.com,local.lmn.co.ke').split(',')

# Application definition
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'corsheaders',
    'drf_spectacular',
    'django_structlog',
    'django_filters',
]

LOCAL_APPS = [
    'core',
    'clients',
    'mpesa',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'core.middleware.api_auth.APIKeyAuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_structlog.middlewares.RequestMiddleware',
]

ROOT_URLCONF = 'lmn_payment_gateways.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'lmn_payment_gateways.wsgi.application'

# Database Configuration
DATABASES = {
    'default': dj_database_url.config(
        default=config('DATABASE_URL', default='mysql://lumenario:Keter7680@lumenario.mysql.pythonanywhere-services.com/lumenario$default')
    )
}

# Upstash REST API
UPSTASH_REDIS_REST_URL = config("UPSTASH_REDIS_REST_URL")
UPSTASH_REDIS_REST_TOKEN = config("UPSTASH_REDIS_REST_TOKEN")

CACHES = {
    "default": {
        "BACKEND": "core.cache.upstash_rest_cache.UpstashRestCache",
        "LOCATION": "",
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Nairobi'  # Kenya timezone for MPesa
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Django REST Framework Configuration
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'core.authentication.MultiAuthentication',  # Use multi-auth for flexibility
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'clients.permissions.api_client_permissions.IsValidClient',  # Use our custom permission
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'EXCEPTION_HANDLER': 'core.exceptions.custom_exception_handler',
}

# API Documentation
SPECTACULAR_SETTINGS = {
    'TITLE': config('API_TITLE', default='Lumenario Payment Gateway API'),
    'DESCRIPTION': config('API_DESCRIPTION', default='A secure payment gateway API'),
    'VERSION': config('API_VERSION', default='1.0.0'),
    'SERVE_INCLUDE_SCHEMA': False,
    'SECURITY': [{'ApiKeyAuth': []}],
    'COMPONENT_SPLIT_REQUEST': True,
}

# CORS Configuration
CORS_ALLOWED_ORIGINS = config('CORS_ALLOWED_ORIGINS', default='').split(',') if config('CORS_ALLOWED_ORIGINS', default='') else []
CORS_ALLOW_CREDENTIALS = True

# Security Settings
if not DEBUG:
    SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)
    SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=31536000, cast=int)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = config('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=True, cast=bool)
    SECURE_HSTS_PRELOAD = config('SECURE_HSTS_PRELOAD', default=True, cast=bool)
    SECURE_CONTENT_TYPE_NOSNIFF = config('SECURE_CONTENT_TYPE_NOSNIFF', default=True, cast=bool)
    SECURE_BROWSER_XSS_FILTER = config('SECURE_BROWSER_XSS_FILTER', default=True, cast=bool)
    SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=True, cast=bool)
    CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=True, cast=bool)

# MPesa Configuration
MPESA_CONFIG = {
    'ENVIRONMENT': config('MPESA_ENVIRONMENT', default='sandbox'),
    'CONSUMER_KEY': config('MPESA_CONSUMER_KEY', default='7ejseeAP94J8QzZGDEM7DBzMXY5eZ8PZpanHnDfT8zc6SwwS'),
    'CONSUMER_SECRET': config('MPESA_CONSUMER_SECRET', default='AD8UduGn4yTfEoJZqNevPoZlCUJhVWR41B4pngcRuMXVhNNYOhS93qmHAYFlGIT1'),
    'SHORTCODE': config('MPESA_SHORTCODE', default='174379'),
    'PASSKEY': config('MPESA_PASSKEY', default='bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919'),
    'INITIATOR_NAME': config('MPESA_INITIATOR_NAME', default='lumenario'),
    'SECURITY_CREDENTIAL': config('MPESA_SECURITY_CREDENTIAL', default='llrG2cOeCF9DCmWYEc/kFIUcFRk429UFdFKK/h7aNs/FxSoWlLTSDG9MgmeAbK5bUEm4STzf2SFK8Qire3Yprcd+9gW2F0YmcEVj//GR79jK0sK9znLxZVmiUh7BX59dgrzBn7m+mOlkboZPI6/FFQ1Cqkslf+O2nQYjLnGOOmUfUgFBlYIe6dFG/vxiYUAsA9eH0LcObwZUBSW1A141NFrtmhkc/XVPWXR2MWAUUKXqhCTCJNz1wY9gcJ6/ZEhTdC8/pQu7Lk7dpnPfQUkUU89CoQuH4cc8xFBw/mVoOwSqh5zIRJWX6uwwp2nUNy2BwT1yhqevxJSPRs2v/IaLWQ=='),
    'STK_CALLBACK_URL': config('MPESA_STK_CALLBACK_URL', default='https://lumenario.pythonanywhere.com/api/v1/mpesa/callback/'),
    'VALIDATION_URL': config('MPESA_VALIDATION_URL', default='https://lumenario.pythonanywhere.com/api/v1/mpesa/validate/'),
    'CONFIRMATION_URL': config('MPESA_CONFIRMATION_URL', default='https://lumenario.pythonanywhere.com/api/v1/mpesa/confirm/'),
}

# Encryption Configuration
ENCRYPTION_CONFIG = {
    'ENCRYPTION_KEY': config('ENCRYPTION_KEY', default='008eIvvBXUAGAywWr0_BzECT5uabladL'),
    'FERNET_KEY': config('FERNET_KEY', default='odp2bd1FTimkq56Rz-yG4arCFADlHq8aT1AnPNdMf4I='),
}

# Logging Configuration
LOG_LEVEL = config('LOG_LEVEL', default='INFO')
LOG_FILE_PATH = config('LOG_FILE_PATH', default=str(BASE_DIR / 'logs'))

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': LOG_LEVEL,
            'class': 'logging.FileHandler',
            'filename': '/home/lumenario/lumenario/logs/payment_gateway.log',
            'formatter': 'verbose',
        },
        'console': {
            'level': LOG_LEVEL,
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file', 'console'],
            'level': LOG_LEVEL,
            'propagate': True,
        },
        'mpesa': {
            'handlers': ['file', 'console'],
            'level': LOG_LEVEL,
            'propagate': True,
        },
        'clients': {
            'handlers': ['file', 'console'],
            'level': LOG_LEVEL,
            'propagate': True,
        },
        'core': {
            'handlers': ['file', 'console'],
            'level': LOG_LEVEL,
            'propagate': True,
        },
    },
}

# Rate Limiting
RATE_LIMIT_CONFIG = {
    'PER_MINUTE': config('RATE_LIMIT_PER_MINUTE', default=100, cast=int),
    'PER_HOUR': config('RATE_LIMIT_PER_HOUR', default=1000, cast=int),
}

# Email Configuration
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='gilbertketer759@gmail.com')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='lcepjkszvrlwaxly')

# Monitoring
ENABLE_MONITORING = config('ENABLE_MONITORING', default=False, cast=bool)
SENTRY_DSN = config('SENTRY_DSN', default='')

if ENABLE_MONITORING and SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        traces_sample_rate=1.0,
        send_default_pii=True
    )
