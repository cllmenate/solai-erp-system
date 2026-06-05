from django.contrib.auth import get_user_model
from ninja.security import HttpBearer

from shared.utils.jwt import decode_jwt_token


class JWTAuth(HttpBearer):
    """
    Django Ninja authentication class that validates a JWT token
    from the Authorization Bearer header.
    """
    def authenticate(self, request, token):
        payload = decode_jwt_token(token)
        if not payload:
            return None
        
        user_id = payload.get("user_id")
        if not user_id:
            return None
            
        user_model = get_user_model()
        try:
            user = user_model.objects.get(id=user_id, is_active=True)
            return user
        except user_model.DoesNotExist:
            return None
