from barcode.ean import EuropeanArticleNumber13
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import BaseModel


class Brand(BaseModel):
    """
    Brand represents the manufacturer or brand name of item models.
    """
    tenant = models.ForeignKey(
        "core.Tenant",
        on_delete=models.CASCADE,
        related_name="brands",
    )
    website = models.URLField(blank=True, null=True, verbose_name="Site da Marca")

    class Meta:
        verbose_name = "marca"
        verbose_name_plural = "marcas"
        unique_together = ("tenant", "name")

    def __str__(self):
        return f"{self.name} ({self.tenant.trade_name})"


class TechSheetTemplate(BaseModel):
    """
    Technical sheet template defining custom schema of fields (nutritional, technical, etc.).
    """
    TEMPLATE_TYPES = [
        ("nutritional", "Nutritional (ANVISA)"),
        ("technical", "Technical"),
        ("chemical", "Chemical"),
        ("custom", "Custom"),
    ]

    tenant = models.ForeignKey(
        "core.Tenant",
        on_delete=models.CASCADE,
        related_name="tech_sheet_templates",
    )
    template_type = models.CharField(
        max_length=50,
        choices=TEMPLATE_TYPES,
        default="custom",
        verbose_name="Tipo de Template",
    )
    fields_schema = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Esquema de Campos",
    )

    class Meta:
        verbose_name = "template de ficha técnica"
        verbose_name_plural = "templates de ficha técnica"
        unique_together = ("tenant", "name")

    def clean(self):
        super().clean()
        if self.template_type == "nutritional":
            # TECH-01: Must contain specific fields for nutritional templates
            required_fields = {
                "porção",
                "valor_energetico",
                "carboidratos",
                "proteinas",
                "gorduras_totais",
                "gorduras_saturadas",
                "gorduras_trans",
                "fibras",
                "sodio",
            }
            # Fields can be key/value schema or keys inside fields_schema dict
            schema_keys = set(self.fields_schema.keys())
            missing = required_fields - schema_keys
            if missing:
                raise ValidationError(
                    f"Templates nutricionais ANVISA devem conter obrigatoriamente os seguintes campos: {', '.join(missing)}"
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class Category(BaseModel):
    """
    Hierarchical category taxonomy for catalog items. Max depth is 3.
    """
    tenant = models.ForeignKey(
        "core.Tenant",
        on_delete=models.CASCADE,
        related_name="categories",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="Categoria Pai",
    )
    tech_sheet_templates = models.ManyToManyField(
        TechSheetTemplate,
        blank=True,
        related_name="categories",
        verbose_name="Templates Associados",
    )

    class Meta:
        verbose_name = "categoria"
        verbose_name_plural = "categorias"
        unique_together = ("tenant", "name")

    def clean(self):
        super().clean()
        # Enforce maximum depth of 3
        if self.parent:
            depth = 1
            curr = self.parent
            while curr.parent:
                depth += 1
                curr = curr.parent
                if depth >= 3:
                    raise ValidationError(
                        "A profundidade máxima da árvore de categorias é de 3 níveis."
                    )
            
            # Prevent circular reference
            if self.parent == self:
                raise ValidationError("Uma categoria não pode ser pai de si mesma.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class Model(BaseModel):
    """
    Item model (e.g. iPhone 15 Pro, Organic Sugar 1kg) belonging to a brand & categories.
    """
    tenant = models.ForeignKey(
        "core.Tenant",
        on_delete=models.CASCADE,
        related_name="item_models",
    )
    brand = models.ForeignKey(
        Brand,
        on_delete=models.PROTECT,
        related_name="models",
        verbose_name="Marca",
    )
    categories = models.ManyToManyField(
        Category,
        related_name="models",
        verbose_name="Categorias",
    )
    unit_of_measure = models.CharField(
        max_length=50,
        verbose_name="Unidade de Medida",
    )
    weight = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
        verbose_name="Peso Unitário (kg)",
    )
    tech_sheet_templates = models.ManyToManyField(
        TechSheetTemplate,
        blank=True,
        related_name="models",
        verbose_name="Templates de Ficha Técnica",
    )

    class Meta:
        verbose_name = "modelo de item"
        verbose_name_plural = "modelos de item"
        unique_together = ("tenant", "name")

    @property
    def all_tech_sheet_templates(self):
        """
        Gathers direct templates plus inherited ones from categories (ASSET-007).
        """
        direct_templates = list(self.tech_sheet_templates.all())
        category_templates = []
        # Categories may have many templates associated
        for category in self.categories.all():
            category_templates.extend(list(category.tech_sheet_templates.all()))
        
        seen = set()
        result = []
        for t in direct_templates + category_templates:
            if t.id not in seen:
                seen.add(t.id)
                result.append(t)
        return result


class Item(BaseModel):
    """
    Individual items with unique SKU and Barcode belonging to a Model.
    """
    ITEM_TYPES = [
        ("input", "Insumo"),
        ("product", "Produto"),
        ("asset", "Ativo"),
        ("consumable", "Consumo"),
    ]

    tenant = models.ForeignKey(
        "core.Tenant",
        on_delete=models.CASCADE,
        related_name="items",
    )
    model = models.ForeignKey(
        Model,
        on_delete=models.PROTECT,
        related_name="items",
        verbose_name="Modelo",
    )
    item_type = models.CharField(
        max_length=20,
        choices=ITEM_TYPES,
        verbose_name="Tipo de Item",
    )
    ncm = models.CharField(
        max_length=10,
        blank=True,
        null=True,
        db_index=True,
        verbose_name="NCM",
    )
    sku = models.CharField(
        max_length=100,
        unique=True,
        blank=True,
        verbose_name="SKU",
    )
    barcode = models.CharField(
        max_length=100,
        unique=True,
        blank=True,
        verbose_name="Código de Barras",
    )
    serial_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Número de Série",
    )
    acquisition_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        verbose_name="Preço de Aquisição",
    )
    sale_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        verbose_name="Preço de Venda",
    )
    minimum_stock = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=0.000,
        verbose_name="Estoque Mínimo",
    )

    class Meta:
        verbose_name = "item"
        verbose_name_plural = "itens"

    def clean(self):
        super().clean()
        # ITEM-03: Immutable item_type after transaction linked (or batches created)
        if self.pk:
            try:
                original = Item.objects.get(pk=self.pk)
                if original.item_type != self.item_type and original.batches.exists():
                    raise ValidationError(
                        "O tipo do item não pode ser alterado após lotes estarem vinculados."
                    )
            except Item.DoesNotExist:
                pass

    def save(self, *args, **kwargs):
        # Ensure name defaults to model name if not explicitly set
        if not self.name and self.model:
            self.name = self.model.name

        # ITEM-01: Auto-generate SKU
        if not self.sku:
            prefix = self.tenant.subdomain[:3].upper() if self.tenant else "SOL"
            type_codes = {
                "input": "INS",
                "product": "PROD",
                "asset": "ATV",
                "consumable": "CON",
            }
            code = type_codes.get(self.item_type, "GEN")
            count = Item.objects.filter(tenant=self.tenant, item_type=self.item_type).count() + 1
            self.sku = f"{prefix}-{code}-{count:05d}"

        # ITEM-02: Auto-generate EAN-13 Barcode if not provided
        if not self.barcode:
            # Format: 200 (internal use) + tenant numeric hash (4 digits) + sequence (5 digits)
            seq = Item.objects.filter(tenant=self.tenant).count() + 1
            tenant_num = str(int(self.tenant.id.hex[:6], 16))[:4].zfill(4)
            base_12 = f"200{tenant_num}{seq:05d}"[:12].zfill(12)
            ean = EuropeanArticleNumber13(base_12)
            self.barcode = ean.get_fullcode()

        self.full_clean()
        super().save(*args, **kwargs)


class Batch(BaseModel):
    """
    A Batch represents a specific group of inventory items manufactured/acquired together.
    """
    STATUS_CHOICES = [
        ("active", "Ativo"),
        ("expired", "Expirado"),
        ("discarded", "Descartado"),
        ("depleted", "Esgotado"),
    ]

    item = models.ForeignKey(
        Item,
        on_delete=models.CASCADE,
        related_name="batches",
        verbose_name="Item",
    )
    batch_code = models.CharField(
        max_length=100,
        verbose_name="Código do Lote",
    )
    manufacture_date = models.DateField(
        verbose_name="Data de Fabricação",
    )
    expiry_date = models.DateField(
        verbose_name="Data de Validade",
    )
    total_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        verbose_name="Quantidade Total",
    )
    stock_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        verbose_name="Quantidade em Estoque",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active",
        verbose_name="Status",
    )

    class Meta:
        verbose_name = "lote"
        verbose_name_plural = "lotes"
        # Within the same tenant/item, batch code must be unique
        unique_together = ("item", "batch_code")

    def clean(self):
        super().clean()
        
        # BATCH-03: stock_quantity cannot be negative
        if self.stock_quantity < 0:
            raise ValidationError("A quantidade em estoque não pode ser negativa.")

        # ASSET-006: Mark as depleted when stock_quantity reaches zero
        if self.stock_quantity == 0 and self.status == "active":
            self.status = "depleted"

        # Check if expiration date has passed and update status to expired (BATCH-01)
        from django.utils import timezone
        if self.expiry_date and self.expiry_date < timezone.now().date():
            self.status = "expired"

    def save(self, *args, **kwargs):
        if not self.name and self.item:
            self.name = f"Lote {self.batch_code} - {self.item.name}"
        self.full_clean()
        super().save(*args, **kwargs)


class StockTransaction(BaseModel):
    """
    Represents a manual inventory stock transaction (input or output).
    Ensures that the corresponding batch inventory is updated atomically
    and never drops below zero (BATCH-03).
    """
    TRANSACTION_TYPES = [
        ("input", "Entrada"),
        ("output", "Saída"),
    ]

    tenant = models.ForeignKey(
        "core.Tenant",
        on_delete=models.CASCADE,
        related_name="stock_transactions",
    )
    batch = models.ForeignKey(
        Batch,
        on_delete=models.CASCADE,
        related_name="transactions",
        verbose_name="Lote",
    )
    transaction_type = models.CharField(
        max_length=10,
        choices=TRANSACTION_TYPES,
        verbose_name="Tipo de Movimentação",
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        verbose_name="Quantidade",
    )

    class Meta:
        verbose_name = "movimentação de estoque"
        verbose_name_plural = "movimentações de estoque"
        ordering = ["-created_at"]

    def clean(self):
        super().clean()
        if self.quantity is not None and self.quantity <= 0:
            raise ValidationError("A quantidade deve ser maior que zero.")
        if not self._state.adding:
            raise ValidationError("Movimentações de estoque não podem ser alteradas após criadas.")

    def save(self, *args, **kwargs):
        from decimal import Decimal
        from django.db import transaction as db_transaction
        
        with db_transaction.atomic():
            is_new = self._state.adding
            if is_new:
                qty = Decimal(str(self.quantity))
                # Lock da linha para evitar race conditions (BATCH-03)
                batch = Batch.objects.select_for_update().get(pk=self.batch_id)
                if self.transaction_type == "input":
                    batch.stock_quantity += qty
                elif self.transaction_type == "output":
                    if batch.stock_quantity < qty:
                        raise ValidationError(
                            f"Saldo insuficiente no lote {batch.batch_code}. Saldo disponível: {batch.stock_quantity}."
                        )
                    batch.stock_quantity -= qty
                batch.clean()
                batch.save()

                if not self.name:
                    tipo_display = "Entrada" if self.transaction_type == "input" else "Saída"
                    self.name = f"{tipo_display} - Lote {batch.batch_code} ({qty:.3f})"
                
            self.full_clean()
            super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Movimentações de estoque não podem ser excluídas para preservar a auditoria.")

