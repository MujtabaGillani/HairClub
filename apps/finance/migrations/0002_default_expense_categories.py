from django.db import migrations

DEFAULT_CATEGORIES = [
    ("Salaries & wages", "people"),
    ("Rent", "house-door"),
    ("Utilities", "lightning-charge"),
    ("Food & refreshments", "cup-hot"),
    ("Entertainment", "balloon"),
    ("Marketing & ads", "megaphone"),
    ("Courier & delivery", "truck"),
    ("Salon supplies", "basket"),
    ("Equipment & repairs", "tools"),
    ("Bank & payment fees", "bank"),
    ("Taxes & licences", "file-earmark-text"),
    ("Other", "three-dots"),
]


def create_categories(apps, schema_editor):
    ExpenseCategory = apps.get_model("finance", "ExpenseCategory")
    for order, (name, icon) in enumerate(DEFAULT_CATEGORIES):
        ExpenseCategory.objects.get_or_create(name=name, defaults={"icon": icon, "sort_order": order})


class Migration(migrations.Migration):
    dependencies = [("finance", "0001_initial")]
    operations = [migrations.RunPython(create_categories, migrations.RunPython.noop)]
