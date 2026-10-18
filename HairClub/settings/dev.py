"""Local development settings."""

from .base import *  # noqa: F401,F403
from .base import CSRF_TRUSTED_ORIGINS, env_bool, os

DEBUG = env_bool("DJANGO_DEBUG", True)
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY") or "django-insecure-dev-only-key-change-me"  # noqa: S105
ALLOWED_HOSTS = ["*"]

# Sharing the dev server through an HTTPS tunnel (ngrok, Cloudflare Tunnel).
# The tunnel terminates HTTPS, so trust its domains for CSRF and honour its
# X-Forwarded-Proto header so absolute URLs (e.g. Google OAuth callback) use https.
CSRF_TRUSTED_ORIGINS = [
    *CSRF_TRUSTED_ORIGINS,
    "https://*.ngrok-free.app",
    "https://*.ngrok.app",
    "https://*.ngrok.io",
    "https://*.trycloudflare.com",
]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# runserver serves static files itself; WhiteNoise is for production.
MIDDLEWARE = [m for m in MIDDLEWARE if m != "whitenoise.middleware.WhiteNoiseMiddleware"]  # noqa: F405
