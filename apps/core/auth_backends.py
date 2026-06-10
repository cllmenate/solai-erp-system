from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailOrUsernameBackend(ModelBackend):
    """
    Custom authentication backend that allows users to log in using either their
    username or their email address.
    It respects the current PostgreSQL search path schema context.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        user_model = get_user_model()
        if username is None:
            username = kwargs.get(user_model.USERNAME_FIELD)

        tenant = kwargs.get("tenant") or getattr(request, "tenant", None)

        try:
            # Try to fetch user by email first, fallback to username
            if "@" in username:
                user = user_model.objects.get(email=username, tenant=tenant)
            else:
                user = user_model.objects.get(username=username, tenant=tenant)
        except user_model.DoesNotExist:
            # Run the default password hasher once to mitigate timing attacks
            user_model().set_password(password)
            return None
        except user_model.MultipleObjectsReturned:
            # Should not happen because (tenant, username) and (tenant, email) are unique
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None


class RolePermissionBackend:
    """
    Checks permissions assigned to the custom User.role (which inherits from Group).
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        return None

    def get_user(self, user_id):
        return None

    def has_perm(self, user_obj, perm, obj=None):
        if not user_obj.is_active or user_obj.is_anonymous:
            return False
        if user_obj.is_superuser:
            return True
        if not hasattr(user_obj, "role") or not user_obj.role:
            return False
        if not getattr(user_obj.role, "is_active", True):
            return False

        try:
            app_label, codename = perm.split(".")
        except ValueError:
            return False

        return user_obj.role.permissions.filter(
            content_type__app_label=app_label, codename=codename
        ).exists()

    def get_all_permissions(self, user_obj, obj=None):
        if not user_obj.is_active or user_obj.is_anonymous:
            return set()
        if not hasattr(user_obj, "role") or not user_obj.role:
            return set()
        if not getattr(user_obj.role, "is_active", True):
            return set()

        perms = user_obj.role.permissions.select_related("content_type")
        return {f"{p.content_type.app_label}.{p.codename}" for p in perms}

    def has_module_perms(self, user_obj, app_label):
        if not user_obj.is_active or user_obj.is_anonymous:
            return False
        if user_obj.is_superuser:
            return True
        if not hasattr(user_obj, "role") or not user_obj.role:
            return False
        if not getattr(user_obj.role, "is_active", True):
            return False
        return user_obj.role.permissions.filter(
            content_type__app_label=app_label
        ).exists()

