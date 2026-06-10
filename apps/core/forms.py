from django import forms
from django.contrib.auth import get_user_model

from apps.core.models import Role, Sector


class RoleForm(forms.ModelForm):
    sector = forms.ModelChoiceField(
        queryset=Sector.objects.none(),
        label="Setor",
        widget=forms.Select(attrs={
            "class": "w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-300 dark:border-slate-800 rounded-sm text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-1 focus:ring-brand-500",
        })
    )

    class Meta:
        model = Role
        fields = ["name", "sector", "level", "description", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={
                "class": "w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-300 dark:border-slate-800 rounded-sm text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-1 focus:ring-brand-500",
                "placeholder": "Ex: Gerente de Vendas"
            }),
            "level": forms.Select(attrs={
                "class": "w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-300 dark:border-slate-800 rounded-sm text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-1 focus:ring-brand-500",
            }),
            "description": forms.Textarea(attrs={
                "class": "w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-300 dark:border-slate-800 rounded-sm text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-1 focus:ring-brand-500",
                "rows": 3,
                "placeholder": "Breve descrição das responsabilidades do cargo"
            }),
            "is_active": forms.CheckboxInput(attrs={
                "class": "h-4 w-4 text-brand-600 focus:ring-brand-500 border-slate-300 dark:border-slate-800 rounded-sm bg-slate-50 dark:bg-slate-900"
            })
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


class UserForm(forms.ModelForm):
    role = forms.ModelChoiceField(
        queryset=Role.objects.none(),
        label="Cargo",
        widget=forms.Select(attrs={
            "class": "w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-300 dark:border-slate-800 rounded-sm text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-1 focus:ring-brand-500",
        })
    )

    class Meta:
        model = get_user_model()
        fields = ["username", "email", "full_name", "role", "is_active"]
        widgets = {
            "username": forms.TextInput(attrs={
                "class": "w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-300 dark:border-slate-800 rounded-sm text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-1 focus:ring-brand-500",
                "placeholder": "Ex: joao.silva"
            }),
            "email": forms.EmailInput(attrs={
                "class": "w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-300 dark:border-slate-800 rounded-sm text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-1 focus:ring-brand-500",
                "placeholder": "Ex: joao@empresa.com"
            }),
            "full_name": forms.TextInput(attrs={
                "class": "w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-300 dark:border-slate-800 rounded-sm text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-1 focus:ring-brand-500",
                "placeholder": "Ex: João Silva"
            }),
            "is_active": forms.CheckboxInput(attrs={
                "class": "h-4 w-4 text-brand-600 focus:ring-brand-500 border-slate-300 dark:border-slate-800 rounded-sm bg-slate-50 dark:bg-slate-900"
            })
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
