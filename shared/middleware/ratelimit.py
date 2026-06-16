from django.contrib import messages
from django.contrib.auth.signals import user_logged_in
from django.core.cache import cache
from django.dispatch import receiver
from django.http import JsonResponse
from django.shortcuts import render


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

class RateLimitMiddleware:
    """
    Middleware to implement rate limiting:
    1. Login POST attempts (AUTH-003): Max 5 attempts per 15 minutes per IP + username.
    2. API requests (SEC-005): Max 100 requests per minute per Tenant.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        
        # 1. Login Rate Limit (AUTH-003): 5 attempts / 15 minutes
        if path == "/auth/login/" and request.method == "POST":
            username = request.POST.get("username_or_email", "").strip()
            ip = get_client_ip(request)
            key = f"ratelimit:login:{ip}:{username}"
            
            count = cache.get(key, 0)
            if count >= 5:
                accept = request.headers.get("accept", "")
                if "application/json" in accept or request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return JsonResponse(
                        {"error": "Muitas tentativas de login. Por favor, tente novamente em 15 minutos."},
                        status=429
                    )
                
                messages.error(request, "Muitas tentativas de login. Por favor, tente novamente em 15 minutos.")
                response = render(request, "core/login.html", status=429)
                return response
            
            # Increment attempt counter
            if count == 0:
                cache.set(key, 1, 900)  # 15 minutes = 900 seconds
            else:
                try:
                    cache.incr(key)
                except ValueError:
                    cache.set(key, 1, 900)

        # 2. API Rate Limit (SEC-005): per Tenant (100 requests / minute)
        elif path.startswith("/api/"):
            tenant = getattr(request, "tenant", None)
            if tenant:
                key = f"ratelimit:api:{tenant.id}"
                limit = 100  # 100 requests
                period = 60  # 1 minute
                
                count = cache.get(key, 0)
                if count >= limit:
                    return JsonResponse(
                        {"error": "Rate limit exceeded. Too many requests. Please try again later."},
                        status=429
                    )
                
                if count == 0:
                    cache.set(key, 1, period)
                else:
                    try:
                        cache.incr(key)
                    except ValueError:
                        cache.set(key, 1, period)

        return self.get_response(request)

# Signal receiver to clear failed login attempts counter on successful login
@receiver(user_logged_in)
def reset_login_limit(sender, request, user, **kwargs):
    username = request.POST.get("username_or_email", "").strip()
    ip = get_client_ip(request)
    key = f"ratelimit:login:{ip}:{username}"
    cache.delete(key)
