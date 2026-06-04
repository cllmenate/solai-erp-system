from django.contrib import admin
from django.shortcuts import render
from django.urls import include, path

from apps.core.billing import (
    billing_view,
    stripe_cancel,
    stripe_checkout,
    stripe_success,
    stripe_webhook,
)
from config.api import api


def landing_page(request):
    return render(request, "landing.html")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", landing_page, name="landing_page"),
    
    # Ninja API
    path("api/", api.urls),
    
    # Commercial app views
    path("commercial/", include("apps.commercial.urls")),
    
    # Stripe integration views
    path("stripe/create-checkout/", stripe_checkout, name="stripe_checkout"),
    path("stripe/success/", stripe_success, name="stripe_success"),
    path("stripe/cancel/", stripe_cancel, name="stripe_cancel"),
    path("stripe/webhook/", stripe_webhook, name="stripe_webhook"),
    
    # Billing view
    path("billing/", billing_view, name="billing_view"),
]


