from datetime import timedelta
import pytest
from django.contrib.auth import get_user_model, authenticate
from django.utils import timezone
from apps.core.models import Tenant, Role
from shared.utils.jwt import generate_jwt_token, decode_jwt_token


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
        User = get_user_model()
        user = User.objects.create_user(
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
        User = get_user_model()
        User.objects.create_user(
            username="dualuser",
            email="dualuser@example.com",
            password="dualpassword123",
            tenant=self.tenant,
        )

        # Auth with username
        user_by_username = authenticate(username="dualuser", password="dualpassword123")
        assert user_by_username is not None
        assert user_by_username.username == "dualuser"

        # Auth with email
        user_by_email = authenticate(username="dualuser@example.com", password="dualpassword123")
        assert user_by_email is not None
        assert user_by_email.email == "dualuser@example.com"

        # Fail auth with invalid password
        assert authenticate(username="dualuser", password="wrongpassword") is None
        assert authenticate(username="dualuser@example.com", password="wrongpassword") is None

    def test_jwt_generation_and_decoding(self):
        User = get_user_model()
        user = User.objects.create_user(
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
