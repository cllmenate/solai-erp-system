import datetime

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection, transaction
from django.utils import timezone

from apps.core.models import Tenant


def provision_tenant(
    company_name: str,
    trade_name: str,
    cnpj: str,
    subdomain: str,
    schema_name: str,
    admin_username: str,
    admin_email: str,
    admin_password: str | None = None,
) -> Tenant:
    """
    Creates a Tenant record in the public schema, provisions the schema,
    runs database migrations inside that schema, and creates the admin user.
    If admin_password is not provided, the admin user is created as inactive (is_active=False)
    so they can set their password later via a token-based link.
    """
    db_engine = connection.settings_dict.get("ENGINE", "")
    is_sqlite = "sqlite" in db_engine

    # Step 1: Create the Tenant record in the public schema
    if not is_sqlite:
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO public")

    trial_ends_at = timezone.now() + datetime.timedelta(days=14)

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

    # Step 2: Create PostgreSQL schema & run migrations inside it
    if not is_sqlite:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")
            cursor.execute(f"SET search_path TO {schema_name}, public")

    try:
        call_command("migrate", interactive=False)
    except Exception as e:
        # Rollback tenant creation on postgres
        if not is_sqlite:
            with connection.cursor() as cursor:
                cursor.execute("SET search_path TO public")
            tenant.delete()
            with connection.cursor() as cursor:
                cursor.execute(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE")
        raise e

    # Step 3: Create admin user, default sectors and default role in the schema
    try:
        from django.contrib.auth.models import Permission

        from apps.core.models import Role, Sector
        
        user_model = get_user_model()
        is_active = admin_password is not None

        # Pre-create default sectors
        default_sectors = ["Administração", "Vendas", "Estoque", "Produção", "Financeiro"]
        created_sectors = {}
        for sec_name in default_sectors:
            sec_obj, _ = Sector.objects.get_or_create(
                name=sec_name,
                tenant=tenant,
                defaults={
                    "description": f"Setor de {sec_name}",
                    "is_active": True,
                }
            )
            created_sectors[sec_name] = sec_obj
        
        # Create default Administrador role for the tenant linked to "Administração" sector
        admin_role, _ = Role.objects.get_or_create(  # type: ignore[misc]
            name=f"{tenant.subdomain}:Administrador",
            tenant=tenant,
            defaults={
                "level": 100,  # type: ignore[misc]
                "description": "Administrador Geral do Tenant",  # type: ignore[misc]
                "is_active": True,  # type: ignore[misc]
                "sector": created_sectors["Administração"],  # type: ignore[misc]
            }
        )
        if not admin_role.sector:
            admin_role.sector = created_sectors["Administração"]
            admin_role.save()
        
        # Assign roles management permissions
        perms = Permission.objects.filter(
            content_type__app_label="core",
            codename__in=["add_role", "change_role", "delete_role", "view_role"]
        )
        admin_role.permissions.set(perms)
        
        # We need to construct the superuser
        admin_user = user_model.objects.create_superuser(
            username=admin_username,
            email=admin_email,
            password=admin_password,
            tenant=tenant,
            is_active=is_active,
        )
        admin_user.role = admin_role
        admin_user.save()
    except Exception as e:
        # Rollback schema and tenant on user creation failure
        if not is_sqlite:
            with connection.cursor() as cursor:
                cursor.execute("SET search_path TO public")
            tenant.delete()
            with connection.cursor() as cursor:
                cursor.execute(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE")
        raise e

    # Reset search_path
    if not is_sqlite:
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO public")

    return tenant
