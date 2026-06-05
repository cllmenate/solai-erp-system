from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client
from django.utils import timezone
from validate_docbr import CNPJ

from apps.assets.models import Batch, Brand, Category, Item, Model, TechSheetTemplate
from apps.core.models import Tenant
from shared.utils.jwt import generate_jwt_token


@pytest.mark.django_db
class TestAssetsModels:
    def setup_method(self):
        self.cnpj_generator = CNPJ()
        self.tenant = Tenant.objects.create(
            company_name="SolAI Assets Inc",
            trade_name="SolAI Assets",
            cnpj=self.cnpj_generator.generate(),
            subdomain="solai-assets",
            schema_name="tenant_solai_assets",
            trial_ends_at=timezone.now() + timedelta(days=14),
        )
        self.brand = Brand.objects.create(
            tenant=self.tenant,
            name="Nestle",
            website="https://www.nestle.com"
        )

    def test_category_depth_limit(self):
        """
        Verify that adding a category at depth 4 raises a ValidationError.
        """
        cat1 = Category.objects.create(tenant=self.tenant, name="Alimentos")
        cat2 = Category.objects.create(tenant=self.tenant, name="Doces", parent=cat1)
        cat3 = Category.objects.create(tenant=self.tenant, name="Chocolates", parent=cat2)
        
        # Max depth is 3. Adding cat4 (parent=cat3) should fail since cat3 is already at depth 3.
        with pytest.raises(ValidationError):
            Category.objects.create(tenant=self.tenant, name="Chocolate Amargo", parent=cat3)

    def test_tech_sheet_nutritional_validation(self):
        """
        Verify that nutritional templates require all mandatory ANVISA fields.
        """
        # Nutritional template missing 'sodio'
        incomplete_schema = {
            "porção": "100g",
            "valor_energetico": "200 kcal",
            "carboidratos": "10g",
            "proteinas": "5g",
            "gorduras_totais": "2g",
            "gorduras_saturadas": "0g",
            "gorduras_trans": "0g",
            "fibras": "1g",
        }
        with pytest.raises(ValidationError):
            TechSheetTemplate.objects.create(
                tenant=self.tenant,
                name="Nutricional Incompleto",
                template_type="nutritional",
                fields_schema=incomplete_schema
            )

        # Complete nutritional template
        complete_schema = incomplete_schema.copy()
        complete_schema["sodio"] = "50mg"
        template = TechSheetTemplate.objects.create(
            tenant=self.tenant,
            name="Nutricional Completo",
            template_type="nutritional",
            fields_schema=complete_schema
        )
        assert template.id is not None

    def test_model_template_inheritance(self):
        """
        Verify that models inherit templates from categories.
        """
        template = TechSheetTemplate.objects.create(
            tenant=self.tenant,
            name="Nutricional Test",
            template_type="nutritional",
            fields_schema={
                "porção": "50g", "valor_energetico": "100 kcal", "carboidratos": "5g",
                "proteinas": "3g", "gorduras_totais": "1g", "gorduras_saturadas": "0g",
                "gorduras_trans": "0g", "fibras": "0.5g", "sodio": "10mg"
            }
        )
        category = Category.objects.create(tenant=self.tenant, name="Laticinios")
        category.tech_sheet_templates.add(template)

        model_obj = Model.objects.create(
            tenant=self.tenant,
            name="Leite Desnatado 1L",
            brand=self.brand,
            unit_of_measure="L"
        )
        model_obj.categories.add(category)

        # Inherited template list should contain the template from category
        assert template in model_obj.all_tech_sheet_templates

    def test_item_sku_and_barcode_generation(self):
        """
        Verify that SKU and Barcode are correctly auto-generated.
        """
        model_obj = Model.objects.create(
            tenant=self.tenant,
            name="Achocolatado 400g",
            brand=self.brand,
            unit_of_measure="un"
        )
        item1 = Item.objects.create(
            tenant=self.tenant,
            model=model_obj,
            item_type="product",
            ncm="1806.90.00"
        )
        
        # Tenant subdomain is "solai-assets", prefix should be "SOL" (first 3 chars upper)
        # Type is "product" -> code is "PROD"
        # First product -> 00001
        assert item1.sku == "SOL-PROD-00001"
        assert len(item1.barcode) == 13  # Valid EAN-13 length

        # Add second item of type "product"
        item2 = Item.objects.create(
            tenant=self.tenant,
            model=model_obj,
            item_type="product"
        )
        assert item2.sku == "SOL-PROD-00002"

    def test_batch_expiration_and_negative_stock(self):
        """
        Verify batch status transitions to expired if dates in past, and prevents negative stock.
        """
        model_obj = Model.objects.create(
            tenant=self.tenant,
            name="Iogurte Morango",
            brand=self.brand,
            unit_of_measure="un"
        )
        item = Item.objects.create(
            tenant=self.tenant,
            model=model_obj,
            item_type="product"
        )

        # Expiry date in past
        past_date = timezone.now().date() - timedelta(days=1)
        batch = Batch.objects.create(
            item=item,
            batch_code="L123",
            manufacture_date=past_date - timedelta(days=10),
            expiry_date=past_date,
            total_quantity=100.0,
            stock_quantity=100.0
        )
        assert batch.status == "expired"

        # Try to make stock negative
        batch.stock_quantity = -5.0
        with pytest.raises(ValidationError):
            batch.save()


@pytest.mark.django_db
class TestAssetsAPIEndpoints:
    def setup_method(self):
        self.cnpj_generator = CNPJ()
        self.tenant = Tenant.objects.create(
            company_name="SolAI Assets Inc",
            trade_name="SolAI Assets",
            cnpj=self.cnpj_generator.generate(),
            subdomain="solai-assets",
            schema_name="tenant_solai_assets",
            trial_ends_at=timezone.now() + timedelta(days=14),
        )
        self.user = get_user_model().objects.create_user(
            username="assets_admin",
            email="admin@solai-assets.com",
            password="password123",
            tenant=self.tenant,
        )
        self.token = generate_jwt_token(self.user, tenant_id=self.tenant.id)
        self.client = Client()
        self.auth_headers = {
            "HTTP_AUTHORIZATION": f"Bearer {self.token}",
            "HTTP_X_TENANT_ID": str(self.tenant.id),
        }

    def test_create_brand_via_api(self):
        payload = {
            "name": "Coca-Cola",
            "website": "https://coca-cola.com"
        }
        response = self.client.post(
            "/api/assets/brands",
            data=payload,
            content_type="application/json",
            **self.auth_headers
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Coca-Cola"
        assert Brand.objects.filter(tenant=self.tenant, name="Coca-Cola").exists()

    def test_create_category_via_api(self):
        payload = {
            "name": "Bebidas",
            "tech_sheet_template_ids": []
        }
        response = self.client.post(
            "/api/assets/categories",
            data=payload,
            content_type="application/json",
            **self.auth_headers
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Bebidas"
        assert Category.objects.filter(tenant=self.tenant, name="Bebidas").exists()


@pytest.mark.django_db
class TestAssetsViews:
    def setup_method(self):
        self.cnpj_generator = CNPJ()
        self.tenant = Tenant.objects.create(
            company_name="SolAI Views Inc",
            trade_name="SolAI Views",
            cnpj=self.cnpj_generator.generate(),
            subdomain="solai-views",
            schema_name="tenant_solai_views",
            trial_ends_at=timezone.now() + timedelta(days=14),
        )
        self.user = get_user_model().objects.create_superuser(
            username="views_admin",
            email="admin@solai-views.com",
            password="password123",
            tenant=self.tenant,
        )
        self.client = Client()
        self.client.force_login(self.user)
        self.headers = {"HTTP_HOST": "solai-views.localhost"}

        # Seed initial models
        self.brand = Brand.objects.create(tenant=self.tenant, name="Nestle Views")
        self.category = Category.objects.create(tenant=self.tenant, name="Alimentos Views")
        self.model_obj = Model.objects.create(
            tenant=self.tenant,
            name="Leite Views",
            brand=self.brand,
            unit_of_measure="un",
        )
        self.item = Item.objects.create(
            tenant=self.tenant,
            model=self.model_obj,
            item_type="product",
        )

    def test_brand_views(self):
        # List
        response = self.client.get("/assets/brands/", **self.headers)
        assert response.status_code == 200
        assert "Nestle Views" in response.content.decode("utf-8")

        # Create
        response = self.client.post("/assets/brands/create/", {
            "name": "Nova Marca Views",
            "website": "https://novamarca.com",
            "description": "Teste"
        }, **self.headers)
        assert response.status_code == 302
        assert Brand.objects.filter(tenant=self.tenant, name="Nova Marca Views").exists()

        # Update
        brand = Brand.objects.get(tenant=self.tenant, name="Nova Marca Views")
        response = self.client.post(f"/assets/brands/{brand.id}/edit/", {
            "name": "Marca Views Editada",
            "website": "https://editada.com",
            "description": "Edição"
        }, **self.headers)
        assert response.status_code == 302
        brand.refresh_from_db()
        assert brand.name == "Marca Views Editada"

        # Delete
        response = self.client.get(f"/assets/brands/{brand.id}/delete/", **self.headers)
        assert response.status_code == 302
        brand.refresh_from_db()
        assert brand.is_active is False

    def test_category_views(self):
        # List
        response = self.client.get("/assets/categories/", **self.headers)
        assert response.status_code == 200
        assert "Alimentos Views" in response.content.decode("utf-8")

        # Create
        response = self.client.post("/assets/categories/create/", {
            "name": "Sub Categoria Views",
            "parent": str(self.category.id),
            "description": "Subcat"
        }, **self.headers)
        assert response.status_code == 302
        assert Category.objects.filter(tenant=self.tenant, name="Sub Categoria Views", parent=self.category).exists()

        # Update
        sub_cat = Category.objects.get(tenant=self.tenant, name="Sub Categoria Views")
        response = self.client.post(f"/assets/categories/{sub_cat.id}/edit/", {
            "name": "Subcat Editada",
            "parent": "",
            "description": "Sem pai"
        }, **self.headers)
        assert response.status_code == 302
        sub_cat.refresh_from_db()
        assert sub_cat.name == "Subcat Editada"
        assert sub_cat.parent is None

    def test_model_views(self):
        # List
        response = self.client.get("/assets/models/", **self.headers)
        assert response.status_code == 200
        assert "Leite Views" in response.content.decode("utf-8")

        # Create
        response = self.client.post("/assets/models/create/", {
            "name": "Iogurte Views",
            "brand": str(self.brand.id),
            "categories": [str(self.category.id)],
            "unit_of_measure": "PCT",
            "weight": "0.500",
            "description": "Model test"
        }, **self.headers)
        assert response.status_code == 302
        assert Model.objects.filter(tenant=self.tenant, name="Iogurte Views").exists()

    def test_batch_views(self):
        # List
        response = self.client.get("/assets/batches/", **self.headers)
        assert response.status_code == 200

        # Create
        response = self.client.post("/assets/batches/create/", {
            "item": str(self.item.id),
            "batch_code": "B123_VIEWS",
            "manufacture_date": "2026-06-01",
            "expiry_date": "2026-06-15",
            "total_quantity": "100",
            "stock_quantity": "100",
            "status": "active"
        }, **self.headers)
        assert response.status_code == 302
        assert Batch.objects.filter(batch_code="B123_VIEWS").exists()

