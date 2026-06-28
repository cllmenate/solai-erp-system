import os
from django.conf import settings
from django.db import models
from cryptography.fernet import Fernet

def get_fernet():
    key = getattr(settings, "CRYPTOGRAPHY_KEY", None)
    if not key:
        # Fallback to secret key if CRYPTOGRAPHY_KEY is not defined
        from django.utils.crypto import get_random_string
        import base64
        secret = settings.SECRET_KEY[:32].encode('utf-8')
        # Need exactly 32 bytes url-safe base64 encoded for Fernet
        key = base64.urlsafe_b64encode(secret.ljust(32, b' '))
    return Fernet(key)

class EncryptedCharField(models.CharField):
    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        try:
            return get_fernet().decrypt(value.encode('utf-8')).decode('utf-8')
        except Exception:
            return value

    def get_prep_value(self, value):
        if value is None:
            return value
        # Ensure it's not already encrypted (naive check)
        if isinstance(value, str) and value.startswith('gAAAAA'):
            return value
        return get_fernet().encrypt(str(value).encode('utf-8')).decode('utf-8')

class EncryptedEmailField(models.EmailField, EncryptedCharField):
    pass
