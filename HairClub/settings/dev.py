"""Local development settings."""

from .base import *  # noqa: F401,F403
from .base import env_bool, os

DEBUG = env_bool("DJANGO_DEBUG", True)
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY") or "django-insecure-dev-only-key-change-me"  # noqa: S105
ALLOWED_HOSTS = ["*"]

# runserver serves static files itself; WhiteNoise is for production.
MIDDLEWARE = [m for m in MIDDLEWARE if m != "whitenoise.middleware.WhiteNoiseMiddleware"]  # noqa: F405
