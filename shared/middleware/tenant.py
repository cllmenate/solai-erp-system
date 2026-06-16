import base64
import json

from django.db import connection
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils import timezone

from apps.core.models import Tenant


def get_subdomain_from_host(host):
    """
    Extracts the subdomain from host.
    """
    parts = host.split(".")
    if len(parts) > 2:
        if parts[-1] == "localhost":
            return parts[0]
        return parts[0]
    elif len(parts) == 2 and parts[1] == "localhost":
        return parts[0]
    return None


def get_tenant_id_from_jwt(auth_header):
    """
    Extracts tenant_id from a raw JWT payload without signature verification.
    """
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ")[1]
    try:
        parts = token.split(".")
        if len(parts) == 3:
            payload_b64 = parts[1]
            payload_b64 += "=" * (4 - len(payload_b64) % 4)
            payload_json = base64.b64decode(payload_b64).decode("utf-8")
            payload = json.loads(payload_json)
            return payload.get("tenant_id")
    except Exception:
        pass
    return None


def set_tenant_schema(schema_name):
    """
    Sets search_path of PostgreSQL connection to schema_name, public.
    If database engine is SQLite (for tests), it is a no-op.
    """
    db_engine = connection.settings_dict.get("ENGINE", "")
    if "sqlite" in db_engine:
        return
    with connection.cursor() as cursor:
        cursor.execute(f"SET search_path TO {schema_name}, public")


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        # 1. Resolve tenant from JWT or Subdomain first
        tenant_id = None
        auth_header = request.headers.get("Authorization")
        if auth_header:
            tenant_id = get_tenant_id_from_jwt(auth_header)

        if not tenant_id:
            tenant_id = request.headers.get("X-Tenant-ID")

        host = request.get_host().split(":")[0]
        subdomain = get_subdomain_from_host(host)

        tenant = None
        if tenant_id:
            try:
                set_tenant_schema("public")
                tenant = Tenant.objects.get(id=tenant_id, is_active=True)
            except (Tenant.DoesNotExist, ValueError):
                return JsonResponse(
                    {"error": "Invalid or inactive Tenant ID"}, status=403
                )
        elif subdomain:
            try:
                set_tenant_schema("public")
                tenant = Tenant.objects.get(subdomain=subdomain, is_active=True)
            except Tenant.DoesNotExist:
                return JsonResponse(
                    {"error": f'Tenant with subdomain "{subdomain}" not found'},
                    status=404,
                )

        if tenant:
            request.tenant = tenant
            set_tenant_schema(tenant.schema_name)
            
            # Block Tenant access to Django Admin
            if path == "/admin" or path.startswith("/admin/"):
                return JsonResponse(
                    {"error": "Tenants do not have access to Django Admin"},
                    status=403,
                )
            
            # Check trial status and Stripe subscription
            if (
                tenant.trial_ends_at < timezone.now()
                and not tenant.stripe_subscription_id
            ):
                is_api = (
                    path.startswith("/api/")
                    or request.headers.get("accept", "").startswith("application/json")
                )
                if is_api:
                    return JsonResponse(
                        {
                            "error": (
                                "Trial period expired. "
                                "Active Stripe subscription required."
                            )
                        },
                        status=403,
                    )
                return redirect("/billing/?subdomain=" + tenant.subdomain)
        else:
            # If no tenant, check if the path is a public route on the public schema
            public_prefixes = [
                "/admin/",
                "/static/",
                "/media/",
                "/stripe/webhook/",
                "/stripe/success/",
                "/stripe/cancel/",
                "/billing/",
                "/api/stripe/webhook/",
                "/auth/",
            ]
            is_public = path == "/" or path == "/favicon.ico" or path == "/admin"
            for prefix in public_prefixes:
                if path.startswith(prefix):
                    is_public = True
                    break

            if is_public:
                set_tenant_schema("public")
                request.tenant = None
            else:
                return JsonResponse({"error": "Tenant context required"}, status=403)

        response = self.get_response(request)
        if hasattr(request, "user") and request.user.is_authenticated:
            response["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
            response["Pragma"] = "no-cache"
            response["Expires"] = "0"
        return response
