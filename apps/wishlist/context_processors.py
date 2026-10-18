def wishlist(request):
    """IDs of the signed-in user's favourites, so product cards can show a filled heart."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"wishlist_ids": set(), "wishlist_count": 0}
    ids = set(user.wishlist_items.values_list("product_id", flat=True))
    return {"wishlist_ids": ids, "wishlist_count": len(ids)}
