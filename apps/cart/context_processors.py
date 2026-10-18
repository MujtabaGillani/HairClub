from django.conf import settings


def cart(request):
    """Cheap item count for the header badge: reads the session only, no queries."""
    session = getattr(request, "session", None)
    items = (session.get(settings.CART_SESSION_KEY) if session is not None else None) or {}
    try:
        count = sum(int(q) for q in items.values())
    except (TypeError, ValueError, AttributeError):
        count = 0
    return {"cart_count": count}
