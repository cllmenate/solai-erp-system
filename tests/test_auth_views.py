from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.signing import dumps
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Tenant
from apps.core.services import provision_tenant


@pytest.mark.django_db
class TestAuthViews:
    def test_provision_tenant_service(self):
        tenant = provision_tenant(
            company_name="Test Company",
            trade_name="Test Trade",
            cnpj="99.999.999/0001-99",
            subdomain="testsub",
            schema_name="tenant_testsub",
            admin_username="testadmin",
            admin_email="testadmin@company.com",
            admin_password="testpassword123"
        )
        assert tenant is not None
        assert tenant.company_name == "Test Company"
        assert tenant.subdomain == "testsub"
        
        user_model = get_user_model()
        user = user_model.objects.get(username="testadmin")
        assert user.email == "testadmin@company.com"
        assert user.is_active is True
        assert user.check_password("testpassword123") is True

    def test_login_view(self, client):
        tenant = Tenant.objects.create(
            company_name="SolAI Testing LTDA",
            trade_name="SolAI Test",
            cnpj="88.888.888/0001-88",
            subdomain="solaitest",
            schema_name="tenant_solaitest",
            trial_ends_at=timezone.now() + timedelta(days=14),
        )
        user_model = get_user_model()
        user_model.objects.create_user(
            username="testuser",
            email="testuser@example.com",
            password="securepassword123",
            tenant=tenant,
            is_active=True
        )

        # Test accessing login directly with tenant subdomain context
        response = client.get(reverse("login"), HTTP_HOST="solaitest.localhost")
        assert response.status_code == 200

        response = client.post(reverse("login"), {
            "username_or_email": "testuser",
            "password": "securepassword123"
        }, HTTP_HOST="solaitest.localhost")
        assert response.status_code == 302
        assert response.url == "/"

        # Log out the user to test public login redirection
        client.logout()

        # Test public login redirection
        response = client.get(reverse("login"))
        assert response.status_code == 200

        # Post with invalid subdomain
        response = client.post(reverse("login"), {
            "subdomain": "invalidsub",
            "username_or_email": "testuser",
            "password": "securepassword123"
        })
        assert response.status_code == 200

        # Post with valid subdomain (should redirect to subdomain login page)
        response = client.post(reverse("login"), {
            "subdomain": "solaitest",
            "username_or_email": "testuser",
            "password": "securepassword123"
        })
        assert response.status_code == 302
        assert "solaitest" in response.url

    def test_signup_trial_view(self, client):
        response = client.get(reverse("signup_trial"))
        assert response.status_code == 200

        response = client.post(reverse("signup_trial"), {
            "company_name": "New Company Ltd",
            "trade_name": "New Trade",
            "cnpj": "12.345.678/0001-99",
            "subdomain": "newsub",
            "username": "newadmin",
            "email": "newadmin@newcompany.com"
        })
        assert response.status_code == 302
        assert "/auth/signup-success/" in response.url

    def test_set_password_view(self, client):
        tenant = Tenant.objects.create(
            company_name="SolAI Testing LTDA2",
            trade_name="SolAI Test2",
            cnpj="88.888.888/0001-89",
            subdomain="solaitest2",
            schema_name="tenant_solaitest2",
            trial_ends_at=timezone.now() + timedelta(days=14),
        )
        user_model = get_user_model()
        user = user_model.objects.create_user(
            username="inactiveadmin",
            email="inactiveadmin@example.com",
            tenant=tenant,
            is_active=False
        )

        token = dumps(
            {"subdomain": "solaitest2", "username": "inactiveadmin"},
            salt="set-password-salt"
        )
        url = reverse("set_password", kwargs={"token": token})
        
        response = client.get(url)
        assert response.status_code == 200

        response = client.post(url, {
            "password": "newpassword123",
            "password_confirm": "newpassword123"
        })
        assert response.status_code == 302
        
        user.refresh_from_db()
        assert user.is_active is True
        assert user.check_password("newpassword123") is True

    def test_sso_token_login(self, client):
        tenant = Tenant.objects.create(
            company_name="SolAI Testing LTDA3",
            trade_name="SolAI Test3",
            cnpj="88.888.888/0001-90",
            subdomain="solaitest3",
            schema_name="tenant_solaitest3",
            trial_ends_at=timezone.now() + timedelta(days=14),
        )
        user_model = get_user_model()
        user_model.objects.create_user(
            username="sso_user",
            email="sso_user@example.com",
            password="sso_password123",
            tenant=tenant,
            is_active=True
        )

        # 1. Post to public login with subdomain (should redirect to subdomain with token)
        response = client.post(reverse("login"), {
            "subdomain": "solaitest3",
            "username_or_email": "sso_user",
            "password": "sso_password123"
        })
        assert response.status_code == 302
        assert "token=" in response.url
        
        # Extract token string from URL query
        import urllib.parse
        parsed_url = urllib.parse.urlparse(response.url)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        token = query_params["token"][0]

        # 2. Get subdomain login URL with token (should auto-login and redirect to "/")
        response = client.get(
            reverse("login") + f"?token={token}",
            HTTP_HOST="solaitest3.localhost"
        )
        assert response.status_code == 302
        assert response.url == "/"

