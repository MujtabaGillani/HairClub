import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout

LAST_SEEN_KEY = "_last_seen"
WRITE_EVERY_SECONDS = 60  # avoid a session write on every request


class BrowserSessionTimeoutMiddleware:
    """
    Make an unticked "Remember me" mean something.

    allauth marks such sessions "expire at browser close", but browsers that
    restore tabs (e.g. Chrome's "Continue where you left off") also restore the
    cookie, and the server-side session would otherwise live for
    SESSION_COOKIE_AGE. Here, those sessions also end after
    BROWSER_SESSION_IDLE_TIMEOUT seconds without activity. Remembered sessions
    are untouched.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        session = getattr(request, "session", None)
        user = getattr(request, "user", None)
        if session is not None and user is not None and user.is_authenticated and session.get_expire_at_browser_close():
            now = int(time.time())
            last_seen = session.get(LAST_SEEN_KEY)
            if last_seen and now - last_seen > settings.BROWSER_SESSION_IDLE_TIMEOUT:
                logout(request)
                messages.info(
                    request, "You were signed out after a period of inactivity. Tick “Remember me” to stay signed in."
                )
            elif not last_seen or now - last_seen >= WRITE_EVERY_SECONDS:
                session[LAST_SEEN_KEY] = now
        return self.get_response(request)
