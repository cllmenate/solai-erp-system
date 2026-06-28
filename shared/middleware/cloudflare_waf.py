from django.http import HttpResponseForbidden
from django.conf import settings

class CloudflareWAFMiddleware:
    """
    Ensures that requests are coming through Cloudflare by checking
    specific Cloudflare headers or verifying IP ranges.
    
    In a real production environment, you should verify the connecting IP 
    against Cloudflare's published IP list: https://www.cloudflare.com/ips/
    For this implementation, we check for the CF-Connecting-IP header if 
    CLOUDFLARE_WAF_ENABLED is True in settings.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.enabled = getattr(settings, 'CLOUDFLARE_WAF_ENABLED', False)

    def __call__(self, request):
        if self.enabled:
            # Simplistic check. In prod, better to drop traffic at NGINX level or validate IPs.
            if 'HTTP_CF_CONNECTING_IP' not in request.META:
                return HttpResponseForbidden("Direct access not allowed. Please connect via Cloudflare.")
        
        response = self.get_response(request)
        return response
