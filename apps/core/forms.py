from django import forms

from apps.core.models import Role


class RoleForm(forms.ModelForm):
    class Meta:
        model = Role
        fields = ["name", "level", "description", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={
                "class": "w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-300 dark:border-slate-800 rounded-sm text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-1 focus:ring-brand-500",
                "placeholder": "Ex: Gerente de Vendas"
            }),
            "level": forms.NumberInput(attrs={
                "class": "w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-300 dark:border-slate-800 rounded-sm text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-1 focus:ring-brand-500",
                "placeholder": "Nível de acesso (ex: 1 a 100)"
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
