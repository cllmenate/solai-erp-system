from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection

from apps.core.models import Tenant


class Command(BaseCommand):
    help = (
        "Runs migrations on the public schema and then "
        "across all active tenant schemas."
    )

    def handle(self, *args, **options):
        db_engine = connection.settings_dict.get("ENGINE", "")
        is_sqlite = "sqlite" in db_engine

        if is_sqlite:
            self.stdout.write(
                self.style.WARNING("SQLite detected. Running standard migration...")
            )
            call_command("migrate", interactive=False)
            self.stdout.write(self.style.SUCCESS("Migrations completed successfully."))
            return

        # 1. Migrate public schema
        self.stdout.write(self.style.NOTICE("Running migrations on public schema..."))
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO public")
        call_command("migrate", interactive=False)

        # 2. Fetch active tenants
        tenants = Tenant.objects.filter(is_active=True)
        self.stdout.write(
            self.style.NOTICE(f"Found {tenants.count()} active tenants to migrate.")
        )

        for tenant in tenants:
            self.stdout.write(
                self.style.WARNING(
                    f"Migrating tenant schema: {tenant.schema_name} "
                    f"({tenant.trade_name})"
                )
            )

            with connection.cursor() as cursor:
                # Ensure schema exists (sanity check)
                cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {tenant.schema_name}")
                # Switch connection path to the tenant schema
                cursor.execute(f"SET search_path TO {tenant.schema_name}, public")

            try:
                call_command("migrate", interactive=False)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Successfully migrated schema '{tenant.schema_name}'."
                    )
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f"Failed to migrate schema '{tenant.schema_name}': {e}"
                    )
                )

        # 3. Reset search path to public
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO public")
        self.stdout.write(self.style.SUCCESS("All migrations completed successfully."))
