from django.shortcuts import redirect
from django_otp.plugins.otp_totp.models import TOTPDevice

class Enforce2FAMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            # Bypass for URLs related to auth, 2FA, logout, static files
            path = request.path_info
            if path.startswith("/auth/") or path.startswith("/logout/") or path.startswith("/static/") or path.startswith("/media/"):
                return self.get_response(request)
            
            # Check if user has a confirmed device
            has_device = TOTPDevice.objects.filter(user=request.user, confirmed=True).exists()
            
            if has_device and not request.user.is_verified():
                return redirect(f"/auth/2fa/?next={request.path}")

        return self.get_response(request)
