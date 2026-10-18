from getpass import getpass

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Role, User


class Command(BaseCommand):
    help = "Create a vendor (salon staff) account, or promote an existing user to vendor."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--first-name", default="")
        parser.add_argument("--password", help="Omit to be prompted securely.")

    def handle(self, *args, email, first_name, password, **options):
        email = email.strip().lower()
        user = User.objects.filter(email__iexact=email).first()
        if user:
            user.role = Role.VENDOR
            user.save(update_fields=["role"])
            if options["verbosity"]:
                self.stdout.write(self.style.SUCCESS(f"Promoted {email} to vendor."))
            return

        password = password or getpass("Password: ")
        try:
            validate_password(password)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc

        User.objects.create_user(
            username=email, email=email, password=password, first_name=first_name, role=Role.VENDOR
        )
        if options["verbosity"]:
            self.stdout.write(self.style.SUCCESS(f"Vendor account {email} created."))
