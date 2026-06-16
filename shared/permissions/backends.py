
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
