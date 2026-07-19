from .settings import *  # noqa: F401,F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'test_db.sqlite3',
    }
}

PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

SECURE_SSL_REDIRECT = False

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

# Paystack is never actually called in tests - every suite patches the HTTP methods. But
# constructing a Paystack client now raises ImproperlyConfigured when the key is missing,
# rather than silently building a client with a None key that fails later inside webhook
# signature verification. Tests need a value present for that construction to succeed.
PAYSTACK_SECRET_KEY = 'sk_test_dummy_secret'

