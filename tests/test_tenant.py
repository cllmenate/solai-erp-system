import json
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.http import JsonResponse
from django.test import RequestFactory
from django.utils import timezone

from apps.core.models import Tenant
from shared.middleware.tenant import (
    TenantMiddleware,
    get_subdomain_from_host,
    get_tenant_id_from_jwt,
)


@pytest.mark.django_db
class TestTenantModels:
    def test_tenant_creation_defaults(self):
        """
        Verify that Tenant is created with correct defaults, auto-sets UUID id,
        and auto-fills `name` from trade_name or company_name.
        """
        trial_ends = timezone.now() + timedelta(days=14)
        tenant = Tenant.objects.create(
            company_name="SolAI Corporation LTDA",
            trade_name="SolAI Corp",
            cnpj="12.345.678/0001-90",
            subdomain="solai-corp",
            schema_name="tenant_solai_corp",
            trial_ends_at=trial_ends,
        )

        assert tenant.id is not None
        assert tenant.name == "SolAI Corp"
        assert tenant.is_active is True
        assert tenant.ai_autonomy_level == "assistive"

        # Verify simple history is tracking
        assert tenant.history.count() == 1

    def test_tenant_history_records(self):
        """
        Verify that updates to Tenant are audited by simple_history.
        """
        trial_ends = timezone.now() + timedelta(days=14)
        tenant = Tenant.objects.create(
            company_name="SolAI Corporation LTDA",
            trade_name="SolAI Corp",
            cnpj="12.345.678/0001-90",
            subdomain="solai-corp",
            schema_name="tenant_solai_corp",
            trial_ends_at=trial_ends,
        )

        tenant.trade_name = "New Trade Name"
        tenant.save()

        assert tenant.history.count() == 2
        history_records = tenant.history.all()
        assert history_records[0].trade_name == "New Trade Name"
        assert history_records[1].trade_name == "SolAI Corp"


class TestHelpers:
    def test_get_subdomain_from_host(self):
        assert get_subdomain_from_host("tenant.solai.com.br") == "tenant"
        assert get_subdomain_from_host("tenant.localhost") == "tenant"
        assert get_subdomain_from_host("localhost") is None

    def test_get_tenant_id_from_jwt(self):
        # A simple base64 encoded payload: {"tenant_id": "some-uuid"}
        # JWT header = eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9
        # JWT payload = eyJ0ZW5hbnRfaWQiOiJzb21lLXV1aWQifQ==
        # JWT signature = signature
        part1 = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        part2 = "eyJ0ZW5hbnRfaWQiOiJzb21lLXV1aWQifQ=="
        token = f"{part1}.{part2}.signature"
        auth_header = f"Bearer {token}"
        assert get_tenant_id_from_jwt(auth_header) == "some-uuid"
        assert get_tenant_id_from_jwt("InvalidHeader") is None


@pytest.mark.django_db
class TestTenantMiddleware:
    def setup_method(self):
        self.factory = RequestFactory()
        self.middleware = TenantMiddleware(
            lambda req: JsonResponse({"status": "success"})
        )

        # Create an active Tenant
        self.trial_ends = timezone.now() + timedelta(days=14)
        self.tenant = Tenant.objects.create(
            company_name="Test Company",
            trade_name="Test Brand",
            cnpj="99.999.999/0001-99",
            subdomain="testbrand",
            schema_name="tenant_testbrand",
            trial_ends_at=self.trial_ends,
        )

    def test_public_paths_allowed_without_tenant(self):
        # Root path /
        request = self.factory.get("/")
        response = self.middleware(request)
        assert response.status_code == 200
        assert request.tenant is None

        # Admin login path
        request = self.factory.get("/admin/login/")
        response = self.middleware(request)
        assert response.status_code == 200
        assert request.tenant is None

    def test_tenant_resolved_via_header(self):
        request = self.factory.get("/api/v1/items/")
        request.META["HTTP_X_TENANT_ID"] = str(self.tenant.id)

        response = self.middleware(request)
        assert response.status_code == 200
        assert request.tenant == self.tenant

    def test_tenant_resolved_via_subdomain(self):
        request = self.factory.get("/dashboard/", HTTP_HOST="testbrand.localhost")

        response = self.middleware(request)
        assert response.status_code == 200
        assert request.tenant == self.tenant

    def test_access_denied_without_tenant_on_protected_path(self):
        request = self.factory.get("/dashboard/")
        response = self.middleware(request)
        assert response.status_code == 403
        assert b"Tenant context required" in response.content


@pytest.mark.django_db
class TestTenantManagementCommands:
    def test_create_tenant_command(self):
        """
        Verify that `create_tenant` runs successfully, provisions tenant record,
        and does not fail on SQLite (which skips schema routing).
        """
        call_command(
            "create_tenant",
            "--company-name=Command Company Inc",
            "--trade-name=Command Brand",
            "--cnpj=11.111.111/0001-11",
            "--subdomain=commandbrand",
            "--schema-name=tenant_commandbrand",
            "--admin-username=cmdadmin",
            "--admin-password=password123",
            "--admin-email=admin@command.com",
        )

        # Check if Tenant was created
        tenant = Tenant.objects.get(subdomain="commandbrand")
        assert tenant.company_name == "Command Company Inc"

        # Check if superuser was created
        user_model = get_user_model()
        assert user_model.objects.filter(
            username="cmdadmin", is_superuser=True
        ).exists()

    def test_migrate_tenants_command(self):
        """
        Verify that `migrate_tenants` runs successfully without exceptions.
        """
        # Create a tenant first
        Tenant.objects.create(
            company_name="Migrate Corp",
            trade_name="Migrate Brand",
            cnpj="22.222.222/0001-22",
            subdomain="migratebrand",
            schema_name="tenant_migratebrand",
            trial_ends_at=timezone.now() + timedelta(days=14),
        )

        # Execute migrate_tenants
        call_command("migrate_tenants")


@pytest.mark.django_db
class TestBillingAndTrialFlow:
    def setup_method(self):
        self.factory = RequestFactory()
        self.middleware = TenantMiddleware(
            lambda req: JsonResponse({"status": "success"})
        )
        # Create an expired Tenant with no Stripe subscription
        self.expired_tenant = Tenant.objects.create(
            company_name="Expired Tenant Ltd",
            trade_name="Expired Brand",
            cnpj="88.888.888/0008-88",
            subdomain="expiredbrand",
            schema_name="tenant_expiredbrand",
            trial_ends_at=timezone.now() - timedelta(days=1),
        )

    def test_expired_trial_redirects_templates(self):
        # Template view HTML request to a protected path
        request = self.factory.get("/dashboard/", HTTP_HOST="expiredbrand.localhost")
        request.headers = {"accept": "text/html"}
        
        response = self.middleware(request)
        assert response.status_code == 302
        assert "/billing/" in response.url

    def test_expired_trial_blocks_api_json(self):
        # API/JSON request
        request = self.factory.get("/api/v1/items/", HTTP_HOST="expiredbrand.localhost")
        request.headers = {"accept": "application/json"}
        
        response = self.middleware(request)
        assert response.status_code == 403
        assert b"Trial period expired" in response.content

    def test_stripe_webhook_provisions_subscription(self):
        from django.test import Client
        c = Client()
        
        # Webhook payload for checkout completed
        payload = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "client_reference_id": "expiredbrand",
                    "subscription": "sub_test_checkout123"
                }
            }
        }
        
        response = c.post(
            "/stripe/webhook/",
            data=json.dumps(payload),
            content_type="application/json"
        )
        assert response.status_code == 200
        
        # Verify tenant subscription state was updated
        self.expired_tenant.refresh_from_db()
        assert self.expired_tenant.stripe_subscription_id == "sub_test_checkout123"
        assert self.expired_tenant.plan == "pro"

