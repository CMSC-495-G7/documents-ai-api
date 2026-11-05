"""Creates the Engineering workspace, 1 admin and 1 employee.

Ok to run more than once. Passwords come from .env.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from users.models import User, Workspace


class Command(BaseCommand):
    help = "Create the Engineering workspace with one admin and one employee."

    @transaction.atomic
    def handle(self, *args, **options):
        workspace, _ = Workspace.objects.get_or_create(
            slug="engineering", defaults={"name": "Engineering"}
        )

        seeds = [
            (settings.SEED_ADMIN_EMAIL, settings.SEED_ADMIN_PASSWORD, User.Role.ADMIN),
            (settings.SEED_EMPLOYEE_EMAIL, settings.SEED_EMPLOYEE_PASSWORD, User.Role.EMPLOYEE),
        ]
        for email, password, role in seeds:
            if not password:
                raise CommandError(f"Password cannot be empty for {email}.")

            user, created = User.objects.get_or_create(
                email=email.lower(),
                defaults={"role": role, "workspace": workspace},
            )
            # Update every run so .env changes stick.
            user.role = role
            user.workspace = workspace
            user.set_password(password)
            user.save()

            self.stdout.write(f"{'Created' if created else 'Updated'} {role}: {user.email}")

        self.stdout.write(self.style.SUCCESS("Seed done."))
