import uuid

from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords


class BaseModel(models.Model):
    """
    Abstract base model containing universal fields.
    Automatically integrates with django-simple-history.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_updated",
    )

    history = HistoricalRecords(inherit=True)

    class Meta:
        abstract = True

    def __str__(self):
        return self.name


class Tenant(BaseModel):
    """
    Tenant representation mapping to PostgreSQL schemas.
    """

    company_name = models.CharField(max_length=255)
    trade_name = models.CharField(max_length=255)
    cnpj = models.CharField(max_length=18, unique=True)
    subdomain = models.SlugField(max_length=63, unique=True)
    schema_name = models.CharField(max_length=63, unique=True)
    stripe_customer_id = models.CharField(max_length=255, blank=True, null=True)
    stripe_subscription_id = models.CharField(max_length=255, blank=True, null=True)
    plan = models.CharField(max_length=50, default="trial")
    trial_ends_at = models.DateTimeField()
    ai_autonomy_level = models.CharField(
        max_length=50,
        choices=[
            ("assistive", "Assistive"),
            ("semi_autonomous", "Semi Autonomous"),
            ("custom", "Custom"),
        ],
        default="assistive",
    )

    def save(self, *args, **kwargs):
        # Auto-set name from trade_name or company_name if name is not set
        if not self.name:
            self.name = self.trade_name or self.company_name
        super().save(*args, **kwargs)
