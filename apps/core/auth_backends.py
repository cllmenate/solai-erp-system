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


