from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from validate_docbr import CNPJ, CPF

from apps.commercial.models import Address, Contact, Partner
from apps.core.models import Tenant
from shared.utils.jwt import generate_jwt_token


@pytest.mark.django_db
class TestCommercialModels:
    def setup_method(self):
        self.cnpj_generator = CNPJ()
        self.cpf_generator = CPF()
        # Create a Tenant
        self.tenant = Tenant.objects.create(
            company_name="SolAI Commercial Ltd",
            trade_name="SolAI Commercial",
            cnpj=self.cnpj_generator.generate(),
            subdomain="solai-comm",
            schema_name="tenant_solai_comm",
            trial_ends_at=timezone.now() + timedelta(days=14),
        )

    def test_create_partner_valid_cnpj(self):
        """
        Verify that a Partner is created successfully with a valid CNPJ.
        """
        valid_cnpj = self.cnpj_generator.generate()
        partner = Partner.objects.create(
            tenant=self.tenant,
            is_customer=True,
            person_type="company",
            legal_name="Cliente PJ Exemplo LTDA",
            trade_name="Cliente PJ",
            document=valid_cnpj,
        )
        assert partner.id is not None
        assert partner.document == valid_cnpj
        
        # Break format definition to fit 88 chars
        expected_formatted = (
            f"{valid_cnpj[:2]}.{valid_cnpj[2:5]}.{valid_cnpj[5:8]}/"
            f"{valid_cnpj[8:12]}-{valid_cnpj[12:]}"
        )
        assert partner.formatted_document == expected_formatted

    def test_create_partner_invalid_document_raises_validation_error(self):
        """
        Verify that invalid CPF or CNPJ documents raise a ValidationError.
        """
        # Invalid CNPJ
        with pytest.raises(ValidationError):
            Partner.objects.create(
                tenant=self.tenant,
                is_customer=True,
                person_type="company",
                legal_name="Cliente PJ Invalido",
                document="11111111111111",  # Invalid CNPJ structure
            )

        # Invalid CPF length / format
        with pytest.raises(ValidationError):
            Partner.objects.create(
                tenant=self.tenant,
                is_customer=True,
                person_type="individual",
                legal_name="Cliente PF Invalido",
                document="12345",  # Too short
            )

    def test_partner_must_have_at_least_one_type(self):
        """
        Verify that a partner must be marked as customer, supplier, or carrier.
        """
        valid_cnpj = self.cnpj_generator.generate()
        with pytest.raises(ValidationError):
            Partner.objects.create(
                tenant=self.tenant,
                person_type="company",
                legal_name="Sem tipo",
                document=valid_cnpj,
            )

    def test_partner_contacts_and_addresses(self):
        """
        Verify that contacts and addresses are linked correctly.
        """
        valid_cnpj = self.cnpj_generator.generate()
        partner = Partner.objects.create(
            tenant=self.tenant,
            is_customer=True,
            legal_name="Cliente PJ Exemplo LTDA",
            document=valid_cnpj,
        )
        Contact.objects.create(
            partner=partner,
            name="John Doe",
            email="john@example.com",
            phone="11999999999",
            is_primary=True,
        )
        Address.objects.create(
            partner=partner,
            label="Matriz",
            zip_code="01001-000",
            street="Praça da Sé",
            number="111",
            neighborhood="Sé",
            city="São Paulo",
            state="SP",
        )
        
        assert partner.contacts.count() == 1
        assert partner.addresses.count() == 1
        assert partner.contacts.first().name == "John Doe"
        assert partner.addresses.first().label == "Matriz"


@pytest.mark.django_db
class TestCommercialAPIEndpoints:
    def setup_method(self):
        self.cnpj_generator = CNPJ()
        self.tenant = Tenant.objects.create(
            company_name="SolAI Commercial Ltd",
            trade_name="SolAI Commercial",
            cnpj=self.cnpj_generator.generate(),
            subdomain="solai-comm",
            schema_name="tenant_solai_comm",
            trial_ends_at=timezone.now() + timedelta(days=14),
        )
        self.user = get_user_model().objects.create_user(
            username="comm_admin",
            email="admin@solai-comm.com",
            password="password123",
            tenant=self.tenant,
        )
        self.token = generate_jwt_token(self.user, tenant_id=self.tenant.id)
        self.client = Client()
        self.auth_headers = {
            "HTTP_AUTHORIZATION": f"Bearer {self.token}",
            "HTTP_X_TENANT_ID": str(self.tenant.id),
        }

    def test_create_partner_api(self):
        """
        Verify creating a partner via Ninja API POST endpoint.
        """
        valid_cnpj = self.cnpj_generator.generate()
        payload = {
            "is_customer": True,
            "is_supplier": False,
            "is_carrier": False,
            "person_type": "company",
            "legal_name": "API Partner Corp",
            "trade_name": "API Partner",
            "document": valid_cnpj,
            "contacts": [
                {
                    "name": "Jane Doe",
                    "email": "jane@api.com",
                    "phone": "11988887777",
                    "role": "Diretora",
                    "is_primary": True
                }
            ],
            "addresses": [
                {
                    "label": "Matriz",
                    "zip_code": "01001-000",
                    "street": "Avenida Paulista",
                    "number": "1000",
                    "neighborhood": "Bela Vista",
                    "city": "São Paulo",
                    "state": "SP",
                    "country": "BR",
                    "is_collection": True,
                    "is_delivery": True
                }
            ]
        }
        
        response = self.client.post(
            "/api/partners/",
            data=payload,
            content_type="application/json",
            **self.auth_headers
        )
        if response.status_code != 201:
            print("RESPONSE ERROR:", response.content)
        assert response.status_code == 201
        data = response.json()
        assert data["legal_name"] == "API Partner Corp"
        assert len(data["contacts"]) == 1
        assert len(data["addresses"]) == 1
        assert data["contacts"][0]["name"] == "Jane Doe"
        assert data["addresses"][0]["street"] == "Avenida Paulista"

    def test_create_partner_api_rule_validation(self):
        """
        Verify creating a partner fails if no contact or address is provided.
        """
        valid_cnpj = self.cnpj_generator.generate()
        payload = {
            "is_customer": True,
            "legal_name": "No Contacts Corp",
            "document": valid_cnpj,
            "contacts": [],
            "addresses": []
        }
        response = self.client.post(
            "/api/partners/",
            data=payload,
            content_type="application/json",
            **self.auth_headers
        )
        assert response.status_code == 400
        assert "ao menos 1 contato" in response.json()["message"]


@pytest.mark.django_db
class TestCommercialViews:
    def setup_method(self):
        self.cnpj_generator = CNPJ()
        self.tenant = Tenant.objects.create(
            company_name="SolAI Commercial Ltd",
            trade_name="SolAI Commercial",
            cnpj=self.cnpj_generator.generate(),
            subdomain="solai-comm",
            schema_name="tenant_solai_comm",
            trial_ends_at=timezone.now() + timedelta(days=14),
        )
        self.user = get_user_model().objects.create_user(
            username="comm_admin",
            email="admin@solai-comm.com",
            password="password123",
            tenant=self.tenant,
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_partner_list_view_renders(self):
        valid_cnpj = self.cnpj_generator.generate()
        Partner.objects.create(
            tenant=self.tenant,
            is_customer=True,
            legal_name="List Partner Corp",
            document=valid_cnpj,
        )
        
        # Break URL parameters to stay within line limit
        url = reverse("partner_list")
        response = self.client.get(
            url,
            HTTP_HOST="solai-comm.localhost"
        )
        assert response.status_code == 200
        assert b"List Partner Corp" in response.content

    def test_htmx_partials_render(self):
        url_contact = reverse("htmx_contact_row") + "?index=3"
        response = self.client.get(
            url_contact,
            HTTP_HOST="solai-comm.localhost"
        )
        assert response.status_code == 200
        assert b"contact_name[]" in response.content
        assert b"Principal" in response.content

        url_address = reverse("htmx_address_row") + "?index=5"
        response = self.client.get(
            url_address,
            HTTP_HOST="solai-comm.localhost"
        )
        assert response.status_code == 200
        assert b"address_zip_code[]" in response.content
        assert b"UF *" in response.content
