import uuid

from django.conf import settings
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    Group,
    PermissionsMixin,
)
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
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


class Role(Group):
    """
    Extends Django's default Group model to represent roles inside a Tenant.
    """
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="roles",
        null=True,
        blank=True
    )
    level = models.IntegerField(default=1)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "role"
        verbose_name_plural = "roles"

    @property
    def friendly_name(self):
        if self.name and ":" in self.name:
            return self.name.split(":", 1)[1]
        return self.name

    def save(self, *args, **kwargs):
        if self.tenant and self.name and not self.name.startswith(f"{self.tenant.subdomain}:"):
            self.name = f"{self.tenant.subdomain}:{self.name}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.friendly_name


class UserManager(BaseUserManager):
    def create_user(self, username, email, password=None, **extra_fields):
        if not username:
            raise ValueError("The Username field must be set")
        if not email:
            raise ValueError("The Email field must be set")

        email = self.normalize_email(email)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(username, email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model supporting multi-tenancy, custom roles and simple history.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="users",
        null=True,
        blank=True
    )
    username = models.CharField(max_length=150)
    email = models.EmailField()
    full_name = models.CharField(max_length=255, blank=True)
    role = models.ForeignKey(
        Role,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users"
    )

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email"]

    history = HistoricalRecords()

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"
        unique_together = ("tenant", "username"), ("tenant", "email")

    def __str__(self):
        return f"{self.username} ({self.email})"


class UserPreferences(models.Model):
    """
    Stores look & feel preferences and other UI/usability preferences for a user.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="preferences"
    )
    dark_mode = models.BooleanField(default=False)
    sidebar_compact = models.BooleanField(default=False)
    visual_theme = models.CharField(max_length=50, default="default")

    def __str__(self):
        return f"Preferences for {self.user.username}"


@receiver(post_save, sender=User)
def create_user_preferences(sender, instance, created, **kwargs):
    if created:
        UserPreferences.objects.get_or_create(user=instance)

