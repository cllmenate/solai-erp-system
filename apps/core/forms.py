from django import forms
from django.contrib.auth import get_user_model

from apps.core.models import Role, Sector, Tenant


def apply_design_system_styles(form):
    """
    Applies standard Tailwind classes for the design system (HeroUI-inspired)
    to the widgets of the form, preventing duplication in individual forms.
    """
    for _field_name, field in form.fields.items():
        widget = field.widget
        
        # Check widget type to determine base classes
        if isinstance(widget, forms.CheckboxInput):
            base_class = "h-4 w-4 text-brand-600 focus:ring-brand-500/20 border-slate-200 dark:border-slate-800 rounded-md bg-slate-100/60 dark:bg-slate-900/60 focus:ring-2"
        elif isinstance(widget, forms.Textarea):
            base_class = "w-full px-4 py-3 bg-slate-100/60 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 rounded-xl text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-4 focus:ring-brand-500/20 focus:border-brand-500 transition-all duration-200"
            if "rows" not in widget.attrs:
                widget.attrs["rows"] = 3
        else:
            base_class = "w-full px-4 py-3 bg-slate-100/60 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 rounded-xl text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-4 focus:ring-brand-500/20 focus:border-brand-500 transition-all duration-200"
            
        widget.attrs["class"] = base_class


class DesignSystemFormMixin:
    """
    Mixin that dynamically styles form widgets and applies error styling
    when the field has validation errors.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_design_system_styles(self)

    def __getitem__(self, name):
        bound_field = super().__getitem__(name)
        if self.is_bound and bound_field.errors:
            widget = bound_field.field.widget
            css_class = widget.attrs.get("class", "")
            
            # Use red/amber borders for inputs with errors
            if isinstance(widget, forms.CheckboxInput):
                if "border-rose-500" not in css_class:
                    css_class = css_class.replace("border-slate-200", "border-rose-500 dark:border-rose-500")
                    css_class = css_class.replace("focus:ring-brand-500/20", "focus:ring-rose-500/20")
                    widget.attrs["class"] = css_class
            else:
                if "border-rose-500" not in css_class:
                    css_class = css_class.replace("border-slate-200", "border-rose-500 dark:border-rose-500")
                    css_class = css_class.replace("dark:border-slate-800", "")
                    css_class = css_class.replace("focus:ring-brand-500/20", "focus:ring-rose-500/20")
                    css_class = css_class.replace("focus:border-brand-500", "focus:border-rose-500")
                    widget.attrs["class"] = css_class
        return bound_field


class RoleForm(DesignSystemFormMixin, forms.ModelForm):
    sector = forms.ModelChoiceField(
        queryset=Sector.objects.none(),
        label="Setor",
    )

    class Meta:
        model = Role
        fields = ["name", "sector", "level", "description", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={
                "placeholder": "Ex: Gerente de Vendas"
            }),
            "description": forms.Textarea(attrs={
                "placeholder": "Breve descrição das responsabilidades do cargo"
            }),
        }

    def __init__(self, *args, **kwargs):
        self.tenant = kwargs.pop("tenant", None)
        super().__init__(*args, **kwargs)
        if self.tenant:
            self.fields["sector"].queryset = Sector.objects.filter(tenant=self.tenant)
            self.fields["sector"].required = True
        
        self.fields["level"].choices = Role.LEVEL_CHOICES
        
        if self.instance and self.instance.pk:
            self.initial["name"] = self.instance.friendly_name

    def clean_name(self):
        name = self.cleaned_data.get("name")
        if not name:
            raise forms.ValidationError("O nome do cargo é obrigatório.")
        friendly_name = name.strip()
        
        full_name = f"{self.tenant.subdomain}:{friendly_name}" if self.tenant else friendly_name
        
        qs = Role.objects.filter(name=full_name, tenant=self.tenant)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Já existe um cargo com este nome neste tenant.")
        return friendly_name


class UserForm(DesignSystemFormMixin, forms.ModelForm):
    role = forms.ModelChoiceField(
        queryset=Role.objects.none(),
        label="Cargo",
    )

    class Meta:
        model = get_user_model()
        fields = ["username", "email", "full_name", "role", "is_active"]
        widgets = {
            "username": forms.TextInput(attrs={
                "placeholder": "Ex: joao.silva"
            }),
            "email": forms.EmailInput(attrs={
                "placeholder": "Ex: joao@empresa.com"
            }),
            "full_name": forms.TextInput(attrs={
                "placeholder": "Ex: João Silva"
            }),
        }

    def __init__(self, *args, **kwargs):
        self.tenant = kwargs.pop("tenant", None)
        self.request_user = kwargs.pop("request_user", None)
        super().__init__(*args, **kwargs)

        if self.tenant:
            roles_qs = Role.objects.filter(tenant=self.tenant, is_active=True)
            
            # Request user cannot assign roles with level >= their own unless they are superuser
            if self.request_user and not self.request_user.is_superuser:
                user_role_level = getattr(self.request_user.role, "level", 0)
                roles_qs = roles_qs.filter(level__lt=user_role_level)

            self.fields["role"].queryset = roles_qs
            self.fields["role"].required = True

    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip()
        user_model = get_user_model()
        qs = user_model.objects.filter(username=username, tenant=self.tenant)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Este nome de usuário já está em uso nesta empresa.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip()
        user_model = get_user_model()
        qs = user_model.objects.filter(email=email, tenant=self.tenant)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Este e-mail já está em uso por outro usuário nesta empresa.")
        return email

class TenantSettingsForm(DesignSystemFormMixin, forms.ModelForm):
    class Meta:
        model = Tenant
        fields = ["dpo_name", "dpo_email"]
        widgets = {
            "dpo_name": forms.TextInput(attrs={"placeholder": "Ex: João Silva"}),
            "dpo_email": forms.EmailInput(attrs={"placeholder": "Ex: dpo@empresa.com"}),
        }

