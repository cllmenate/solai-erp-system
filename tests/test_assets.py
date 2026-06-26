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

    def test_list_items_advanced_search_and_filters(self):
        brand = Brand.objects.create(tenant=self.tenant, name="Apple")
        category = Category.objects.create(tenant=self.tenant, name="Smartphones")
        model = Model.objects.create(tenant=self.tenant, name="iPhone 15", brand=brand)
        model.categories.add(category)
        
        Item.objects.create(
            tenant=self.tenant,
            model=model,
            item_type="product",
            ncm="8517.13.00",
            sku="APL-IPH15-01",
            barcode="190199608518",
            acquisition_price=800.0,
            sale_price=1000.0,
        )
        
        response = self.client.get(
            "/api/assets/items?search=Apple",
            **self.auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["sku"] == "APL-IPH15-01"

        response = self.client.get(
            "/api/assets/items?ncm=8517",
            **self.auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1

    def test_list_items_price_filters_api(self):
        brand = Brand.objects.create(tenant=self.tenant, name="Price Brand")
        model = Model.objects.create(tenant=self.tenant, name="Price Model", brand=brand)
        Item.objects.create(
            tenant=self.tenant, model=model, item_type="product",
            acquisition_price=10.0, sale_price=20.0, sku="P1"
        )
        Item.objects.create(
            tenant=self.tenant, model=model, item_type="product",
            acquisition_price=50.0, sale_price=100.0, sku="P2"
        )
        Item.objects.create(
            tenant=self.tenant, model=model, item_type="product",
            acquisition_price=200.0, sale_price=400.0, sku="P3"
        )

        response = self.client.get("/api/assets/items?min_sale_price=50&max_sale_price=150", **self.auth_headers)
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["sku"] == "P2"

        response = self.client.get("/api/assets/items?min_acquisition_price=40&max_acquisition_price=250", **self.auth_headers)
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 2
        skus = {item["sku"] for item in items}
        assert skus == {"P2", "P3"}

    def test_list_models_category_filter_api(self):
        brand = Brand.objects.create(tenant=self.tenant, name="Model Brand")
        cat1 = Category.objects.create(tenant=self.tenant, name="Cat One")
        cat2 = Category.objects.create(tenant=self.tenant, name="Cat Two")
        m1 = Model.objects.create(tenant=self.tenant, name="Model One", brand=brand)
        m1.categories.add(cat1)
        m2 = Model.objects.create(tenant=self.tenant, name="Model Two", brand=brand)
        m2.categories.add(cat2)

        response = self.client.get(f"/api/assets/models?category_id={cat1.id}", **self.auth_headers)
        assert response.status_code == 200
        models = response.json()["items"]
        assert len(models) == 1
        assert models[0]["name"] == "Model One"

    def test_list_batches_status_and_date_filters_api(self):
        brand = Brand.objects.create(tenant=self.tenant, name="Batch Brand")
        model = Model.objects.create(tenant=self.tenant, name="Batch Model", brand=brand)
        item = Item.objects.create(tenant=self.tenant, model=model, item_type="product")
        today = timezone.now().date()
        Batch.objects.create(
            item=item, batch_code="B1", total_quantity=10, stock_quantity=10,
            status="active", manufacture_date=today - timedelta(days=10),
            expiry_date=today + timedelta(days=10)
        )
        Batch.objects.create(
            item=item, batch_code="B2", total_quantity=10, stock_quantity=10,
            status="expired", manufacture_date=today - timedelta(days=30),
            expiry_date=today - timedelta(days=5)
        )

        response = self.client.get("/api/assets/batches?status=expired", **self.auth_headers)
        assert response.status_code == 200
        batches = response.json()["items"]
        assert len(batches) == 1
        assert batches[0]["batch_code"] == "B2"

        response = self.client.get(
            f"/api/assets/batches?expiry_min={today}&expiry_max={today + timedelta(days=20)}",
            **self.auth_headers
        )
        assert response.status_code == 200
        batches = response.json()["items"]
        assert len(batches) == 1
        assert batches[0]["batch_code"] == "B1"


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

    def test_item_list_advanced_search_and_pagination(self):
        brand = Brand.objects.create(tenant=self.tenant, name="Coca-Cola Corp")
        category = Category.objects.create(tenant=self.tenant, name="Refrigerantes")
        model = Model.objects.create(tenant=self.tenant, name="Coca-Cola 2L", brand=brand)
        model.categories.add(category)
        
        # Create 25 items to test pagination
        for i in range(25):
            Item.objects.create(
                tenant=self.tenant,
                model=model,
                item_type="product",
                sku=f"COC-2L-{i:03d}",
                barcode=f"78949000100{i:02d}",
                ncm="2202.10.00",
            )
            
        # Test general search by brand name
        response = self.client.get("/assets/items/?search=Coca-Cola", **self.headers)
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "Coca-Cola" in content
        assert "Mostrando de" in content
        assert ">1<" in content
        assert ">20<" in content
        assert ">25<" in content
        
        # Test specific brand filter
        response = self.client.get(f"/assets/items/?brand={brand.id}", **self.headers)
        assert response.status_code == 200
        content_brand = response.content.decode("utf-8")
        assert "Mostrando de" in content_brand
        assert ">1<" in content_brand
        assert ">20<" in content_brand
        assert ">25<" in content_brand

    def test_item_list_price_filters_view(self):
        brand = Brand.objects.create(tenant=self.tenant, name="View Brand")
        model = Model.objects.create(tenant=self.tenant, name="View Model", brand=brand)
        Item.objects.create(
            tenant=self.tenant, model=model, item_type="product",
            acquisition_price=10.0, sale_price=20.0, sku="VP1"
        )
        Item.objects.create(
            tenant=self.tenant, model=model, item_type="product",
            acquisition_price=50.0, sale_price=100.0, sku="VP2"
        )

        response = self.client.get("/assets/items/?min_sale_price=50&max_sale_price=150", **self.headers)
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "VP2" in content
        assert "VP1" not in content

    def test_model_list_category_filter_view(self):
        brand = Brand.objects.create(tenant=self.tenant, name="View Model Brand")
        cat1 = Category.objects.create(tenant=self.tenant, name="V-Cat One")
        cat2 = Category.objects.create(tenant=self.tenant, name="V-Cat Two")
        m1 = Model.objects.create(tenant=self.tenant, name="V-Model One", brand=brand)
        m1.categories.add(cat1)
        m2 = Model.objects.create(tenant=self.tenant, name="V-Model Two", brand=brand)
        m2.categories.add(cat2)

        response = self.client.get(f"/assets/models/?category={cat1.id}", **self.headers)
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "V-Model One" in content
        assert "V-Model Two" not in content

    def test_batch_list_status_and_date_filters_view(self):
        brand = Brand.objects.create(tenant=self.tenant, name="View Batch Brand")
        model = Model.objects.create(tenant=self.tenant, name="View Batch Model", brand=brand)
        item = Item.objects.create(tenant=self.tenant, model=model, item_type="product")
        today = timezone.now().date()
        Batch.objects.create(
            item=item, batch_code="VB1", total_quantity=10, stock_quantity=10,
            status="active", manufacture_date=today - timedelta(days=10),
            expiry_date=today + timedelta(days=10)
        )
        Batch.objects.create(
            item=item, batch_code="VB2", total_quantity=10, stock_quantity=10,
            status="expired", manufacture_date=today - timedelta(days=30),
            expiry_date=today - timedelta(days=5)
        )

        response = self.client.get("/assets/batches/?status=expired", **self.headers)
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "VB2" in content
        assert "VB1" not in content

        response = self.client.get(f"/assets/batches/?expiry_min={today}&expiry_max={today + timedelta(days=20)}", **self.headers)
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "VB1" in content
        assert "VB2" not in content

