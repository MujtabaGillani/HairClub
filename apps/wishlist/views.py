from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from apps.catalog.models import Product
from apps.core.http import is_ajax, redirect_next

from .models import WishlistItem


class WishlistView(LoginRequiredMixin, ListView):
    template_name = "wishlist/wishlist.html"
    context_object_name = "items"
    extra_context = {"active_tab": "wishlist"}

    def get_queryset(self):
        return (
            WishlistItem.objects.filter(user=self.request.user, product__is_active=True)
            .select_related("product", "product__category")
            .prefetch_related("product__images")
        )


@require_POST
def wishlist_toggle(request, product_id):
    ajax = is_ajax(request)
    if not request.user.is_authenticated:
        next_url = request.POST.get("next") or reverse("wishlist:list")
        login_url = f"{reverse('account_login')}?{urlencode({'next': next_url})}"
        if ajax:
            return JsonResponse(
                {"ok": False, "login_url": login_url, "message": "Sign in to save favourites."}, status=401
            )
        return redirect(login_url)

    product = get_object_or_404(Product.objects.visible(), pk=product_id)
    item, created = WishlistItem.objects.get_or_create(user=request.user, product=product)
    if not created:
        item.delete()
    message = f"“{product.name}” {'saved to' if created else 'removed from'} your favourites."
    count = WishlistItem.objects.filter(user=request.user).count()

    if ajax:
        return JsonResponse({"ok": True, "in_wishlist": created, "message": message, "wishlist_count": count})
    messages.success(request, message)
    return redirect_next(request, "wishlist:list")
