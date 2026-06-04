from django.core.exceptions import ValidationError
from django.db import models
from validate_docbr import CNPJ, CPF

from apps.core.models import BaseModel, Tenant


def validate_document(value):
    """
    Validates document value as either a valid CPF or CNPJ.
    """
    # Remove punctuation
    clean_val = "".join(filter(str.isdigit, str(value)))
    
    if len(clean_val) == 11:
        cpf = CPF()
        if not cpf.validate(clean_val):
            raise ValidationError("CPF inválido.")
    elif len(clean_val) == 14:
        cnpj = CNPJ()
        if not cnpj.validate(clean_val):
            raise ValidationError("CNPJ inválido.")
    else:
        raise ValidationError("O documento deve ser um CPF (11 dígitos) ou CNPJ (14 dígitos).")


class Partner(BaseModel):
    """
    Partner model representing customers, suppliers, and carriers.
    """
    PERSON_TYPE_CHOICES = [
        ("individual", "Pessoa Física (PF)"),
        ("company", "Pessoa Jurídica (PJ)"),
    ]

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="partners",
    )
    is_customer = models.BooleanField(default=False, verbose_name="Cliente")
    is_supplier = models.BooleanField(default=False, verbose_name="Fornecedor")
    is_carrier = models.BooleanField(default=False, verbose_name="Transportadora")
    
    person_type = models.CharField(
        max_length=20,
        choices=PERSON_TYPE_CHOICES,
        default="company",
        verbose_name="Tipo de Pessoa",
    )
    legal_name = models.CharField(max_length=255, verbose_name="Razão Social / Nome Completo")
    trade_name = models.CharField(max_length=255, blank=True, null=True, verbose_name="Nome Fantasia / Apelido")
    document = models.CharField(
        max_length=20,
        validators=[validate_document],
        verbose_name="CPF/CNPJ",
    )
    state_registration = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="Inscrição Estadual",
    )
    municipal_registration = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="Inscrição Municipal",
    )
    website = models.URLField(blank=True, null=True, verbose_name="Site")
    integration_code = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Código de Integração",
    )

    class Meta:
        verbose_name = "parceiro"
        verbose_name_plural = "parceiros"
        unique_together = ("tenant", "document")

    def clean(self):
        super().clean()
        # Enforce that it has at least one type
        if not (self.is_customer or self.is_supplier or self.is_carrier):
            raise ValidationError(
                "O parceiro deve ser marcado como pelo menos um tipo (Cliente, Fornecedor ou Transportadora)."
            )
        # Normalize document
        self.document = "".join(filter(str.isdigit, str(self.document)))

    def full_clean(self, exclude=None, validate_unique=True, validate_constraints=True):
        if not self.name:
            self.name = self.trade_name or self.legal_name
        super().full_clean(exclude, validate_unique, validate_constraints)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def formatted_document(self):
        doc = self.document
        if len(doc) == 11:
            return f"{doc[:3]}.{doc[3:6]}.{doc[6:9]}-{doc[9:]}"
        elif len(doc) == 14:
            return f"{doc[:2]}.{doc[2:5]}.{doc[5:8]}/{doc[8:12]}-{doc[12:]}"
        return doc


class Contact(models.Model):
    """
    Contact details for a Partner.
    """
    partner = models.ForeignKey(
        Partner,
        on_delete=models.CASCADE,
        related_name="contacts",
    )
    name = models.CharField(max_length=255, verbose_name="Nome")
    email = models.EmailField(verbose_name="E-mail")
    phone = models.CharField(max_length=20, verbose_name="Telefone")
    role = models.CharField(max_length=100, blank=True, null=True, verbose_name="Cargo")
    is_primary = models.BooleanField(default=False, verbose_name="Contato Principal")

    class Meta:
        verbose_name = "contato"
        verbose_name_plural = "contatos"

    def __str__(self):
        return f"{self.name} - {self.partner.name}"


class Address(models.Model):
    """
    Address details for a Partner.
    """
    partner = models.ForeignKey(
        Partner,
        on_delete=models.CASCADE,
        related_name="addresses",
    )
    label = models.CharField(max_length=100, verbose_name="Rótulo (ex: Matriz, Filial)")
    zip_code = models.CharField(max_length=10, verbose_name="CEP")
    street = models.CharField(max_length=255, verbose_name="Logradouro")
    number = models.CharField(max_length=20, verbose_name="Número")
    complement = models.CharField(max_length=100, blank=True, null=True, verbose_name="Complemento")
    neighborhood = models.CharField(max_length=100, verbose_name="Bairro")
    city = models.CharField(max_length=100, verbose_name="Cidade")
    state = models.CharField(max_length=2, verbose_name="UF")
    country = models.CharField(max_length=100, default="BR", verbose_name="País")
    is_collection = models.BooleanField(default=False, verbose_name="Endereço de Coleta")
    is_delivery = models.BooleanField(default=False, verbose_name="Endereço de Entrega")

    class Meta:
        verbose_name = "endereço"
        verbose_name_plural = "endereços"

    def __str__(self):
        return f"{self.label}: {self.street}, {self.number} - {self.city}/{self.state}"
