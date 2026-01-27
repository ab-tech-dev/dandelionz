import os
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader
import cloudinary.api

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

# Build paths inside the project

# SECURITY
SECRET_KEY = os.getenv('SECRET_KEY')
DEBUG = os.getenv('DEBUG', 'False') == 'True'
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS').split(',')


REFERRAL_BONUS_AMOUNT = os.getenv('REFERRAL_BONUS_AMOUNT')  # Could be Naira, points, etc.


# Application definition
INSTALLED_APPS = [
    # Local apps
    'django_admin_trap',
    'authentication',
    'users.apps.UsersConfig',
    'store',
    'transactions.apps.TransactionsConfig',

    # Django default apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',


    # Third-party apps
    'cloudinary',
    'cloudinary_storage',
    'corsheaders',
    'rest_framework',
    'drf_yasg',
    'django_celery_results',
    'django_celery_beat',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "https://dandelionz.com.ng",
    "https://app.dandelionz.com.ng",
    "https://api.dandelionz.com.ng",
]

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
]

CSRF_TRUSTED_ORIGINS = [
    "http://localhost:3000",
    "https://dandelionz.com.ng",
    "https://app.dandelionz.com.ng",
    "https://api.dandelionz.com.ng",
]

ROOT_URLCONF = 'e_commerce_api.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'e_commerce_api.wsgi.application'

SITE_ID = 1


# Database (PostgreSQL on VPS)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME'),
        'USER': os.getenv('DB_USER'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST'),  
        'PORT': int(os.getenv('DB_PORT')),
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files
# STATIC_URL = '/static/'
# STATIC_ROOT = BASE_DIR / 'staticfiles'
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'


# Default primary key
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# JWT settings
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=14),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'uuid',
    'USER_ID_CLAIM': 'user_uuid',
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
}


JWT_COOKIE_SECURE = True
JWT_COOKIE_NAME = 'refresh_token'
SESSION_COOKIE_DOMAIN = None

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour',
        # Stricter limits for sensitive operations
        'payment_verification': '5/min',  # Payment verification: 5 requests per minute
        'installment_verification': '5/min',  # Installment payment verification: 5 requests per minute
        'checkout': '10/min',  # Checkout endpoint: 10 requests per minute
    }
}

# Celery (Redis on VPS)
CELERY_TIMEZONE = "Africa/Lagos"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL')
CELERY_RESULT_BACKEND = os.getenv('CELERY_BROKER_URL')

# Celery Logging Configuration
CELERY_WORKER_LOG_LEVEL = os.getenv('CELERY_WORKER_LOG_LEVEL', 'INFO')
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_SEND_SENT_EVENT = True
CELERY_WORKER_SEND_TASK_EVENTS = True
CELERYD_LOG_FORMAT = '[%(asctime)s: %(levelname)s/%(processName)s] %(message)s'
CELERYD_TASK_LOG_FORMAT = '[%(asctime)s: %(levelname)s/%(processName)s] [%(task_name)s(%(task_id)s)] %(message)s'

# Django Caching (Redis on VPS)
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": str(os.getenv('REDIS_URL')),
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    }
}

# Frontend URL
FRONTEND_URL = 'https://app.dandelionz.com.ng'

# Email & Verification
REQUIRE_EMAIL_VERIFICATION = True
EMAIL_VERIFICATION_TIMEOUT = 3600 * 24
APP_NAME = 'Dandelionz'
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL')
AUTH_USER_MODEL = 'authentication.CustomUser'

from dotenv import load_dotenv
import os
from pathlib import Path



# Email & Verification

EMAIL_BACKEND = 'authentication.core.email_backend.RobustSMTPEmailBackend'
EMAIL_HOST = os.getenv('EMAIL_HOST')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))

EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'False').lower() in ('true', '1', 'yes')
EMAIL_USE_SSL = os.getenv('EMAIL_USE_SSL', 'False').lower() in ('true', '1', 'yes')

EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')

# SMTP Connection Settings
EMAIL_TIMEOUT = 60  # 60 seconds timeout for SMTP operations (increased to prevent read timeouts)
EMAIL_CONNECTION_RETRY_ATTEMPTS = 3
EMAIL_CONNECTION_RETRY_DELAY = 2  # seconds between retries


# Logging Configuration with Celery Support
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {name} {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
            'level': 'DEBUG',
        },
    },
    'loggers': {
        # Root logger - catch all logs
        '': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        # Django logging
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        # Celery task logging
        'celery': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'celery.task': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'celery.worker': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        # Application-specific loggers
        'authentication': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'store': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'transactions': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'users': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}

# Paystack
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
PAYSTACK_PUBLIC_KEY = os.getenv("PAYSTACK_PUBLIC_KEY")
PAYSTACK_BASE_URL = os.getenv("PAYSTACK_BASE_URL", "https://api.paystack.co")
PAYSTACK_CALLBACK_URL = os.getenv(
    "PAYSTACK_CALLBACK_URL",
    "https://api.dandelionz.com.ng/transactions/verify-payment/"
)
PAYSTACK_WEBHOOK_URL = os.getenv(
    "PAYSTACK_WEBHOOK_URL",
    "https://api.dandelionz.com.ng/transactions/webhook/"
)

# Cloudinary
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)
DEFAULT_FILE_STORAGE = os.getenv("CLOUDINARY_URL")


SWAGGER_SETTINGS = {
    'SECURITY_DEFINITIONS': {
        'Bearer': {
            'type': 'apiKey',
            'name': 'Authorization',
            'in': 'header',
            'description': 'JWT Authorization header using the Bearer scheme. Example: "Bearer {token}"'
        }
    },
    'USE_SESSION_AUTH': False,
}
