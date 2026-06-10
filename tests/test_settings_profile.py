from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Tenant


@pytest.mark.django_db
class TestSettingsProfileView:
    @pytest.fixture(autouse=True)
    def setup_method(self):
        self.tenant = Tenant.objects.create(
            company_name="SolAI Testing LTDA Profile",
            trade_name="SolAI Profile",
            cnpj="99.999.999/0001-88",
            subdomain="proftest",
            schema_name="tenant_proftest",
            trial_ends_at=timezone.now() + timedelta(days=14),
        )
        
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="testuser",
            email="testuser@example.com",
            password="securepassword123",
            tenant=self.tenant,
            is_active=True
        )

        self.other_user = user_model.objects.create_user(
            username="otheruser",
            email="otheruser@example.com",
            password="securepassword123",
            tenant=self.tenant,
            is_active=True
        )

    def test_unauthenticated_redirect(self, client):
        response = client.get(reverse("settings_profile"), HTTP_HOST="proftest.localhost")
        assert response.status_code == 302
        assert reverse("login") in response.url

    def test_authenticated_access(self, client):
        client.force_login(self.user)
        response = client.get(reverse("settings_profile"), HTTP_HOST="proftest.localhost")
        assert response.status_code == 200
        assert "preferences" in response.context

    def test_update_profile_success(self, client):
        client.force_login(self.user)
        response = client.post(
            reverse("settings_profile"),
            {
                "action": "profile",
                "full_name": "Novo Nome Completo",
                "email": "novoemail@example.com"
            },
            HTTP_HOST="proftest.localhost"
        )
        assert response.status_code == 302
        self.user.refresh_from_db()
        assert self.user.full_name == "Novo Nome Completo"
        assert self.user.email == "novoemail@example.com"

    def test_update_profile_duplicate_email(self, client):
        client.force_login(self.user)
        _response = client.post(
            reverse("settings_profile"),
            {
                "action": "profile",
                "full_name": "Novo Nome Completo",
                "email": "otheruser@example.com"  # Already in use by self.other_user
            },
            HTTP_HOST="proftest.localhost"
        )
        # Should reload page or redirect, but user email must not change
        self.user.refresh_from_db()
        assert self.user.full_name != "Novo Nome Completo"
        assert self.user.email == "testuser@example.com"

    def test_change_password_success(self, client):
        client.force_login(self.user)
        response = client.post(
            reverse("settings_profile"),
            {
                "action": "password",
                "current_password": "securepassword123",
                "new_password": "brandnewpassword123",
                "confirm_password": "brandnewpassword123"
            },
            HTTP_HOST="proftest.localhost"
        )
        assert response.status_code == 302
        self.user.refresh_from_db()
        assert self.user.check_password("brandnewpassword123") is True

    def test_change_password_incorrect_current(self, client):
        client.force_login(self.user)
        _response = client.post(
            reverse("settings_profile"),
            {
                "action": "password",
                "current_password": "wrongpassword123",
                "new_password": "brandnewpassword123",
                "confirm_password": "brandnewpassword123"
            },
            HTTP_HOST="proftest.localhost"
        )
        self.user.refresh_from_db()
        assert self.user.check_password("brandnewpassword123") is False

    def test_update_appearance_preferences(self, client):
        client.force_login(self.user)
        
        # Initial check
        prefs = self.user.preferences
        assert prefs.dark_mode is False
        assert prefs.sidebar_compact is False
        assert prefs.visual_theme == "default"

        # Update
        response = client.post(
            reverse("settings_profile"),
            {
                "action": "appearance",
                "dark_mode": "on",
                "sidebar_compact": "on",
                "visual_theme": "ocean"
            },
            HTTP_HOST="proftest.localhost"
        )
        assert response.status_code == 302
        
        # Refresh and verify
        prefs.refresh_from_db()
        assert prefs.dark_mode is True
        assert prefs.sidebar_compact is True
        assert prefs.visual_theme == "ocean"
