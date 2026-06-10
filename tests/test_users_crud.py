from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Role, Sector, Tenant


@pytest.mark.django_db
class TestUsersCRUD:
    @pytest.fixture(autouse=True)
    def setup_method(self):
        # Setup Tenants
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

        # Setup Sectors
        self.sector_admin_a = Sector.objects.create(name="Administração", tenant=self.tenant_a)
        self.sector_sales_a = Sector.objects.create(name="Vendas", tenant=self.tenant_a)
        self.sector_admin_b = Sector.objects.create(name="Administração", tenant=self.tenant_b)

        # Setup Permissions
        self.view_perm = Permission.objects.get(content_type__app_label="core", codename="view_user")
        self.add_perm = Permission.objects.get(content_type__app_label="core", codename="add_user")
        self.change_perm = Permission.objects.get(content_type__app_label="core", codename="change_user")

        # Setup Roles for Tenant A
        self.role_admin_a = Role.objects.create(
            name="tenanta:Admin",
            tenant=self.tenant_a,
            sector=self.sector_admin_a,
            level=100,
            description="Admin",
            is_active=True
        )
        self.role_admin_a.permissions.add(self.view_perm, self.add_perm, self.change_perm)

        self.role_manager_a = Role.objects.create(
            name="tenanta:Manager",
            tenant=self.tenant_a,
            sector=self.sector_sales_a,
            level=50,
            description="Manager",
            is_active=True
        )
        self.role_manager_a.permissions.add(self.view_perm, self.add_perm, self.change_perm)

        self.role_normal_a = Role.objects.create(
            name="tenanta:Normal",
            tenant=self.tenant_a,
            sector=self.sector_sales_a,
            level=10,
            description="Normal",
            is_active=True
        )

        # Setup Roles for Tenant B
        self.role_admin_b = Role.objects.create(
            name="tenantb:Admin",
            tenant=self.tenant_b,
            sector=self.sector_admin_b,
            level=100,
            description="Admin B",
            is_active=True
        )
        self.role_admin_b.permissions.add(self.view_perm, self.add_perm, self.change_perm)

        self.role_normal_b = Role.objects.create(
            name="tenantb:Normal",
            tenant=self.tenant_b,
            level=10,
            description="Normal B",
            is_active=True
        )

        # Setup Users
        user_model = get_user_model()
        self.admin_a = user_model.objects.create_user(
            username="admina",
            email="admina@example.com",
            password="password123",
            tenant=self.tenant_a,
            role=self.role_admin_a,
            is_active=True
        )
        self.manager_a = user_model.objects.create_user(
            username="managera",
            email="managera@example.com",
            password="password123",
            tenant=self.tenant_a,
            role=self.role_manager_a,
            is_active=True
        )
        self.user_a = user_model.objects.create_user(
            username="usera",
            email="usera@example.com",
            password="password123",
            tenant=self.tenant_a,
            role=self.role_normal_a,
            is_active=True
        )
        self.admin_b = user_model.objects.create_user(
            username="adminb",
            email="adminb@example.com",
            password="password123",
            tenant=self.tenant_b,
            role=self.role_admin_b,
            is_active=True
        )

    def test_unauthenticated_redirect(self, client):
        response = client.get(reverse("settings_users"), HTTP_HOST="tenanta.localhost")
        assert response.status_code == 302
        assert reverse("login") in response.url

    def test_unauthorized_forbidden(self, client):
        # user_a has normal role (no view_user permission)
        client.force_login(self.user_a)
        response = client.get(reverse("settings_users"), HTTP_HOST="tenanta.localhost")
        assert response.status_code == 403

    def test_authorized_list_scoped_by_tenant(self, client):
        client.force_login(self.admin_a)
        response = client.get(reverse("settings_users"), HTTP_HOST="tenanta.localhost")
        assert response.status_code == 200
        users = response.context["users"]
        assert self.admin_a in users
        assert self.manager_a in users
        assert self.user_a in users
        # admin_b belongs to tenant B and must not be listed
        assert self.admin_b not in users

    def test_create_user_success(self, client):
        client.force_login(self.admin_a)
        response = client.post(
            reverse("settings_role_user_create"),
            {
                "username": "newuser",
                "email": "newuser@example.com",
                "full_name": "New User",
                "role": self.role_normal_a.id,
                "is_active": True
            },
            HTTP_HOST="tenanta.localhost"
        )
        assert response.status_code == 302
        user_model = get_user_model()
        new_user = user_model.objects.get(username="newuser", tenant=self.tenant_a)
        assert new_user.email == "newuser@example.com"
        assert new_user.role == self.role_normal_a
        assert new_user.has_usable_password() is True

    def test_create_user_hierarchy_restriction(self, client):
        # manager_a has level 50 role. They cannot create a user with role of level 50 or 100.
        client.force_login(self.manager_a)
        response = client.post(
            reverse("settings_role_user_create"),
            {
                "username": "illegaluser",
                "email": "illegal@example.com",
                "full_name": "Illegal User",
                "role": self.role_manager_a.id,  # Level 50, equal to manager_a's level
                "is_active": True
            },
            HTTP_HOST="tenanta.localhost"
        )
        assert response.status_code == 200
        # Form should have error because role choice field queryset excludes role_manager_a
        assert "role" in response.context["form"].errors

    def test_create_user_duplicate_username_fails(self, client):
        client.force_login(self.admin_a)
        # Attempt to create a user with username "usera" which already exists in Tenant A
        response = client.post(
            reverse("settings_role_user_create"),
            {
                "username": "usera",
                "email": "diffemail@example.com",
                "full_name": "Duplicate User",
                "role": self.role_normal_a.id,
                "is_active": True
            },
            HTTP_HOST="tenanta.localhost"
        )
        assert response.status_code == 200
        assert "username" in response.context["form"].errors

    def test_create_user_different_tenant_same_username_success(self, client):
        # Tenant B admin creates a user with username "usera" (which already exists in Tenant A)
        client.force_login(self.admin_b)
        response = client.post(
            reverse("settings_role_user_create"),
            {
                "username": "usera",
                "email": "userb@example.com",
                "full_name": "User B",
                "role": self.role_normal_b.id,
                "is_active": True
            },
            HTTP_HOST="tenantb.localhost"
        )
        assert response.status_code == 302
        user_model = get_user_model()
        assert user_model.objects.filter(username="usera", tenant=self.tenant_b).exists()

    def test_edit_user_success(self, client):
        client.force_login(self.admin_a)
        response = client.post(
            reverse("settings_user_edit", args=[self.user_a.id]),
            {
                "username": "usera_updated",
                "email": "usera_updated@example.com",
                "full_name": "User A Updated",
                "role": self.role_manager_a.id,
                "is_active": True
            },
            HTTP_HOST="tenanta.localhost"
        )
        assert response.status_code == 302
        self.user_a.refresh_from_db()
        assert self.user_a.username == "usera_updated"
        assert self.user_a.email == "usera_updated@example.com"
        assert self.user_a.role == self.role_manager_a

    def test_edit_user_hierarchy_restriction(self, client):
        # manager_a (level 50) tries to edit admin_a (level 100). Should raise PermissionDenied (403).
        client.force_login(self.manager_a)
        response = client.get(
            reverse("settings_user_edit", args=[self.admin_a.id]),
            HTTP_HOST="tenanta.localhost"
        )
        assert response.status_code == 403

    def test_toggle_active_status(self, client):
        client.force_login(self.admin_a)
        assert self.user_a.is_active is True
        response = client.post(
            reverse("settings_user_toggle_active", args=[self.user_a.id]),
            HTTP_HOST="tenanta.localhost"
        )
        assert response.status_code == 302
        self.user_a.refresh_from_db()
        assert self.user_a.is_active is False

    def test_toggle_active_hierarchy_restriction(self, client):
        # manager_a (level 50) tries to toggle active on admin_a (level 100). Should raise PermissionDenied (403).
        client.force_login(self.manager_a)
        response = client.post(
            reverse("settings_user_toggle_active", args=[self.admin_a.id]),
            HTTP_HOST="tenanta.localhost"
        )
        assert response.status_code == 403

    def test_invite_create_permission_change(self, client):
        # manager_a (who is not superuser, but has role_manager_a with core.add_user perm) can access invite page
        client.force_login(self.manager_a)
        response = client.get(reverse("invite_create"), HTTP_HOST="tenanta.localhost")
        assert response.status_code == 200
