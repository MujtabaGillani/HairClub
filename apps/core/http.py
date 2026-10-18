from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme


def is_ajax(request) -> bool:
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def redirect_next(request, fallback, *fallback_args, **fallback_kwargs):
    """Redirect to ``next`` (POST or GET) only if it points at this site; otherwise to ``fallback``."""
    target = request.POST.get("next") or request.GET.get("next") or ""
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(target)
    return redirect(fallback, *fallback_args, **fallback_kwargs)


def actor(user):
    """The user to record on audit fields, or ``None`` for anonymous visitors."""
    return user if user is not None and user.is_authenticated else None
