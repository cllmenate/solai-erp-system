
from django.core.management.base import BaseCommand


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

        self.stdout.write(
            self.style.WARNING(
                f"Starting provisioning for tenant: {trade_name} ({schema_name})"
            )
        )

        from apps.core.services import provision_tenant

        try:
            provision_tenant(
                company_name=company_name,
                trade_name=trade_name,
                cnpj=cnpj,
                subdomain=subdomain,
                schema_name=schema_name,
                admin_username=admin_username,
                admin_email=admin_email,
                admin_password=admin_password,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully provisioned tenant {trade_name} and admin user {admin_username}!"
                )
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Failed to provision tenant: {e}")
            )

