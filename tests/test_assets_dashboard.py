from datetime import timedelta
import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import Client
from django.utils import timezone
from validate_docbr import CNPJ

from apps.assets.models import Batch, Brand, Category, Item, Model
from apps.core.models import Tenant, Role


@pytest.mark.django_db
class TestAssetsDashboardAndPermissions:
    def setup_method(self):
        self.cnpj_generator = CNPJ()
        self.tenant = Tenant.objects.create(
            company_name="SolAI Dashboard Inc",
            trade_name="SolAI Dashboard",
            cnpj=self.cnpj_generator.generate(),
            subdomain="solai-dashboard",
            schema_name="tenant_solai_dashboard",
            trial_ends_at=timezone.now() + timedelta(days=14),
        )
        
        # Create a specific role and user
        self.role = Role.objects.create(
            tenant=self.tenant,
            name="Stock Operator",
            level=3
        )
        
        self.user = get_user_model().objects.create_user(
            username="stock_op",
            email="operator@solai.com",
            password="password123",
            tenant=self.tenant,
            role=self.role
        )
        
        self.client = Client()
        self.headers = {"HTTP_HOST": "solai-dashboard.localhost"}

        # Seed catalog data
        self.brand = Brand.objects.create(tenant=self.tenant, name="Dashboard Brand")
        self.category = Category.objects.create(tenant=self.tenant, name="Dashboard Category")
        self.model_obj = Model.objects.create(
            tenant=self.tenant,
            name="Dashboard Model",
            brand=self.brand,
            unit_of_measure="un",
        )
        self.model_obj.categories.add(self.category)
        
        self.item = Item.objects.create(
            tenant=self.tenant,
            model=self.model_obj,
            item_type="product",
            minimum_stock=10.0,
            acquisition_price=5.0
        )

    def test_dashboard_permission_denied(self):
        # User not logged in
        response = self.client.get("/assets/dashboard/", **self.headers)
        assert response.status_code == 302 # Redirect to login

        # User logged in but no role permissions
        self.client.force_login(self.user)
        response = self.client.get("/assets/dashboard/", **self.headers)
        assert response.status_code == 403 # Permission Denied

    def test_dashboard_permission_granted(self):
        # Assign view_item permission to the role
        content_type = ContentType.objects.get_for_model(Item)
        permission = Permission.objects.get(content_type=content_type, codename="view_item")
        self.role.permissions.add(permission)

        self.client.force_login(self.user)
        response = self.client.get("/assets/dashboard/", **self.headers)
        assert response.status_code == 200

        # Verify context data is computed correctly
        context = response.context
        assert context["total_items"] == 1
        assert context["total_qty"] == 0 # No batches created yet
        assert context["total_value"] == 0.0
        assert context["low_stock_count"] == 1 # 0 < 10.0 minimum_stock

    def test_metric_calculations_with_batches(self):
        # Assign view_item permission
        content_type = ContentType.objects.get_for_model(Item)
        permission = Permission.objects.get(content_type=content_type, codename="view_item")
        self.role.permissions.add(permission)

        # Create active batch
        Batch.objects.create(
            item=self.item,
            batch_code="B_OK",
            manufacture_date=timezone.now().date() - timedelta(days=5),
            expiry_date=timezone.now().date() + timedelta(days=60),
            total_quantity=20.0,
            stock_quantity=20.0,
            status="active"
        )

        # Create expiring batch
        Batch.objects.create(
            item=self.item,
            batch_code="B_EXPIRING",
            manufacture_date=timezone.now().date() - timedelta(days=15),
            expiry_date=timezone.now().date() + timedelta(days=10),
            total_quantity=5.0,
            stock_quantity=5.0,
            status="active"
        )

        self.client.force_login(self.user)
        response = self.client.get("/assets/dashboard/", **self.headers)
        assert response.status_code == 200
        
        context = response.context
        assert context["total_items"] == 1
        assert context["total_qty"] == 25.0
        assert context["total_value"] == 125.0 # (20 + 5) * 5.0 acquisition price
        assert context["low_stock_count"] == 0 # 25.0 >= 10.0
        assert context["total_expiration_alerts"] == 1 # B_EXPIRING is expiring in 10 days (<30 days)

    def test_item_audit_history(self):
        # Assign view_item permission
        content_type = ContentType.objects.get_for_model(Item)
        permission = Permission.objects.get(content_type=content_type, codename="view_item")
        self.role.permissions.add(permission)

        # Modify item to trigger simple-history logging
        self.item.minimum_stock = 15.0
        self.item.save()

        self.client.force_login(self.user)
        response = self.client.get(f"/assets/items/{self.item.id}/", **self.headers)
        assert response.status_code == 200
        
        # Verify context contains the audit trail history
        context = response.context
        assert "audit_history" in context
        audit = context["audit_history"]
        
        # Should have 2 entries: 1 create + 1 update
        assert len(audit) == 2
        # The latest entry should be the update with changes
        assert audit[0]["type"] == "update"
        assert len(audit[0]["fields"]) == 1
        assert audit[0]["fields"][0]["field"] == "minimum_stock"

    def test_batch_audit_history(self):
        # Assign required permissions
        batch_ct = ContentType.objects.get_for_model(Batch)
        view_batch_perm = Permission.objects.get(content_type=batch_ct, codename="view_batch")
        change_batch_perm = Permission.objects.get(content_type=batch_ct, codename="change_batch")
        item_ct = ContentType.objects.get_for_model(Item)
        view_item_perm = Permission.objects.get(content_type=item_ct, codename="view_item")
        
        self.role.permissions.add(view_batch_perm, change_batch_perm, view_item_perm)

        # Create active batch
        batch = Batch.objects.create(
            item=self.item,
            batch_code="B_AUDIT_TEST",
            manufacture_date=timezone.now().date() - timedelta(days=5),
            expiry_date=timezone.now().date() + timedelta(days=60),
            total_quantity=20.0,
            stock_quantity=20.0,
            status="active"
        )

        # Modify batch to trigger history
        batch.stock_quantity = 15.0
        batch.save()

        self.client.force_login(self.user)
        
        # Verify batch edit page includes batch audit history
        response = self.client.get(f"/assets/batches/{batch.id}/edit/", **self.headers)
        assert response.status_code == 200
        assert "audit_history" in response.context
        audit = response.context["audit_history"]
        assert len(audit) == 2
        assert audit[0]["type"] == "update"
        assert len(audit[0]["fields"]) == 1
        assert audit[0]["fields"][0]["field"] == "stock_quantity"

        # Verify item detail page does NOT include batch audit history
        item_response = self.client.get(f"/assets/items/{self.item.id}/", **self.headers)
        assert item_response.status_code == 200
        item_audit = item_response.context["audit_history"]
        # Item has only 1 entry (creation) since we only modified the batch, not the item
        assert len(item_audit) == 1
        assert item_audit[0]["type"] == "create"
