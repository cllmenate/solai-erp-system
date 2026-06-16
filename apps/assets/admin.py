from django.contrib import admin

from apps.assets.models import Batch, Brand, Category, Item, Model, TechSheetTemplate


class BatchInline(admin.TabularInline):
    model = Batch
    extra = 1
    fk_name = "item"


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "website", "is_active")
    list_filter = ("tenant", "is_active")
    search_fields = ("name", "tenant__company_name", "tenant__subdomain")
    ordering = ("tenant", "name")


@admin.register(TechSheetTemplate)
class TechSheetTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "template_type", "is_active")
    list_filter = ("tenant", "template_type", "is_active")
    search_fields = ("name", "tenant__company_name", "tenant__subdomain")
    ordering = ("tenant", "name")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "parent", "is_active")
    list_filter = ("tenant", "is_active")
    search_fields = ("name", "parent__name", "tenant__company_name", "tenant__subdomain")
    ordering = ("tenant", "name")
    filter_horizontal = ("tech_sheet_templates",)


@admin.register(Model)
class ModelAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "brand", "unit_of_measure", "weight", "is_active")
    list_filter = ("tenant", "brand", "is_active")
    search_fields = ("name", "brand__name", "tenant__company_name", "tenant__subdomain")
    ordering = ("tenant", "name")
    filter_horizontal = ("categories", "tech_sheet_templates")


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "barcode", "item_type", "model", "tenant", "is_active")
    list_filter = ("tenant", "item_type", "is_active")
    search_fields = (
        "name",
        "sku",
        "barcode",
        "serial_number",
        "model__name",
        "tenant__company_name",
        "tenant__subdomain",
    )
    ordering = ("tenant", "sku")
    inlines = [BatchInline]


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = (
        "batch_code",
        "item",
        "status",
        "manufacture_date",
        "expiry_date",
        "stock_quantity",
        "total_quantity",
        "is_active",
    )
    list_filter = ("status", "item__tenant", "manufacture_date", "expiry_date", "is_active")
    search_fields = (
        "batch_code",
        "item__name",
        "item__sku",
        "item__tenant__company_name",
        "item__tenant__subdomain",
    )
    ordering = ("item__tenant", "expiry_date", "batch_code")
