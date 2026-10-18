"""Settings used by the automated test-suite."""

import tempfile

from .dev import *  # noqa: F401,F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
MEDIA_ROOT = tempfile.mkdtemp(prefix="hairclub-test-media-")
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
LOGGING = {"version": 1, "disable_existing_loggers": True}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
