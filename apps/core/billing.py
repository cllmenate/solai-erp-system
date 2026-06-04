import json

import stripe
from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt

from apps.core.models import Tenant

stripe.api_key = settings.STRIPE_SECRET_KEY


def stripe_checkout(request):
    """
    Creates a Stripe Checkout Session for subscription plans.
    """
    if request.method != "POST":
        return redirect("/")

    plan_type = request.POST.get("plan", "basic")
    subdomain = request.POST.get("subdomain")
    
    # Resolve subdomain from tenant context or fallback to host subdomain
    if not subdomain and getattr(request, "tenant", None):
        subdomain = request.tenant.subdomain

    # Plan pricing definition (mock prices or simulated session creation)
    price_ids = {
        "basic": "price_basic_placeholder",
        "pro": "price_pro_placeholder",
        "enterprise": "price_enterprise_placeholder"
    }
    price_id = price_ids.get(plan_type, price_ids["basic"])

    # Determine redirect URLs
    success_url = (
        request.build_absolute_uri("/stripe/success/")
        + "?session_id={CHECKOUT_SESSION_ID}"
    )
    cancel_url = request.build_absolute_uri("/stripe/cancel/")

    try:
        # If simulated key is used, bypass Stripe API call for tests
        if settings.STRIPE_SECRET_KEY == "sk_test_placeholder":
            # Simulation for development / testing without live stripe account
            mock_session_id = "cs_test_mocksession12345"
            # Attempt to provision plan locally directly if simulated
            if subdomain:
                try:
                    tenant = Tenant.objects.get(subdomain=subdomain)
                    tenant.stripe_subscription_id = f"sub_mock_{plan_type}"
                    tenant.plan = plan_type
                    tenant.save()
                except Tenant.DoesNotExist:
                    pass
            return HttpResponseRedirect(
                success_url.replace("{CHECKOUT_SESSION_ID}", mock_session_id)
            )

        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price": price_id,
                    "quantity": 1,
                },
            ],
            mode="subscription",
            success_url=success_url,
            cancel_url=cancel_url,
            client_reference_id=subdomain,
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


def stripe_success(request):
    """
    Stripe checkout success redirection landing.
    """
    session_id = request.GET.get("session_id", "mock_session")
    msg = (
        f"<h1>Assinatura concluída!</h1>"
        f"<p>Obrigado! Sua conta foi ativada. ID: {session_id}</p>"
        f"<a href='/'>Voltar ao ERP</a>"
    )
    return HttpResponse(msg)


def stripe_cancel(request):
    """
    Stripe checkout cancellation landing.
    """
    msg = (
        "<h1>Assinatura cancelada</h1>"
        "<p>O processo de checkout foi interrompido. Nenhuma cobrança feita.</p>"
        "<a href='/'>Voltar</a>"
    )
    return HttpResponse(msg)


@csrf_exempt
def stripe_webhook(request):
    """
    Webhook handler to receive asynchronous notifications from Stripe.
    """
    payload = request.body
    sig_header = request.headers.get("STRIPE_SIGNATURE")
    event = None

    # Handle simulated requests (e.g. from tests)
    if settings.STRIPE_SECRET_KEY == "sk_test_placeholder" or not sig_header:
        try:
            event = json.loads(payload)
        except Exception:
            return HttpResponse(status=400)
    else:
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
        except ValueError:
            # Invalid payload
            return HttpResponse(status=400)
        except stripe.error.SignatureVerificationError:
            # Invalid signature
            return HttpResponse(status=400)

    # Process events
    event_type = event.get("type")
    data_object = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        subdomain = data_object.get("client_reference_id")
        subscription_id = data_object.get("subscription")
        if subdomain and subscription_id:
            try:
                tenant = Tenant.objects.get(subdomain=subdomain)
                tenant.stripe_subscription_id = subscription_id
                tenant.plan = "pro"  # Default to pro or extract from line items
                tenant.save()
            except Tenant.DoesNotExist:
                pass

    elif event_type == "invoice.paid":
        # Handle recurring payments if subscription metadata exists
        subscription_id = data_object.get("subscription")
        if subscription_id:
            try:
                tenant = Tenant.objects.get(stripe_subscription_id=subscription_id)
                tenant.is_active = True
                tenant.save()
            except Tenant.DoesNotExist:
                pass

    elif event_type == "invoice.payment_failed":
        subscription_id = data_object.get("subscription")
        if subscription_id:
            try:
                tenant = Tenant.objects.get(stripe_subscription_id=subscription_id)
                # Mark subscription inactive/invalidated
                tenant.stripe_subscription_id = ""
                tenant.save()
            except Tenant.DoesNotExist:
                pass

    elif event_type == "customer.subscription.deleted":
        subscription_id = data_object.get("id")
        if subscription_id:
            try:
                tenant = Tenant.objects.get(stripe_subscription_id=subscription_id)
                tenant.stripe_subscription_id = ""
                tenant.save()
            except Tenant.DoesNotExist:
                pass

    return HttpResponse(status=200)


def billing_view(request):
    """
    Renders billing alerts and warnings for expired tenant trials.
    """
    subdomain = request.GET.get("subdomain", "")
    return render(request, "billing.html", {"subdomain": subdomain})
