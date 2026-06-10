from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.core.models import Role, Sector, Tenant, User, UserPreferences


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("company_name", "trade_name", "cnpj", "subdomain", "plan", "trial_ends_at", "is_active")
    list_filter = ("plan", "is_active", "created_at")
    search_fields = ("company_name", "trade_name", "cnpj", "subdomain")
    ordering = ("-created_at",)


@admin.register(Sector)
class SectorAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "is_active", "created_at")
    list_filter = ("tenant", "is_active", "created_at")
    search_fields = ("name", "tenant__company_name", "tenant__subdomain")
    ordering = ("tenant", "name")


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "sector", "level", "is_active")
    list_filter = ("tenant", "sector", "is_active")
    search_fields = ("name", "tenant__company_name", "description")
    ordering = ("tenant", "-level", "name")


class UserPreferencesInline(admin.StackedInline):
    model = UserPreferences
    can_delete = False
    verbose_name_plural = "preferências"


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("username", "email", "full_name", "tenant", "role", "is_active", "is_staff")
    list_filter = ("tenant", "is_active", "is_staff", "created_at")
    search_fields = ("username", "email", "full_name", "tenant__company_name")
    ordering = ("tenant", "username")
    inlines = [UserPreferencesInline]


@admin.register(UserPreferences)
class UserPreferencesAdmin(admin.ModelAdmin):
    list_display = ("user", "dark_mode", "sidebar_compact", "visual_theme")
    list_filter = ("dark_mode", "sidebar_compact", "visual_theme")
    search_fields = ("user__username", "user__email")
