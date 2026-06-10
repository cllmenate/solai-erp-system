from datetime import timedelta
import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Tenant, Role

@pytest.mark.django_db
class TestRolesCRUD:
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

        # Set up permissions
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
        response = client.get(reverse("settings_roles"), HTTP_HOST="tenanta.localhost")
        assert response.status_code == 302
        assert reverse("login") in response.url

    def test_unauthorized_forbidden(self, client):
        client.force_login(self.user_a)
        response = client.get(reverse("settings_roles"), HTTP_HOST="tenanta.localhost")
        assert response.status_code == 403

    def test_authorized_access(self, client):
        client.force_login(self.admin_a)
        response = client.get(reverse("settings_roles"), HTTP_HOST="tenanta.localhost")
        assert response.status_code == 200
        assert self.role_admin_a in response.context["roles"]
        assert self.role_normal_a in response.context["roles"]
        # Tenant B roles must NOT be listed
        assert self.role_admin_b not in response.context["roles"]

    def test_create_role_success(self, client):
        client.force_login(self.admin_a)
        response = client.post(
            reverse("settings_role_create"),
            {
                "name": "Novo Cargo",
                "level": 50,
                "description": "Novo cargo do tenant A",
                "is_active": True
            },
            HTTP_HOST="tenanta.localhost"
        )
        assert response.status_code == 302
        new_role = Role.objects.get(name="tenanta:Novo Cargo", tenant=self.tenant_a)
        assert new_role.level == 50
        assert new_role.friendly_name == "Novo Cargo"

    def test_create_role_duplicate_name_same_tenant_fails(self, client):
        client.force_login(self.admin_a)
        # Attempt to create "Normal" which already exists as "tenanta:Normal"
        response = client.post(
            reverse("settings_role_create"),
            {
                "name": "Normal",
                "level": 20,
                "description": "Duplicado",
                "is_active": True
            },
            HTTP_HOST="tenanta.localhost"
        )
        # Should render form with errors
        assert response.status_code == 200
        assert "form" in response.context
        assert response.context["form"].errors

    def test_create_role_same_name_different_tenant_success(self, client):
        # Tenant B creates "Normal"
        client.force_login(self.admin_b)
        response = client.post(
            reverse("settings_role_create"),
            {
                "name": "Normal",
                "level": 20,
                "description": "Normal em B",
                "is_active": True
            },
            HTTP_HOST="tenantb.localhost"
        )
        assert response.status_code == 302
        assert Role.objects.filter(name="tenantb:Normal", tenant=self.tenant_b).exists()

    def test_edit_role(self, client):
        client.force_login(self.admin_a)
        response = client.post(
            reverse("settings_role_edit", args=[self.role_normal_a.id]),
            {
                "name": "Normal Alterado",
                "level": 15,
                "description": "Descrição alterada",
                "is_active": True
            },
            HTTP_HOST="tenanta.localhost"
        )
        assert response.status_code == 302
        self.role_normal_a.refresh_from_db()
        assert self.role_normal_a.name == "tenanta:Normal Alterado"
        assert self.role_normal_a.friendly_name == "Normal Alterado"
        assert self.role_normal_a.level == 15

    def test_toggle_active_status(self, client):
        client.force_login(self.admin_a)
        assert self.role_normal_a.is_active is True
        
        response = client.post(
            reverse("settings_role_toggle_active", args=[self.role_normal_a.id]),
            HTTP_HOST="tenanta.localhost"
        )
        assert response.status_code == 302
        self.role_normal_a.refresh_from_db()
        assert self.role_normal_a.is_active is False

    def test_deactivated_role_short_circuits_permissions(self):
        # Normal user A has a role
        assert self.user_a.role.is_active is True
        # Assign some permissions directly to the normal role
        custom_perm = Permission.objects.get(content_type__app_label="assets", codename="view_item")
        self.role_normal_a.permissions.add(custom_perm)
        
        # Verify user has permission when active
        assert self.user_a.has_perm("assets.view_item") is True
        
        # Deactivate role
        self.role_normal_a.is_active = False
        self.role_normal_a.save()
        
        # Verify user no longer has permission when role is inactive
        assert self.user_a.has_perm("assets.view_item") is False

    def test_warning_banners_context(self, client):
        # Log in as normal user with active role
        client.force_login(self.user_a)
        response = client.get("/", HTTP_HOST="tenanta.localhost")
        assert "current_user_role_deactivated" not in response.context
        
        # Deactivate role of normal user
        self.role_normal_a.is_active = False
        self.role_normal_a.save()
        
        # Check that user sees the deactivated role warning
        response = client.get("/", HTTP_HOST="tenanta.localhost")
        assert response.context.get("current_user_role_deactivated") is True

        # Log in as admin, should see warning that active users have inactive roles
        client.force_login(self.admin_a)
        response = client.get(reverse("settings_roles"), HTTP_HOST="tenanta.localhost")
        assert response.context.get("admin_has_inactive_roles_warning") is True
