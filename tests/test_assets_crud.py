from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone

from apps.assets.models import Brand, Category, Item, Model, TechSheetTemplate
from apps.core.models import Role, Sector, Tenant


@pytest.mark.django_db
class TestAssetsCRUD:
    
    @pytest.fixture(autouse=True)
    def setup_method(self):
        self.tenant = Tenant.objects.create(
            company_name="Tenant Test",
            trade_name="Tenant Trade",
            cnpj="11.111.111/0001-11",
            subdomain="tenanttest",
            schema_name="tenant_tenanttest",
            trial_ends_at=timezone.now() + timedelta(days=14),
        )
        self.sector = Sector.objects.create(name="Admin", tenant=self.tenant)
        self.role = Role.objects.create(
            name="AdminRole",
            tenant=self.tenant,
            sector=self.sector,
            level=100,
            is_active=True
        )
        permissions = Permission.objects.filter(
            content_type__app_label='assets',
            codename__in=[
                'view_item', 'add_item', 'change_item',
                'view_brand', 'view_category', 'view_model', 'view_techsheettemplate'
            ]
        )
        self.role.permissions.add(*permissions)
        
        user_model = get_user_model()
        self.admin = user_model.objects.create_user(
            username="admin",
            email="admin@example.com",
            password="password123",
            tenant=self.tenant,
            role=self.role,
            is_active=True
        )
        self.brand = Brand.objects.create(tenant=self.tenant, name="Brand 1")
        self.category = Category.objects.create(tenant=self.tenant, name="Category 1")
        self.item_model = Model.objects.create(tenant=self.tenant, brand=self.brand, name="Model 1")
        self.item = Item.objects.create(tenant=self.tenant, name="Item 1", model=self.item_model, item_type="consumable")

    def test_item_create_requires_name(self, client):
        client.force_login(self.admin)
        url = reverse('item_create')
        data = {
            'name': 'Test Item Name',
            'model': self.item_model.id,
            'item_type': 'consumable',
        }
        response = client.post(url, data, HTTP_HOST="tenanttest.localhost")
        assert response.status_code == 302
        item = Item.objects.get(name='Test Item Name', tenant=self.tenant)
        assert item.name == 'Test Item Name'

    def test_item_update_saves_name(self, client):
        client.force_login(self.admin)
        url = reverse('item_edit', args=[self.item.id])
        data = {
            'name': 'Updated Item Name',
            'model': self.item.model.id,
            'item_type': self.item.item_type,
        }
        response = client.post(url, data, HTTP_HOST="tenanttest.localhost")
        assert response.status_code == 302
        self.item.refresh_from_db()
        assert self.item.name == 'Updated Item Name'

    def test_brand_detail_view(self, client):
        client.force_login(self.admin)
        url = reverse('brand_detail', args=[self.brand.id])
        response = client.get(url, HTTP_HOST="tenanttest.localhost")
        assert response.status_code == 200
        assert 'brand' in response.context
        assert 'audit_history' in response.context

    def test_category_detail_view(self, client):
        client.force_login(self.admin)
        url = reverse('category_detail', args=[self.category.id])
        response = client.get(url, HTTP_HOST="tenanttest.localhost")
        assert response.status_code == 200
        assert 'category' in response.context
        assert 'audit_history' in response.context

    def test_model_detail_view(self, client):
        client.force_login(self.admin)
        url = reverse('model_detail', args=[self.item_model.id])
        response = client.get(url, HTTP_HOST="tenanttest.localhost")
        assert response.status_code == 200
        assert 'model' in response.context
        assert 'audit_history' in response.context

    def test_tech_sheet_template_detail_view(self, client):
        client.force_login(self.admin)
        template = TechSheetTemplate.objects.create(
            tenant=self.tenant,
            name="Test Template",
            template_type="custom",
            fields_schema={}
        )
        url = reverse('tech_sheet_template_detail', args=[template.id])
        response = client.get(url, HTTP_HOST="tenanttest.localhost")
        assert response.status_code == 200
        assert 'template' in response.context
        assert 'audit_history' in response.context
