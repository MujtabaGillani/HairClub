from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.catalog.models import Product
from apps.core.http import is_ajax, redirect_next
from apps.core.models import SiteSettings
from apps.orders.models import ShippingMethod
from apps.orders.services import calculate_shipping

from .forms import CartAddForm, CartUpdateForm
from .services import Cart


def cart_detail(request):
    cart = Cart(request)
    site = SiteSettings.load()
    subtotal = cart.subtotal
    shipping = calculate_shipping(subtotal, ShippingMethod.STANDARD, site)
    threshold = site.free_shipping_threshold
    return render(
        request,
        "cart/cart_detail.html",
        {
            "cart": cart,
            "shipping_estimate": shipping,
            "estimated_total": subtotal + shipping,
            "free_shipping_remaining": threshold - subtotal if threshold and 0 < subtotal < threshold else 0,
        },
    )


@require_POST
def cart_add(request, product_id):
    product = get_object_or_404(Product.objects.visible(), pk=product_id)
    form = CartAddForm(request.POST)
    cart = Cart(request)

    if not product.is_purchasable:
        msg, ok = f"“{product.name}” is not available to buy online.", False
    elif not form.is_valid():
        msg, ok = "Please choose a valid quantity.", False
    else:
        in_cart_before = cart.quantity_of(product.pk)
        final_qty = cart.add(product, form.cleaned_data["quantity"])
        if final_qty == in_cart_before:
            msg, ok = f"You already have the maximum available quantity of “{product.name}”.", False
        else:
            msg, ok = f"“{product.name}” added to your cart.", True

    if is_ajax(request):
        return JsonResponse({"ok": ok, "message": msg, "cart_count": len(cart)}, status=200 if ok else 400)
    (messages.success if ok else messages.warning)(request, msg)
    return redirect_next(request, "cart:detail")


@require_POST
def cart_update(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    form = CartUpdateForm(request.POST)
    cart = Cart(request)
    if form.is_valid():
        requested = form.cleaned_data["quantity"]
        final_qty = cart.add(product, requested, replace=True)
        if requested > final_qty:
            messages.warning(request, f"Only {final_qty} of “{product.name}” available.")
        else:
            messages.success(request, "Cart updated.")
    else:
        messages.error(request, "Please choose a valid quantity.")
    return redirect("cart:detail")


@require_POST
def cart_remove(request, product_id):
    Cart(request).remove(product_id)
    messages.info(request, "Item removed from your cart.")
    return redirect("cart:detail")
