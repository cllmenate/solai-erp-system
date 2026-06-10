from django.contrib import admin
from django.test import RequestFactory, Client
from django.urls import reverse
import pytest

from apps.core.models import Tenant, User, Role
from apps.commercial.models import Partner, Contact, Address
from apps.assets.models import Brand, Category, TechSheetTemplate, Model, Item, Batch
from shared.middleware.tenant import TenantMiddleware


from django.utils import timezone
from datetime import timedelta

@pytest.mark.django_db
class TestAdminRegistration:
    def test_models_registered_in_admin(self):
        """
        Verify that all required 12 models are registered in Django Admin.
        """
        registered_models = admin.site._registry.keys()
        
        models_to_check = [
            Tenant,
            User,
            Role,
            Partner,
            Contact,
            Address,
            Brand,
            Category,
            TechSheetTemplate,
            Model,
            Item,
            Batch,
        ]
        
        for model in models_to_check:
            assert model in registered_models, f"{model.__name__} is not registered in Django Admin"

    def test_tenant_middleware_blocks_admin_access_under_tenant_context(self):
        """
        Verify that TenantMiddleware returns 403 when accessing /admin or /admin/ with a tenant resolved.
        """
        # Create a tenant
        trial_ends = timezone.now() + timedelta(days=14)
        tenant = Tenant.objects.create(
            company_name="Blocked Tenant Corp",
            trade_name="Blocked Tenant",
            cnpj="00.000.000/0001-00",
            subdomain="blocked-tenant",
            schema_name="tenant_blocked_tenant",
            trial_ends_at=trial_ends,
        )
        
        factory = RequestFactory()
        middleware = TenantMiddleware(lambda req: None)
        
        # Request /admin/ with tenant subdomain HTTP_HOST
        request = factory.get("/admin/", HTTP_HOST="blocked-tenant.localhost")
        response = middleware(request)
        
        assert response is not None
        assert response.status_code == 403
        assert b"Tenants do not have access to Django Admin" in response.content

        # Request /admin (without trailing slash)
        request = factory.get("/admin", HTTP_HOST="blocked-tenant.localhost")
        response = middleware(request)
        
        assert response is not None
        assert response.status_code == 403
        assert b"Tenants do not have access to Django Admin" in response.content

    def test_tenant_middleware_allows_admin_access_under_public_context(self):
        """
        Verify that TenantMiddleware allows access to /admin and /admin/ under public (no tenant) context.
        """
        factory = RequestFactory()
        middleware = TenantMiddleware(lambda req: "allowed")
        
        # Request /admin/ without a tenant subdomain
        request = factory.get("/admin/login/", HTTP_HOST="localhost")
        response = middleware(request)
        assert response == "allowed"

        # Request /admin without a tenant subdomain
        request = factory.get("/admin", HTTP_HOST="localhost")
        response = middleware(request)
        assert response == "allowed"
