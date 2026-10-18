from django.conf import settings

from .models import SiteSettings
from .whatsapp import build_whatsapp_url


def site(request):
    site_settings = SiteSettings.load()
    return {
        "site_settings": site_settings,
        "currency_symbol": settings.CURRENCY_SYMBOL,
        "whatsapp_chat_url": build_whatsapp_url(
            site_settings.whatsapp_number,
            f"Hi {site_settings.business_name}, I have a question.",
        ),
    }
