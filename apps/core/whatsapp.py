"""Helpers for building click-to-chat WhatsApp links (https://wa.me)."""

import re
from urllib.parse import quote

WHATSAPP_BASE_URL = "https://wa.me"


def normalize_phone(phone: str, default_country_code: str = "92") -> str:
    """
    Convert a human-entered phone number into the digits-only international
    format wa.me expects. ``0300 1234567`` becomes ``923001234567``.
    """
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("00"):
        digits = digits[2:]
    elif digits.startswith("0"):
        digits = default_country_code + digits[1:]
    return digits


def build_whatsapp_url(phone: str, message: str = "") -> str:
    number = normalize_phone(phone)
    url = f"{WHATSAPP_BASE_URL}/{number}"
    if message:
        url += f"?text={quote(message, safe='')}"
    return url
