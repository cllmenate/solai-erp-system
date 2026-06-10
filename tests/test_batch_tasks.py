from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone
from validate_docbr import CNPJ

from apps.assets.models import Batch, Brand, Category, Item, Model
from apps.assets.tasks import check_expired_batches
from apps.core.models import Role, Tenant, User


@pytest.mark.django_db
class TestBatchExpirationTasks:
    def setup_method(self):
        self.cnpj_gen = CNPJ()

        # Clear outbox
        mail.outbox = []

        # 1. Setup Tenant A
        self.tenant_a = Tenant.objects.create(
            company_name="Tenant A Corp",
            trade_name="Tenant A",
            cnpj=self.cnpj_gen.generate(),
            subdomain="tna-tenant",
            schema_name="tenant_a_schema",
            trial_ends_at=timezone.now() + timedelta(days=14),
        )
        self.role_a = Role.objects.create(
            tenant=self.tenant_a,
            name="Stock Operator",
            level=3
        )
        self.user_a = User.objects.create_user(
            username="operator_a",
            email="operator_a@tenanta.com",
            password="password123",
            tenant=self.tenant_a,
            role=self.role_a
        )

        # Catalog setup for Tenant A
        self.brand_a = Brand.objects.create(tenant=self.tenant_a, name="Brand A")
        self.category_a = Category.objects.create(tenant=self.tenant_a, name="Category A")
        self.model_a = Model.objects.create(
            tenant=self.tenant_a,
            name="Model A",
            brand=self.brand_a,
            unit_of_measure="un"
        )
        self.model_a.categories.add(self.category_a)
        self.item_a = Item.objects.create(
            tenant=self.tenant_a,
            model=self.model_a,
            item_type="product",
            minimum_stock=5.0,
            acquisition_price=10.0
        )

        # 2. Setup Tenant B
        self.tenant_b = Tenant.objects.create(
            company_name="Tenant B Corp",
            trade_name="Tenant B",
            cnpj=self.cnpj_gen.generate(),
            subdomain="tnb-tenant",
            schema_name="tenant_b_schema",
            trial_ends_at=timezone.now() + timedelta(days=14),
        )
        self.role_b = Role.objects.create(
            tenant=self.tenant_b,
            name="Warehouse Manager",
            level=2
        )
        self.user_b = User.objects.create_user(
            username="manager_b",
            email="manager_b@tenantb.com",
            password="password123",
            tenant=self.tenant_b,
            role=self.role_b
        )

        # Catalog setup for Tenant B
        self.brand_b = Brand.objects.create(tenant=self.tenant_b, name="Brand B")
        self.category_b = Category.objects.create(tenant=self.tenant_b, name="Category B")
        self.model_b = Model.objects.create(
            tenant=self.tenant_b,
            name="Model B",
            brand=self.brand_b,
            unit_of_measure="un"
        )
        self.model_b.categories.add(self.category_b)
        self.item_b = Item.objects.create(
            tenant=self.tenant_b,
            model=self.model_b,
            item_type="product",
            minimum_stock=5.0,
            acquisition_price=15.0
        )

    def test_check_expired_batches_task_marking_and_alerts(self):
        today = timezone.now().date()

        # --- Tenant A Batches ---
        # 1. Expired batch (created as active in future, then updated directly in DB to past date)
        b_expired_a = Batch.objects.create(
            item=self.item_a,
            batch_code="B_EXP_A",
            manufacture_date=today - timedelta(days=30),
            expiry_date=today + timedelta(days=30),
            total_quantity=100.0,
            stock_quantity=50.0,
            status="active"
        )
        Batch.objects.filter(id=b_expired_a.id).update(expiry_date=today - timedelta(days=2))

        # 2. Expiring soon batch (4 days from now)
        b_expiring_a = Batch.objects.create(
            item=self.item_a,
            batch_code="B_SOON_A",
            manufacture_date=today - timedelta(days=15),
            expiry_date=today + timedelta(days=4),
            total_quantity=50.0,
            stock_quantity=30.0,
            status="active"
        )
        # 3. Safe batch (15 days from now)
        b_safe_a = Batch.objects.create(
            item=self.item_a,
            batch_code="B_SAFE_A",
            manufacture_date=today - timedelta(days=5),
            expiry_date=today + timedelta(days=15),
            total_quantity=20.0,
            stock_quantity=20.0,
            status="active"
        )

        # --- Tenant B Batches ---
        # 1. Expired batch (created as active in future, then updated directly in DB to past date)
        b_expired_b = Batch.objects.create(
            item=self.item_b,
            batch_code="B_EXP_B",
            manufacture_date=today - timedelta(days=40),
            expiry_date=today + timedelta(days=30),
            total_quantity=10.0,
            stock_quantity=10.0,
            status="active"
        )
        Batch.objects.filter(id=b_expired_b.id).update(expiry_date=today - timedelta(days=5))
        # 2. Safe batch (30 days from now)
        b_safe_b = Batch.objects.create(
            item=self.item_b,
            batch_code="B_SAFE_B",
            manufacture_date=today - timedelta(days=5),
            expiry_date=today + timedelta(days=30),
            total_quantity=10.0,
            stock_quantity=10.0,
            status="active"
        )

        # Run the task
        result = check_expired_batches()
        assert "Processed 2 tenants successfully" in result

        # Refresh from database
        b_expired_a.refresh_from_db()
        b_expiring_a.refresh_from_db()
        b_safe_a.refresh_from_db()

        b_expired_b.refresh_from_db()
        b_safe_b.refresh_from_db()

        # Check status updates
        assert b_expired_a.status == "expired"
        assert b_expiring_a.status == "active"
        assert b_safe_a.status == "active"

        assert b_expired_b.status == "expired"
        assert b_safe_b.status == "active"

        # Check audit history logs (simple-history) for expired batches
        history_a = b_expired_a.history.all()
        assert history_a.count() >= 2  # Created + status updated
        assert history_a[0].status == "expired"

        history_b = b_expired_b.history.all()
        assert history_b.count() >= 2
        assert history_b[0].status == "expired"

        # Check email outbox
        # Should have sent 2 emails: 1 for Tenant A, 1 for Tenant B
        assert len(mail.outbox) == 2

        # Verify Tenant A Email
        email_a = next(e for e in mail.outbox if "Tenant A" in e.subject)
        assert "operator_a@tenanta.com" in email_a.to
        assert "B_EXP_A" in email_a.body
        assert "B_SOON_A" in email_a.body
        assert "B_SAFE_A" not in email_a.body

        # Verify Tenant B Email
        email_b = next(e for e in mail.outbox if "Tenant B" in e.subject)
        assert "manager_b@tenantb.com" in email_b.to
        assert "B_EXP_B" in email_b.body
        assert "B_SAFE_B" not in email_b.body
