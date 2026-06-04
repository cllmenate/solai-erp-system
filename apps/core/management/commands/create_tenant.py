import datetime

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.utils import timezone

from apps.core.models import Tenant


class Command(BaseCommand):
    help = (
        "Creates a new Tenant, sets up its PostgreSQL schema, "
        "migrates it, and creates an admin user."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--company-name",
            required=True,
            type=str,
            help="Company name (Razão Social)",
        )
        parser.add_argument(
            "--trade-name", required=True, type=str, help="Trade name (Nome Fantasia)"
        )
        parser.add_argument(
            "--cnpj", required=True, type=str, help="CNPJ (valid document format)"
        )
        parser.add_argument(
            "--subdomain",
            required=True,
            type=str,
            help="Unique subdomain for URL routing",
        )
        parser.add_argument(
            "--schema-name",
            required=True,
            type=str,
            help="PostgreSQL schema name (unique identifier)",
        )
        parser.add_argument(
            "--admin-username",
            default="admin",
            type=str,
            help="Admin username for the tenant",
        )
        parser.add_argument(
            "--admin-email",
            default="admin@example.com",
            type=str,
            help="Admin email for the tenant",
        )
        parser.add_argument(
            "--admin-password",
            default="admin123",
            type=str,
            help="Admin password for the tenant",
        )

    def handle(self, *args, **options):
        company_name = options["company_name"]
        trade_name = options["trade_name"]
        cnpj = options["cnpj"]
        subdomain = options["subdomain"]
        schema_name = options["schema_name"]
        admin_username = options["admin_username"]
        admin_email = options["admin_email"]
        admin_password = options["admin_password"]

        db_engine = connection.settings_dict.get("ENGINE", "")
        is_sqlite = "sqlite" in db_engine

        self.stdout.write(
            self.style.WARNING(
                f"Starting provisioning for tenant: {trade_name} ({schema_name})"
            )
        )

        # Step 1: Create the Tenant record in the public schema
        if not is_sqlite:
            # Explicitly target public schema for writing Tenant
            with connection.cursor() as cursor:
                cursor.execute("SET search_path TO public")

        trial_ends_at = timezone.now() + datetime.timedelta(days=14)

        try:
            with transaction.atomic():
                tenant = Tenant.objects.create(
                    company_name=company_name,
                    trade_name=trade_name,
                    cnpj=cnpj,
                    subdomain=subdomain,
                    schema_name=schema_name,
                    plan="trial",
                    trial_ends_at=trial_ends_at,
                    ai_autonomy_level="assistive",
                )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to create Tenant record: {e}"))
            return

        # Step 2: Create PostgreSQL schema & run migrations inside it
        if not is_sqlite:
            self.stdout.write(self.style.NOTICE(f"Creating schema '{schema_name}'..."))
            with connection.cursor() as cursor:
                cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")
                cursor.execute(f"SET search_path TO {schema_name}, public")

        self.stdout.write(self.style.NOTICE("Running migrations on tenant schema..."))
        try:
            call_command("migrate", interactive=False)
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Failed to migrate schema '{schema_name}': {e}")
            )
            # Rollback tenant creation on postgres
            if not is_sqlite:
                with connection.cursor() as cursor:
                    cursor.execute("SET search_path TO public")
                tenant.delete()
                with connection.cursor() as cursor:
                    cursor.execute(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE")
            return

        # Step 3: Create admin user in the schema
        self.stdout.write(
            self.style.NOTICE(f"Creating admin user '{admin_username}'...")
        )
        try:
            user_model = get_user_model()
            user_model.objects.create_superuser(
                username=admin_username,
                email=admin_email,
                password=admin_password,
            )
            self.stdout.write(
                self.style.SUCCESS("Successfully created admin user for tenant!")
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to create admin user: {e}"))

        # Reset search_path
        if not is_sqlite:
            with connection.cursor() as cursor:
                cursor.execute("SET search_path TO public")

        self.stdout.write(
            self.style.SUCCESS(f"Tenant '{trade_name}' provisioned successfully!")
        )
