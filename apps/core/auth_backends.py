from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db import connection


class EmailOrUsernameBackend(ModelBackend):
    """
    Custom authentication backend that allows users to log in using either their
    username or their email address.
    It respects the current PostgreSQL search path schema context.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)

        try:
            # Try to fetch user by email first, fallback to username
            if "@" in username:
                user = UserModel.objects.get(email=username)
            else:
                user = UserModel.objects.get(username=username)
        except UserModel.DoesNotExist:
            # Run the default password hasher hasher once to mitigate timing attacks
            UserModel().set_password(password)
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
