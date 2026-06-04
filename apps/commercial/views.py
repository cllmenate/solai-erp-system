
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from apps.commercial.models import Address, Contact, Partner


@login_required
def partner_list_view(request):
    """
    Renders list of partners for the active tenant.
    Supports basic searching and filtering.
    """
    search_query = request.GET.get("search", "")
    partner_type = request.GET.get("type", "")
    
    queryset = Partner.objects.filter(tenant=request.tenant, is_active=True)
    
    if search_query:
        queryset = queryset.filter(
            legal_name__icontains=search_query) | queryset.filter(
            trade_name__icontains=search_query) | queryset.filter(
            document__icontains=search_query)
            
    if partner_type:
        if partner_type == "customer":
            queryset = queryset.filter(is_customer=True)
        elif partner_type == "supplier":
            queryset = queryset.filter(is_supplier=True)
        elif partner_type == "carrier":
            queryset = queryset.filter(is_carrier=True)

    queryset = queryset.order_by("-created_at")
    
    context = {
        "partners": queryset,
        "search_query": search_query,
        "partner_type": partner_type,
    }
    return render(request, "commercial/partner_list.html", context)


@login_required
def partner_detail_view(request, pk):
    """
    Renders partner details with contacts and addresses.
    """
    partner = get_object_or_404(Partner, id=pk, tenant=request.tenant)
    return render(request, "commercial/partner_detail.html", {"partner": partner})


@login_required
def partner_create_view(request):
    """
    Handles rendering and processing partner creation.
    Requires at least 1 contact and 1 address (Regra PARTNER-02).
    """
    if request.method == "POST":
        is_customer = request.POST.get("is_customer") == "on"
        is_supplier = request.POST.get("is_supplier") == "on"
        is_carrier = request.POST.get("is_carrier") == "on"
        person_type = request.POST.get("person_type", "company")
        legal_name = request.POST.get("legal_name")
        trade_name = request.POST.get("trade_name")
        document = request.POST.get("document")
        state_registration = request.POST.get("state_registration")
        municipal_registration = request.POST.get("municipal_registration")
        website = request.POST.get("website")
        integration_code = request.POST.get("integration_code")

        # Parse contacts lists from POST arrays
        contact_names = request.POST.getlist("contact_name[]")
        contact_emails = request.POST.getlist("contact_email[]")
        contact_phones = request.POST.getlist("contact_phone[]")
        contact_roles = request.POST.getlist("contact_role[]")
        contact_primaries = request.POST.getlist("contact_is_primary[]")

        # Parse addresses lists from POST arrays
        addr_labels = request.POST.getlist("address_label[]")
        addr_zips = request.POST.getlist("address_zip_code[]")
        addr_streets = request.POST.getlist("address_street[]")
        addr_numbers = request.POST.getlist("address_number[]")
        addr_complements = request.POST.getlist("address_complement[]")
        addr_neighborhoods = request.POST.getlist("address_neighborhood[]")
        addr_cities = request.POST.getlist("address_city[]")
        addr_states = request.POST.getlist("address_state[]")
        addr_collections = request.POST.getlist("address_is_collection[]")
        addr_deliveries = request.POST.getlist("address_is_delivery[]")

        # Enforce Rule PARTNER-02
        if len(contact_names) == 0:
            messages.error(request, "Um parceiro deve ter ao menos 1 contato cadastrado.")
            return render(request, "commercial/partner_form.html", {"partner": None})
        if len(addr_labels) == 0:
            messages.error(request, "Um parceiro deve ter ao menos 1 endereço cadastrado.")
            return render(request, "commercial/partner_form.html", {"partner": None})

        try:
            with transaction.atomic():
                partner = Partner.objects.create(
                    tenant=request.tenant,
                    is_customer=is_customer,
                    is_supplier=is_supplier,
                    is_carrier=is_carrier,
                    person_type=person_type,
                    legal_name=legal_name,
                    trade_name=trade_name,
                    document=document,
                    state_registration=state_registration,
                    municipal_registration=municipal_registration,
                    website=website,
                    integration_code=integration_code,
                    created_by=request.user,
                    updated_by=request.user,
                )

                # Insert contacts
                for i in range(len(contact_names)):
                    # Check if marked as primary
                    is_primary = False
                    if str(i) in contact_primaries:
                        is_primary = True
                    Contact.objects.create(
                        partner=partner,
                        name=contact_names[i],
                        email=contact_emails[i],
                        phone=contact_phones[i],
                        role=contact_roles[i],
                        is_primary=is_primary
                    )

                # Insert addresses
                for j in range(len(addr_labels)):
                    is_coll = False
                    if str(j) in addr_collections:
                        is_coll = True
                    is_del = False
                    if str(j) in addr_deliveries:
                        is_del = True
                    Address.objects.create(
                        partner=partner,
                        label=addr_labels[j],
                        zip_code=addr_zips[j],
                        street=addr_streets[j],
                        number=addr_numbers[j],
                        complement=addr_complements[j],
                        neighborhood=addr_neighborhoods[j],
                        city=addr_cities[j],
                        state=addr_states[j],
                        is_collection=is_coll,
                        is_delivery=is_del
                    )

                messages.success(request, f"Parceiro '{partner.name}' cadastrado com sucesso.")
                return redirect("partner_detail", pk=partner.id)

        except ValidationError as e:
            msg = dict(e.message_dict) if hasattr(e, "message_dict") else e.messages
            messages.error(request, f"Erro de validação: {msg}")
        except Exception as e:
            messages.error(request, f"Erro ao criar parceiro: {str(e)}")

    return render(request, "commercial/partner_form.html", {"partner": None})


@login_required
def partner_update_view(request, pk):
    """
    Handles editing an existing partner, replacing its contacts/addresses.
    """
    partner = get_object_or_404(Partner, id=pk, tenant=request.tenant)
    
    if request.method == "POST":
        is_customer = request.POST.get("is_customer") == "on"
        is_supplier = request.POST.get("is_supplier") == "on"
        is_carrier = request.POST.get("is_carrier") == "on"
        person_type = request.POST.get("person_type", "company")
        legal_name = request.POST.get("legal_name")
        trade_name = request.POST.get("trade_name")
        document = request.POST.get("document")
        state_registration = request.POST.get("state_registration")
        municipal_registration = request.POST.get("municipal_registration")
        website = request.POST.get("website")
        integration_code = request.POST.get("integration_code")

        # Parse contacts
        contact_names = request.POST.getlist("contact_name[]")
        contact_emails = request.POST.getlist("contact_email[]")
        contact_phones = request.POST.getlist("contact_phone[]")
        contact_roles = request.POST.getlist("contact_role[]")
        contact_primaries = request.POST.getlist("contact_is_primary[]")

        # Parse addresses
        addr_labels = request.POST.getlist("address_label[]")
        addr_zips = request.POST.getlist("address_zip_code[]")
        addr_streets = request.POST.getlist("address_street[]")
        addr_numbers = request.POST.getlist("address_number[]")
        addr_complements = request.POST.getlist("address_complement[]")
        addr_neighborhoods = request.POST.getlist("address_neighborhood[]")
        addr_cities = request.POST.getlist("address_city[]")
        addr_states = request.POST.getlist("address_state[]")
        addr_collections = request.POST.getlist("address_is_collection[]")
        addr_deliveries = request.POST.getlist("address_is_delivery[]")

        if len(contact_names) == 0:
            messages.error(request, "Um parceiro deve ter ao menos 1 contato cadastrado.")
            return render(request, "commercial/partner_form.html", {"partner": partner})
        if len(addr_labels) == 0:
            messages.error(request, "Um parceiro deve ter ao menos 1 endereço cadastrado.")
            return render(request, "commercial/partner_form.html", {"partner": partner})

        try:
            with transaction.atomic():
                partner.is_customer = is_customer
                partner.is_supplier = is_supplier
                partner.is_carrier = is_carrier
                partner.person_type = person_type
                partner.legal_name = legal_name
                partner.trade_name = trade_name
                partner.document = document
                partner.state_registration = state_registration
                partner.municipal_registration = municipal_registration
                partner.website = website
                partner.integration_code = integration_code
                partner.updated_by = request.user
                partner.save()

                # Recreate contacts
                partner.contacts.all().delete()
                for i in range(len(contact_names)):
                    is_primary = False
                    if str(i) in contact_primaries:
                        is_primary = True
                    Contact.objects.create(
                        partner=partner,
                        name=contact_names[i],
                        email=contact_emails[i],
                        phone=contact_phones[i],
                        role=contact_roles[i],
                        is_primary=is_primary
                    )

                # Recreate addresses
                partner.addresses.all().delete()
                for j in range(len(addr_labels)):
                    is_coll = False
                    if str(j) in addr_collections:
                        is_coll = True
                    is_del = False
                    if str(j) in addr_deliveries:
                        is_del = True
                    Address.objects.create(
                        partner=partner,
                        label=addr_labels[j],
                        zip_code=addr_zips[j],
                        street=addr_streets[j],
                        number=addr_numbers[j],
                        complement=addr_complements[j],
                        neighborhood=addr_neighborhoods[j],
                        city=addr_cities[j],
                        state=addr_states[j],
                        is_collection=is_coll,
                        is_delivery=is_del
                    )

                messages.success(request, f"Parceiro '{partner.name}' atualizado com sucesso.")
                return redirect("partner_detail", pk=partner.id)

        except ValidationError as e:
            msg = dict(e.message_dict) if hasattr(e, "message_dict") else e.messages
            messages.error(request, f"Erro de validação: {msg}")
        except Exception as e:
            messages.error(request, f"Erro ao atualizar parceiro: {str(e)}")

    return render(request, "commercial/partner_form.html", {"partner": partner})


@login_required
def partner_delete_view(request, pk):
    """
    Deactivates a partner (sets is_active=False).
    """
    partner = get_object_or_404(Partner, id=pk, tenant=request.tenant)
    partner.is_active = False
    partner.save()
    messages.success(request, f"Parceiro '{partner.name}' desativado com sucesso.")
    return redirect("partner_list")


# --- HTMX Partials ---

@login_required
def htmx_contact_row(request):
    """
    Returns an empty contact form partial view for HTMX injection.
    """
    index = request.GET.get("index", "0")
    return render(request, "commercial/partials/contact_row.html", {"index": index})


@login_required
def htmx_address_row(request):
    """
    Returns an empty address form partial view for HTMX injection.
    """
    index = request.GET.get("index", "0")
    return render(request, "commercial/partials/address_row.html", {"index": index})
