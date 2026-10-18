from django.db import migrations


def backfill(apps, schema_editor):
    """Use the 'delivered' event time (or last update) for orders delivered before delivered_at existed."""
    Order = apps.get_model("orders", "Order")
    OrderEvent = apps.get_model("orders", "OrderEvent")
    for order in Order.objects.filter(status="delivered", delivered_at__isnull=True):
        event = OrderEvent.objects.filter(order=order, status="delivered").order_by("-created_at").first()
        order.delivered_at = event.created_at if event else order.updated_at
        order.save(update_fields=["delivered_at"])


class Migration(migrations.Migration):
    dependencies = [("orders", "0002_order_delivered_at_orderitem_unit_cost")]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
