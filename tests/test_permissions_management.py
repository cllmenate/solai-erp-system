from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Role, Tenant


@pytest.mark.django_db
class TestPermissionsManagement:
    @pytest.fixture(autouse=True)
    def setup_method(self):
        self.tenant_a = Tenant.objects.create(
            company_name="Tenant A",
            trade_name="Tenant A Trade",
            cnpj="11.111.111/0001-11",
            subdomain="tenanta",
            schema_name="tenant_tenanta",
            trial_ends_at=timezone.now() + timedelta(days=14),
        )
        self.tenant_b = Tenant.objects.create(
            company_name="Tenant B",
            trade_name="Tenant B Trade",
            cnpj="22.222.222/0001-22",
            subdomain="tenantb",
            schema_name="tenant_tenantb",
            trial_ends_at=timezone.now() + timedelta(days=14),
        )

        user_model = get_user_model()
        self.admin_a = user_model.objects.create_user(
            username="admina",
            email="admina@example.com",
            password="password123",
            tenant=self.tenant_a,
            is_active=True
        )
        self.user_a = user_model.objects.create_user(
            username="usera",
            email="usera@example.com",
            password="password123",
            tenant=self.tenant_a,
            is_active=True
        )
        self.admin_b = user_model.objects.create_user(
            username="adminb",
            email="adminb@example.com",
            password="password123",
            tenant=self.tenant_b,
            is_active=True
        )

        # Setup permissions
        self.view_perm = Permission.objects.get(content_type__app_label="core", codename="view_role")
        self.add_perm = Permission.objects.get(content_type__app_label="core", codename="add_role")
        self.change_perm = Permission.objects.get(content_type__app_label="core", codename="change_role")
        self.delete_perm = Permission.objects.get(content_type__app_label="core", codename="delete_role")

        # Create Admin Role for Tenant A
        self.role_admin_a = Role.objects.create(
            name="tenanta:Admin",
            tenant=self.tenant_a,
            level=100,
            description="Administrador A",
            is_active=True
        )
        self.role_admin_a.permissions.add(self.view_perm, self.add_perm, self.change_perm, self.delete_perm)
        self.admin_a.role = self.role_admin_a
        self.admin_a.save()

        # Create Normal Role for Tenant A
        self.role_normal_a = Role.objects.create(
            name="tenanta:Normal",
            tenant=self.tenant_a,
            level=10,
            description="Normal A",
            is_active=True
        )
        self.user_a.role = self.role_normal_a
        self.user_a.save()

        # Create Admin Role for Tenant B
        self.role_admin_b = Role.objects.create(
            name="tenantb:Admin",
            tenant=self.tenant_b,
            level=100,
            description="Administrador B",
            is_active=True
        )
        self.role_admin_b.permissions.add(self.view_perm, self.add_perm, self.change_perm, self.delete_perm)
        self.admin_b.role = self.role_admin_b
        self.admin_b.save()

    def test_unauthenticated_redirect(self, client):
        response = client.get(
            reverse("settings_role_permissions", args=[self.role_normal_a.id]),
            HTTP_HOST="tenanta.localhost"
        )
        assert response.status_code == 302
        assert reverse("login") in response.url

    def test_unauthorized_forbidden(self, client):
        client.force_login(self.user_a)
        response = client.get(
            reverse("settings_role_permissions", args=[self.role_normal_a.id]),
            HTTP_HOST="tenanta.localhost"
        )
        assert response.status_code == 403

    def test_tenant_isolation_forbidden_or_not_found(self, client):
        client.force_login(self.admin_a)
        # Admin A tries to access Tenant B's role permissions
        response = client.get(
            reverse("settings_role_permissions", args=[self.role_admin_b.id]),
            HTTP_HOST="tenanta.localhost"
        )
        assert response.status_code == 404

    def test_get_permissions_grid_success(self, client):
        client.force_login(self.admin_a)
        response = client.get(
            reverse("settings_role_permissions", args=[self.role_normal_a.id]),
            HTTP_HOST="tenanta.localhost"
        )
        assert response.status_code == 200
        assert "role" in response.context
        assert "grid_data" in response.context
        assert response.context["role"] == self.role_normal_a

    def test_post_permissions_update_success(self, client):
        client.force_login(self.admin_a)
        # Assign view_role and change_role to self.role_normal_a
        response = client.post(
            reverse("settings_role_permissions", args=[self.role_normal_a.id]),
            {
                "permissions": [self.view_perm.id, self.change_perm.id]
            },
            HTTP_HOST="tenanta.localhost"
        )
        assert response.status_code == 302
        assert response.url == reverse("settings_roles")

        # Verify role has updated permissions
        self.role_normal_a.refresh_from_db()
        assigned_perms = list(self.role_normal_a.permissions.all())
        assert self.view_perm in assigned_perms
        assert self.change_perm in assigned_perms
        assert self.add_perm not in assigned_perms
        assert self.delete_perm not in assigned_perms

        # Verify user inherits permissions immediately
        assert self.user_a.has_perm("core.view_role") is True
        assert self.user_a.has_perm("core.change_role") is True
        assert self.user_a.has_perm("core.add_role") is False
