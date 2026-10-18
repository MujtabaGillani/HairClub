"""WSGI entry point. Defaults to production settings."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "HairClub.settings.prod")

application = get_wsgi_application()
