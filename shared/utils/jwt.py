import datetime
import jwt
from django.conf import settings


def generate_jwt_token(user, tenant_id=None):
    """
    Generates a JWT token for the given user containing tenant_id, user_id, and role_id in the payload.
    """
    now = datetime.datetime.now(datetime.UTC)
    payload = {
        "user_id": str(user.id),
        "username": user.username,
        "email": user.email,
        "role_id": str(user.role.id) if user.role else None,
        "tenant_id": str(tenant_id or user.tenant_id or ""),
        "exp": now + datetime.timedelta(hours=24),
        "iat": now,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def decode_jwt_token(token):
    """
    Decodes the JWT token and returns the payload.
    """
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
