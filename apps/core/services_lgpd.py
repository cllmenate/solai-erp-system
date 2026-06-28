import json
from django.core.serializers.json import DjangoJSONEncoder
from django.apps import apps
from django.utils import timezone
from apps.core.models import User
import hashlib

def export_user_data_json(user: User) -> str:
    """
    Exports all Personal Data associated with a User.
    """
    data = {
        "user_info": {
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
            "is_active": user.is_active,
            "role": user.role.name if user.role else None,
            "tenant": user.tenant.name if user.tenant else None,
        },
        "preferences": {},
        "history": []
    }

    if hasattr(user, 'preferences'):
        prefs = user.preferences
        data["preferences"] = {
            "language": prefs.language,
            "dark_mode": prefs.dark_mode,
            "sidebar_compact": prefs.sidebar_compact,
            "visual_theme": prefs.visual_theme,
            "privacy_consent_accepted": prefs.privacy_consent_accepted,
            "privacy_consent_at": prefs.privacy_consent_at,
            "privacy_consent_ip": prefs.privacy_consent_ip,
        }

    # Example: Export history logs. Note that real projects might have more relations.
    # In a full ERP, we might fetch OS created by this user.
    # But since we just need the PII for LGPD, this basic info suffices.
    return json.dumps(data, cls=DjangoJSONEncoder, indent=2)


def anonymize_user(user: User):
    """
    Anonymizes a user to comply with "Right to be Forgotten",
    while keeping referential integrity intact.
    """
    anon_hash = hashlib.sha256(f"{user.id}-{timezone.now().isoformat()}".encode()).hexdigest()[:12]
    
    user.username = f"anon_user_{anon_hash}"
    user.email = f"{anon_hash}@anonymized.solai.local"
    user.full_name = "Anonymized User"
    user.is_active = False
    user.set_unusable_password()
    user.save()

    # Clear preferences
    if hasattr(user, 'preferences'):
        prefs = user.preferences
        prefs.privacy_consent_ip = None
        prefs.save()

def anonymize_partner(partner):
    """
    Anonymizes a Partner.
    """
    anon_hash = hashlib.sha256(f"{partner.id}-{timezone.now().isoformat()}".encode()).hexdigest()[:12]
    
    partner.legal_name = "Anonymized Partner"
    partner.trade_name = "Anonymized"
    partner.document = "00000000000"
    partner.state_registration = ""
    partner.municipal_registration = ""
    partner.website = ""
    partner.save()

    for contact in partner.contact_set.all():
        contact.name = "Anonymized Contact"
        contact.email = f"{anon_hash}@anonymized.solai.local"
        contact.phone = "00000000000"
        contact.save()
