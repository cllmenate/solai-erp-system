from datetime import timedelta

import pytest
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.cache import cache
from django.http import JsonResponse
from django.test import RequestFactory
from django.utils import timezone

from apps.core.models import Tenant
from shared.middleware.ratelimit import RateLimitMiddleware


@pytest.mark.django_db
class TestRateLimiting:
    def setup_method(self):
        cache.clear()
        self.factory = RequestFactory()
        self.tenant = Tenant.objects.create(
            company_name="Rate Limit Company",
            trade_name="RL Company",
            cnpj="99.999.999/0001-99",
            subdomain="ratelimit",
            schema_name="tenant_ratelimit",
            trial_ends_at=timezone.now() + timedelta(days=14),
        )

    def test_login_rate_limiting(self):
        from django.contrib.auth.models import AnonymousUser
        # Setup middleware
        def get_response(request):
            return JsonResponse({"status": "ok"})
        
        middleware = RateLimitMiddleware(get_response)
        
        # Make 5 failed POST requests
        for _ in range(5):
            request = self.factory.post("/auth/login/", {"username_or_email": "attacker", "password": "wrongpassword"})
            request.user = AnonymousUser()
            # Add session and messages support for middleware/views
            request.session = {}
            messages = FallbackStorage(request)
            request._messages = messages
            
            response = middleware(request)
            assert response.status_code == 200  # The mock view returns 200

        # The 6th request should be rate limited
        request = self.factory.post("/auth/login/", {"username_or_email": "attacker", "password": "wrongpassword"})
        request.user = AnonymousUser()
        request.session = {}
        messages = FallbackStorage(request)
        request._messages = messages
        
        response = middleware(request)
        assert response.status_code == 429

    def test_api_rate_limiting_per_tenant(self):
        def get_response(request):
            return JsonResponse({"status": "ok"})
        
        middleware = RateLimitMiddleware(get_response)
        
        # Make 100 requests to API
        for _ in range(100):
            request = self.factory.get("/api/items")
            request.tenant = self.tenant
            response = middleware(request)
            assert response.status_code == 200

        # The 101st request should be rate limited
        request = self.factory.get("/api/items")
        request.tenant = self.tenant
        response = middleware(request)
        assert response.status_code == 429
