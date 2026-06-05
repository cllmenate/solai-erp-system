from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.shortcuts import get_object_or_404
from ninja import Router, Schema

from apps.commercial.models import Address, Contact, Partner
from apps.core.auth import JWTAuth

router = Router(auth=JWTAuth())


# --- Schemas ---

class ContactInputSchema(Schema):
    name: str
    email: str
    phone: str
    role: str | None = None
    is_primary: bool = False


class ContactSchema(Schema):
    id: int
    name: str
    email: str
    phone: str
    role: str | None = None
    is_primary: bool


class AddressInputSchema(Schema):
    label: str
    zip_code: str
    street: str
    number: str
    complement: str | None = None
    neighborhood: str
    city: str
    state: str
    country: str = "BR"
    is_collection: bool = False
    is_delivery: bool = False


class AddressSchema(Schema):
    id: int
    label: str
    zip_code: str
    street: str
    number: str
    complement: str | None = None
    neighborhood: str
    city: str
    state: str
    country: str
    is_collection: bool
    is_delivery: bool


class PartnerInputSchema(Schema):
    is_customer: bool = False
    is_supplier: bool = False
    is_carrier: bool = False
    person_type: str = "company"
    legal_name: str
    trade_name: str | None = None
    document: str
    state_registration: str | None = None
    municipal_registration: str | None = None
    website: str | None = None
    integration_code: str | None = None
    contacts: list[ContactInputSchema]
    addresses: list[AddressInputSchema]


class PartnerSchema(Schema):
    id: UUID
    name: str
    description: str | None = None
    is_active: bool
    is_customer: bool
    is_supplier: bool
    is_carrier: bool
    person_type: str
    legal_name: str
    trade_name: str | None = None
    document: str
    state_registration: str | None = None
    municipal_registration: str | None = None
    website: str | None = None
    integration_code: str | None = None
    contacts: list[ContactSchema]
    addresses: list[AddressSchema]


class MessageSchema(Schema):
    message: str


# --- Endpoints ---

@router.get("/", response=list[PartnerSchema])
def list_partners(
    request,
    partner_type: str | None = None,
    is_active: bool | None = None,
    search: str | None = None,
):
    """
    List all partners for the current tenant.
    Filters:
    - partner_type: 'customer', 'supplier', or 'carrier'
    - is_active: True/False
    - search: matches legal_name, trade_name, or document
    """
    queryset = Partner.objects.filter(tenant=request.tenant)

    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)

    if partner_type:
        if partner_type == "customer":
            queryset = queryset.filter(is_customer=True)
        elif partner_type == "supplier":
            queryset = queryset.filter(is_supplier=True)
        elif partner_type == "carrier":
            queryset = queryset.filter(is_carrier=True)

    if search:
        queryset = queryset.filter(
            models.Q(legal_name__icontains=search)
            | models.Q(trade_name__icontains=search)
            | models.Q(document__icontains=search)
        )

    # Pre-fetch contacts and addresses to avoid N+1 queries
    queryset = queryset.prefetch_related("contacts", "addresses")
    return queryset


@router.get("/{partner_id}", response=PartnerSchema)
def get_partner(request, partner_id: UUID):
    """
    Retrieve details of a single partner.
    """
    partner = get_object_or_404(Partner, id=partner_id, tenant=request.tenant)
    return partner


@router.post("/", response={201: PartnerSchema, 400: MessageSchema})
def create_partner(request, data: PartnerInputSchema):
    """
    Create a new partner with nested contacts and addresses.
    Ensures Regra PARTNER-02 (at least 1 contact and 1 address).
    """
    if len(data.contacts) < 1:
        return 400, {"message": "Um parceiro deve ter ao menos 1 contato cadastrado."}
    if len(data.addresses) < 1:
        return 400, {"message": "Um parceiro deve ter ao menos 1 endereço cadastrado."}

    try:
        with transaction.atomic():
            partner = Partner(
                tenant=request.tenant,
                is_customer=data.is_customer,
                is_supplier=data.is_supplier,
                is_carrier=data.is_carrier,
                person_type=data.person_type,
                legal_name=data.legal_name,
                trade_name=data.trade_name,
                document=data.document,
                state_registration=data.state_registration,
                municipal_registration=data.municipal_registration,
                website=data.website,
                integration_code=data.integration_code,
                created_by=request.auth,
                updated_by=request.auth,
            )
            partner.full_clean()
            partner.save()

            for c in data.contacts:
                contact = Contact(
                    partner=partner,
                    name=c.name,
                    email=c.email,
                    phone=c.phone,
                    role=c.role,
                    is_primary=c.is_primary,
                )
                contact.full_clean()
                contact.save()

            for a in data.addresses:
                address = Address(
                    partner=partner,
                    label=a.label,
                    zip_code=a.zip_code,
                    street=a.street,
                    number=a.number,
                    complement=a.complement,
                    neighborhood=a.neighborhood,
                    city=a.city,
                    state=a.state,
                    country=a.country,
                    is_collection=a.is_collection,
                    is_delivery=a.is_delivery,
                )
                address.full_clean()
                address.save()

            return 201, partner

    except ValidationError as e:
        return 400, {"message": f"Erro de validação: {dict(e.message_dict) if hasattr(e, 'message_dict') else e.messages}"}
    except Exception as e:
        return 400, {"message": f"Erro ao criar parceiro: {str(e)}"}


@router.put("/{partner_id}", response={200: PartnerSchema, 400: MessageSchema})
def update_partner(request, partner_id: UUID, data: PartnerInputSchema):
    """
    Update an existing partner, replacing its contacts and addresses.
    Ensures Regra PARTNER-02 (at least 1 contact and 1 address).
    """
    if len(data.contacts) < 1:
        return 400, {"message": "Um parceiro deve ter ao menos 1 contato cadastrado."}
    if len(data.addresses) < 1:
        return 400, {"message": "Um parceiro deve ter ao menos 1 endereço cadastrado."}

    partner = get_object_or_404(Partner, id=partner_id, tenant=request.tenant)

    try:
        with transaction.atomic():
            partner.is_customer = data.is_customer
            partner.is_supplier = data.is_supplier
            partner.is_carrier = data.is_carrier
            partner.person_type = data.person_type
            partner.legal_name = data.legal_name
            partner.trade_name = data.trade_name
            partner.document = data.document
            partner.state_registration = data.state_registration
            partner.municipal_registration = data.municipal_registration
            partner.website = data.website
            partner.integration_code = data.integration_code
            partner.updated_by = request.auth

            partner.full_clean()
            partner.save()

            # Replace contacts
            partner.contacts.all().delete()
            for c in data.contacts:
                contact = Contact(
                    partner=partner,
                    name=c.name,
                    email=c.email,
                    phone=c.phone,
                    role=c.role,
                    is_primary=c.is_primary,
                )
                contact.full_clean()
                contact.save()

            # Replace addresses
            partner.addresses.all().delete()
            for a in data.addresses:
                address = Address(
                    partner=partner,
                    label=a.label,
                    zip_code=a.zip_code,
                    street=a.street,
                    number=a.number,
                    complement=a.complement,
                    neighborhood=a.neighborhood,
                    city=a.city,
                    state=a.state,
                    country=a.country,
                    is_collection=a.is_collection,
                    is_delivery=a.is_delivery,
                )
                address.full_clean()
                address.save()

            return 200, partner

    except ValidationError as e:
        return 400, {"message": f"Erro de validação: {dict(e.message_dict) if hasattr(e, 'message_dict') else e.messages}"}
    except Exception as e:
        return 400, {"message": f"Erro ao atualizar parceiro: {str(e)}"}


@router.delete("/{partner_id}", response={200: MessageSchema, 400: MessageSchema})
def delete_partner(request, partner_id: UUID):
    """
    Deactivate or hard delete a partner.
    For audit integrity, we set is_active=False.
    """
    partner = get_object_or_404(Partner, id=partner_id, tenant=request.tenant)
    partner.is_active = False
    partner.save()
    return 200, {"message": "Parceiro desativado com sucesso."}
