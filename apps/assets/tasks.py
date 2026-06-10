import logging
from datetime import timedelta

from celery import shared_task
from django.core.mail import send_mail
from django.utils import timezone

from apps.assets.models import Batch
from apps.core.models import Tenant, User
from shared.middleware.tenant import set_tenant_schema

logger = logging.getLogger(__name__)


@shared_task
def check_expired_batches():
    """
    Task that checks all active tenants for expired and expiring batches.
    - Marks batches as expired if their expiration date has passed.
    - Sends an email alert to the tenant's stock operators/admins.
    """
    today = timezone.now().date()
    tenants = Tenant.objects.filter(is_active=True)
    processed_count = 0

    for tenant in tenants:
        try:
            # Switch PostgreSQL search path to the tenant's schema
            set_tenant_schema(tenant.schema_name)

            # 1. Identify and mark expired batches
            expired_batches = list(
                Batch.objects.filter(
                    item__tenant=tenant, status="active", expiry_date__lt=today
                ).select_related("item", "item__model")
            )

            marked_expired_count = 0
            for batch in expired_batches:
                batch.status = "expired"
                batch.save()
                marked_expired_count += 1

            # 2. Identify batches expiring within 7 days
            expiring_batches = list(
                Batch.objects.filter(
                    item__tenant=tenant,
                    status="active",
                    expiry_date__gte=today,
                    expiry_date__lte=today + timedelta(days=7),
                ).select_related("item", "item__model")
            )

            # 3. If there are expired or expiring batches, notify the tenant's operators
            if expired_batches or expiring_batches:
                # Find recipients
                recipients = []
                users = User.objects.filter(tenant=tenant, is_active=True)

                for u in users:
                    if u.role and any(
                        term in u.role.name.lower()
                        for term in ["operator", "stock", "estoque", "admin"]
                    ):
                        recipients.append(u.email)

                # Fallback to users with view_batch permission or superusers/staff
                if not recipients:
                    for u in users:
                        if (
                            u.has_perm("assets.view_batch")
                            or u.is_staff
                            or u.is_superuser
                        ):
                            recipients.append(u.email)

                # Final fallback to all active users of the tenant
                if not recipients:
                    recipients = list(users.values_list("email", flat=True))

                if recipients:
                    send_expiration_email(
                        tenant, expired_batches, expiring_batches, recipients
                    )

            processed_count += 1
            logger.info(
                f"Processed expiration for tenant {tenant.trade_name}: "
                f"{marked_expired_count} marked expired, "
                f"{len(expiring_batches)} expiring soon."
            )

        except Exception as e:
            logger.error(
                f"Error processing batch expiration for tenant {tenant.trade_name}: {e}",
                exc_info=True,
            )

    # Reset search path to public at the end of task
    set_tenant_schema("public")
    return f"Processed {processed_count} tenants successfully."


def send_expiration_email(tenant, expired_batches, expiring_batches, recipients):
    """
    Sends a formatted email listing expired and expiring batches to the recipients.
    """
    subject = f"[{tenant.trade_name}] Alerta de Vencimento de Lotes"

    body_lines = [
        "Olá,",
        f"Este é um alerta automático do SolAI ERP para a empresa {tenant.company_name}.\n",
    ]

    if expired_batches:
        body_lines.append("=== LOTES EXPIRADOS (Marcados como inativos/expirados) ===")
        for b in expired_batches:
            model_name = b.item.model.name if b.item.model else b.item.name
            body_lines.append(
                f"- SKU: {b.item.sku} | Modelo: {model_name} | Lote: {b.batch_code} | "
                f"Validade: {b.expiry_date.strftime('%d/%m/%Y')} | Qtd. Estoque: {b.stock_quantity}"
            )
        body_lines.append("\n")

    if expiring_batches:
        body_lines.append("=== LOTES PRÓXIMOS AO VENCIMENTO (Nos próximos 7 dias) ===")
        for b in expiring_batches:
            model_name = b.item.model.name if b.item.model else b.item.name
            body_lines.append(
                f"- SKU: {b.item.sku} | Modelo: {model_name} | Lote: {b.batch_code} | "
                f"Validade: {b.expiry_date.strftime('%d/%m/%Y')} | Qtd. Estoque: {b.stock_quantity}"
            )
        body_lines.append("\n")

    body_lines.append(
        "Por favor, verifique o estoque físico e realize as movimentações ou descartes necessários."
    )
    body_lines.append("Atenciosamente,\nEquipe SolAI ERP")

    body = "\n".join(body_lines)

    send_mail(
        subject=subject,
        message=body,
        from_email=None,  # Uses DEFAULT_FROM_EMAIL setting
        recipient_list=recipients,
        fail_silently=False,
    )
