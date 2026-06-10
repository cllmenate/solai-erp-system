from datetime import timedelta

import pytest
from django.contrib.auth import authenticate, get_user_model
from django.utils import timezone

from apps.core.models import Role, Tenant
from shared.utils.jwt import decode_jwt_token, generate_jwt_token


@pytest.mark.django_db
class TestAuthenticationAndModels:
    def setup_method(self):
        # Create a Tenant for testing context
        self.tenant = Tenant.objects.create(
            company_name="SolAI Testing LTDA",
            trade_name="SolAI Test",
            cnpj="88.888.888/0001-88",
            subdomain="solaitest",
            schema_name="tenant_solaitest",
            trial_ends_at=timezone.now() + timedelta(days=14),
        )
        
        # Create a test role
        self.role = Role.objects.create(
            name="Comprador",
            tenant=self.tenant,
            level=3
        )

    def test_custom_user_creation(self):
        user_model = get_user_model()
        user = user_model.objects.create_user(
            username="testuser",
            email="testuser@example.com",
            password="securepassword123",
            tenant=self.tenant,
            role=self.role,
            full_name="Test User Account"
        )
        
        assert user.id is not None
        assert user.username == "testuser"
        assert user.email == "testuser@example.com"
        assert user.role == self.role
        assert user.tenant == self.tenant
        assert user.is_staff is False
        assert user.is_superuser is False
        assert user.check_password("securepassword123") is True

    def test_authenticate_with_username_or_email(self):
        user_model = get_user_model()
        user_model.objects.create_user(
            username="dualuser",
            email="dualuser@example.com",
            password="dualpassword123",
            tenant=self.tenant,
        )

        # Auth with username
        user_by_username = authenticate(
            username="dualuser", password="dualpassword123", tenant=self.tenant
        )
        assert user_by_username is not None
        assert user_by_username.username == "dualuser"

        # Auth with email
        user_by_email = authenticate(
            username="dualuser@example.com", password="dualpassword123", tenant=self.tenant
        )
        assert user_by_email is not None
        assert user_by_email.email == "dualuser@example.com"

        # Fail auth with invalid password
        assert authenticate(
            username="dualuser", password="wrongpassword", tenant=self.tenant
        ) is None
        assert authenticate(
            username="dualuser@example.com", password="wrongpassword", tenant=self.tenant
        ) is None

    def test_authenticate_with_duplicate_credentials_across_tenants(self):
        user_model = get_user_model()
        
        # Tenant 2
        tenant2 = Tenant.objects.create(
            company_name="Another Company LTDA",
            trade_name="Another Test",
            cnpj="77.777.777/0001-77",
            subdomain="anothertest",
            schema_name="tenant_anothertest",
            trial_ends_at=timezone.now() + timedelta(days=14),
        )

        # User in Tenant 1
        user1 = user_model.objects.create_user(
            username="admin",
            email="admin@solai.com",
            password="adminpassword123",
            tenant=self.tenant,
        )

        # User in Tenant 2 with IDENTICAL username and email
        user2 = user_model.objects.create_user(
            username="admin",
            email="admin@solai.com",
            password="adminpassword123",
            tenant=tenant2,
        )

        # Authenticate specifically against Tenant 1
        auth_user1 = authenticate(username="admin", password="adminpassword123", tenant=self.tenant)
        assert auth_user1 is not None
        assert auth_user1.id == user1.id
        assert auth_user1.tenant == self.tenant

        # Authenticate specifically against Tenant 2
        auth_user2 = authenticate(username="admin", password="adminpassword123", tenant=tenant2)
        assert auth_user2 is not None
        assert auth_user2.id == user2.id
        assert auth_user2.tenant == tenant2

        # Verify that superuser login (tenant=None) does not crash and returns None (as we didn't create a superuser)
        auth_superuser = authenticate(username="admin", password="adminpassword123", tenant=None)
        assert auth_superuser is None

    def test_jwt_generation_and_decoding(self):
        user_model = get_user_model()
        user = user_model.objects.create_user(
            username="jwtuser",
            email="jwtuser@example.com",
            password="jwtpassword123",
            tenant=self.tenant,
            role=self.role
        )

        token = generate_jwt_token(user, tenant_id=self.tenant.id)
        assert token is not None
        
        payload = decode_jwt_token(token)
        assert payload is not None
        assert payload["user_id"] == str(user.id)
        assert payload["username"] == "jwtuser"
        assert payload["email"] == "jwtuser@example.com"
        assert payload["tenant_id"] == str(self.tenant.id)
        assert payload["role_id"] == str(self.role.id)
