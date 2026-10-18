"""Access control helpers for vendor-only areas."""

from functools import wraps

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied


def user_is_vendor(user) -> bool:
    return bool(user and user.is_authenticated and getattr(user, "is_vendor", False))


class VendorRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Anonymous users are sent to login; signed-in non-vendors get HTTP 403."""

    raise_exception = False

    def test_func(self):
        return user_is_vendor(self.request.user)

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            raise PermissionDenied("Vendor access required.")
        return super().handle_no_permission()


def vendor_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not user_is_vendor(request.user):
            raise PermissionDenied("Vendor access required.")
        return view_func(request, *args, **kwargs)

    return _wrapped
