from django.contrib import admin

from apps.commercial.models import Address, Contact, Partner


class ContactInline(admin.TabularInline):
    model = Contact
    extra = 1


class AddressInline(admin.TabularInline):
    model = Address
    extra = 1


@admin.register(Partner)
class PartnerAdmin(admin.ModelAdmin):
    list_display = (
        "trade_name",
        "legal_name",
        "document",
        "tenant",
        "is_customer",
        "is_supplier",
        "is_carrier",
        "is_active",
    )
    list_filter = (
        "tenant",
        "is_customer",
        "is_supplier",
        "is_carrier",
        "person_type",
        "is_active",
    )
    search_fields = ("legal_name", "trade_name", "document", "tenant__company_name")
    inlines = [ContactInline, AddressInline]
    ordering = ("tenant", "trade_name")


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "phone", "partner", "is_primary")
    list_filter = ("is_primary", "partner__tenant")
    search_fields = ("name", "email", "phone", "partner__legal_name", "partner__trade_name")
    ordering = ("partner", "name")


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("label", "partner", "city", "state", "is_collection", "is_delivery")
    list_filter = ("state", "is_collection", "is_delivery", "partner__tenant")
    search_fields = ("zip_code", "street", "city", "partner__legal_name", "partner__trade_name")
    ordering = ("partner", "label")
