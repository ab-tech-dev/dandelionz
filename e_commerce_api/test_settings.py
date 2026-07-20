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

# Product/notification signals send mail. The real backend is SMTP, so without
# this the suite tries to deliver actual email to test addresses on any machine
# where EMAIL_HOST is configured.
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

# Those same signals dispatch Celery tasks. With no broker running each one
# blocks ~8s on a refused connection before falling back to running inline, which
# is most of the suite's runtime. Eager mode skips the broker and runs the task
# body directly -- verified to leave the pass/fail set unchanged (same 5 failures
# and 32 errors either way) while taking the suite from ~186s to ~4s.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = False

# Notifications also broadcast over Channels, whose Redis layer retries against
# localhost:6379 for every send. The in-memory layer keeps the same API without
# a server.
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    }
}
