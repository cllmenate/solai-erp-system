from django.contrib import messages
from django.contrib.auth import (
    authenticate,
    get_user_model,
    login,
    logout,
    update_session_auth_hash,
)
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.core.signing import BadSignature, SignatureExpired, dumps, loads
from django.db import connection
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.crypto import get_random_string

from django.utils import timezone
from apps.core.decorators import tenant_permission_required
from apps.core.forms import RoleForm, UserForm, TenantSettingsForm
from apps.core.models import Role, Tenant, UserPreferences
from apps.core.services import provision_tenant
from apps.core.services_lgpd import export_user_data_json
from django_otp.plugins.otp_totp.models import TOTPDevice
import qrcode
import qrcode.image.svg
from io import BytesIO
from django.http import HttpResponse


def login_view(request):
    # SSO auto-login via one-time token on subdomain
    token = request.GET.get("token")
    if token:
        try:
            data = loads(token, salt="public-login-salt", max_age=20)
            token_subdomain = data["subdomain"]
            user_id = data["user_id"]
            
            if getattr(request, "tenant", None) is not None and request.tenant.subdomain == token_subdomain:
                user_model = get_user_model()
                user = user_model.objects.get(id=user_id)
                if user.is_active:
                    login(request, user, backend="apps.core.auth_backends.EmailOrUsernameBackend")
                    messages.success(request, f"Bem-vindo de volta, {user.username}!")
                    return redirect("/")
        except Exception:
            messages.error(request, "O token de login expirou ou é inválido.")
            return redirect("login")

    if request.user.is_authenticated:
        if getattr(request, "tenant", None) is not None:
            return redirect("/")
        logout(request)

    if request.method == "POST":
        username_or_email = request.POST.get("username_or_email")
        password = request.POST.get("password")
        subdomain = request.POST.get("subdomain")

        # If no tenant context exists (accessing from base domain)
        if getattr(request, "tenant", None) is None:
            if not subdomain:
                messages.error(request, "O subdomínio é obrigatório.")
                return render(request, "core/login.html")
            try:
                tenant = Tenant.objects.get(subdomain=subdomain, is_active=True)
            except Tenant.DoesNotExist:
                messages.error(request, "Subdomínio não encontrado ou inativo.")
                return render(request, "core/login.html")

            # Temporarily switch search path to tenant's schema for authentication
            db_engine = connection.settings_dict.get("ENGINE", "")
            if "sqlite" not in db_engine:
                with connection.cursor() as cursor:
                    cursor.execute(f"SET search_path TO {tenant.schema_name}, public")

            user = authenticate(request, username=username_or_email, password=password, tenant=tenant)

            # Reset connection path to public if auth fails so public context is restored
            if "sqlite" not in db_engine and user is None:
                with connection.cursor() as cursor:
                    cursor.execute("SET search_path TO public")

            if user is not None:
                if user.is_active:
                    login_token = dumps(
                        {"user_id": str(user.id), "subdomain": subdomain},
                        salt="public-login-salt"
                    )
                    host_parts = request.get_host().split(":")
                    port = f":{host_parts[1]}" if len(host_parts) > 1 else ""
                    base_domain = host_parts[0]
                    if base_domain.startswith("www."):
                        base_domain = base_domain[4:]
                    
                    if base_domain in ("localhost", "127.0.0.1"):
                        redirect_url = f"http://{subdomain}.localhost{port}/auth/login/?token={login_token}"
                    else:
                        redirect_url = f"http://{subdomain}.{base_domain}{port}/auth/login/?token={login_token}"
                    return redirect(redirect_url)
                else:
                    messages.error(request, "Esta conta está inativa.")
            else:
                messages.error(request, "Usuário, e-mail ou senha inválidos.")
            
            return render(request, "core/login.html")

        # Authenticate under active subdomain/tenant schema
        tenant = getattr(request, "tenant", None)
        user = authenticate(request, username=username_or_email, password=password, tenant=tenant)
        if user is not None:
            if user.is_active:
                login(request, user)
                next_url = request.GET.get("next", "/")
                return redirect(next_url)
            else:
                messages.error(request, "Esta conta está inativa. Se você acabou de se cadastrar, verifique o link de ativação.")
        else:
            messages.error(request, "Usuário, e-mail ou senha inválidos.")

    return render(request, "core/login.html")


def logout_view(request):
    logout(request)
    return redirect("/")


def signup_trial_view(request):
    if request.user.is_authenticated:
        return redirect("/")

    if request.method == "POST":
        company_name = request.POST.get("company_name")
        trade_name = request.POST.get("trade_name")
        cnpj = request.POST.get("cnpj")
        subdomain = request.POST.get("subdomain")
        admin_username = request.POST.get("username")
        admin_email = request.POST.get("email")

        # Basic validations
        if not all([company_name, trade_name, cnpj, subdomain, admin_username, admin_email]):
            messages.error(request, "Todos os campos são obrigatórios.")
            return render(request, "core/signup.html")

        # Let's ensure subdomain is unique in public schema
        # We need to make sure we query Tenant in public schema
        db_engine = connection.settings_dict.get("ENGINE", "")
        if "sqlite" not in db_engine:
            with connection.cursor() as cursor:
                cursor.execute("SET search_path TO public")

        if Tenant.objects.filter(subdomain=subdomain).exists():
            messages.error(request, "Este subdomínio já está em uso.")
            return render(request, "core/signup.html")

        if Tenant.objects.filter(cnpj=cnpj).exists():
            messages.error(request, "Este CNPJ já está cadastrado.")
            return render(request, "core/signup.html")

        schema_name = f"tenant_{subdomain.replace('-', '_')}"

        try:
            # Provision tenant with inactive admin (password=None)
            provision_tenant(
                company_name=company_name,
                trade_name=trade_name,
                cnpj=cnpj,
                subdomain=subdomain,
                schema_name=schema_name,
                admin_username=admin_username,
                admin_email=admin_email,
                admin_password=None,
            )

            # Generate set password token
            token = dumps(
                {"subdomain": subdomain, "username": admin_username},
                salt="set-password-salt"
            )

            # Redirect to success page showing the link
            return redirect(f"/auth/signup-success/?token={token}")

        except Exception as e:
            messages.error(request, f"Erro ao criar conta trial: {e}")

    return render(request, "core/signup.html")


def signup_success_view(request):
    token = request.GET.get("token")
    if not token:
        return redirect("/")
    
    # We construct the absolute URL link for MVP password setup
    host = request.get_host()
    # If the user is on localhost:8000, keep it.
    activation_link = f"http://{host}/auth/set-password/{token}/"
    
    return render(request, "core/signup_success.html", {"activation_link": activation_link})


def set_password_view(request, token):
    try:
        data = loads(token, salt="set-password-salt", max_age=86400)  # 24h
        subdomain = data["subdomain"]
        username = data["username"]
    except (SignatureExpired, BadSignature):
        messages.error(request, "O link de definição de senha expirou ou é inválido.")
        return render(request, "core/set_password_error.html")

    # Set connection search path to this tenant's schema to fetch the inactive user
    try:
        tenant = Tenant.objects.get(subdomain=subdomain)
    except Tenant.DoesNotExist as err:
        raise Http404("Tenant não encontrado") from err

    db_engine = connection.settings_dict.get("ENGINE", "")
    if "sqlite" not in db_engine:
        with connection.cursor() as cursor:
            cursor.execute(f"SET search_path TO {tenant.schema_name}, public")

    user_model = get_user_model()
    try:
        user = user_model.objects.get(username=username, tenant=tenant)
    except user_model.DoesNotExist as err:
        raise Http404("Usuário não encontrado no tenant.") from err

    if request.method == "POST":
        password = request.POST.get("password")
        password_confirm = request.POST.get("password_confirm")

        if not password or password != password_confirm:
            messages.error(request, "As senhas não coincidem ou são inválidas.")
        else:
            user.set_password(password)
            user.is_active = True
            user.save()

            # Automatically login
            # We must pass backend argument because we have multiple auth backends
            login(request, user, backend="apps.core.auth_backends.EmailOrUsernameBackend")
            messages.success(request, "Senha definida com sucesso! Bem-vindo.")
            
            # Redirect to the tenant-specific subdomain dashboard
            # E.g. http://subdomain.localhost:8000/assets/items/
            host_parts = request.get_host().split(":")
            port = f":{host_parts[1]}" if len(host_parts) > 1 else ""
            base_domain = host_parts[0]
            if base_domain.startswith("www."):
                base_domain = base_domain[4:]
            
            # If we're already on a subdomain or just localhost
            if base_domain == "localhost" or base_domain == "127.0.0.1":
                redirect_url = f"http://{subdomain}.localhost{port}/"
            else:
                redirect_url = f"http://{subdomain}.{base_domain}{port}/"
            
            return redirect(redirect_url)

    return render(request, "core/set_password.html", {"username": username, "subdomain": subdomain})


def password_recovery_request_view(request):
    if request.method == "POST":
        email = request.POST.get("email")
        
        # To recover, we need to know which schema/tenant the user belongs to.
        # If there is a subdomain in the host, we check the current schema.
        # Otherwise we search across all schemas?
        # Standard approach: if they recover from demo.localhost:8000, we search in demo schema.
        # If they recover from landing page, we ask for subdomain or look up public (which won't have it).
        # Let's search inside the current active tenant schema resolved by middleware.
        # If no tenant context is resolved, we ask them to use the subdomain-specific login page to recover.
        if not hasattr(request, "tenant") or request.tenant is None:
            messages.error(request, "Por favor, acesse a página de login da sua empresa para recuperar a senha (ex: sua-empresa.solai.com.br/auth/recovery/).")
            return render(request, "core/recovery_request.html")

        user_model = get_user_model()
        try:
            user = user_model.objects.get(email=email, tenant=request.tenant)
            token = dumps(
                {"subdomain": request.tenant.subdomain, "username": user.username, "email": email},
                salt="password-recovery-salt"
            )
            host = request.get_host()
            recovery_link = f"http://{host}/auth/recovery/confirm/{token}/"
            return render(request, "core/recovery_success.html", {"recovery_link": recovery_link})
        except user_model.DoesNotExist:
            # For security, we can display success even if user not found, but for MVP let's be explicit
            messages.error(request, "E-mail não encontrado nesta empresa.")

    return render(request, "core/recovery_request.html")


def password_recovery_confirm_view(request, token):
    try:
        data = loads(token, salt="password-recovery-salt", max_age=3600)  # 1 hour
        subdomain = data["subdomain"]
        username = data["username"]
    except (SignatureExpired, BadSignature):
        messages.error(request, "O link de recuperação expirou ou é inválido.")
        return render(request, "core/set_password_error.html")

    try:
        tenant = Tenant.objects.get(subdomain=subdomain)
    except Tenant.DoesNotExist as err:
        raise Http404("Tenant não encontrado") from err

    db_engine = connection.settings_dict.get("ENGINE", "")
    if "sqlite" not in db_engine:
        with connection.cursor() as cursor:
            cursor.execute(f"SET search_path TO {tenant.schema_name}, public")

    user_model = get_user_model()
    try:
        user = user_model.objects.get(username=username, tenant=tenant)
    except user_model.DoesNotExist as err:
        raise Http404("Usuário não encontrado.") from err

    if request.method == "POST":
        password = request.POST.get("password")
        password_confirm = request.POST.get("password_confirm")

        if not password or password != password_confirm:
            messages.error(request, "As senhas não coincidem ou são inválidas.")
        else:
            user.set_password(password)
            user.is_active = True
            user.save()

            login(request, user, backend="apps.core.auth_backends.EmailOrUsernameBackend")
            messages.success(request, "Sua senha foi redefinida com sucesso.")
            return redirect("/")

    return render(request, "core/recovery_confirm.html", {"username": username})


@tenant_permission_required("core.add_user")
def invite_create_view(request):

    if request.method == "POST":
        email = request.POST.get("email")
        if not email:
            messages.error(request, "E-mail do convidado é obrigatório.")
        else:
            token = dumps(
                {"subdomain": request.tenant.subdomain, "email": email},
                salt="invite-salt"
            )
            host = request.get_host()
            invite_link = f"http://{host}/auth/invite/accept/{token}/"
            return render(request, "core/invite_created.html", {"invite_link": invite_link, "email": email})

    return render(request, "core/invite_create.html")


def invite_accept_view(request, token):
    try:
        data = loads(token, salt="invite-salt", max_age=604800)  # 7 days
        subdomain = data["subdomain"]
        email = data["email"]
    except (SignatureExpired, BadSignature):
        messages.error(request, "O convite expirou ou é inválido.")
        return render(request, "core/set_password_error.html")

    try:
        tenant = Tenant.objects.get(subdomain=subdomain)
    except Tenant.DoesNotExist as err:
        raise Http404("Tenant não encontrado") from err

    db_engine = connection.settings_dict.get("ENGINE", "")
    if "sqlite" not in db_engine:
        with connection.cursor() as cursor:
            cursor.execute(f"SET search_path TO {tenant.schema_name}, public")

    if request.method == "POST":
        username = request.POST.get("username")
        full_name = request.POST.get("full_name")
        password = request.POST.get("password")
        password_confirm = request.POST.get("password_confirm")

        user_model = get_user_model()
        if user_model.objects.filter(username=username, tenant=tenant).exists():
            messages.error(request, "Este nome de usuário já está em uso nesta empresa.")
        elif not password or password != password_confirm:
            messages.error(request, "As senhas não coincidem ou são inválidas.")
        else:
            user = user_model.objects.create_user(
                username=username,
                email=email,
                password=password,
                full_name=full_name,
                tenant=tenant,
                is_active=True
            )
            login(request, user, backend="apps.core.auth_backends.EmailOrUsernameBackend")
            messages.success(request, "Cadastro concluído! Bem-vindo.")
            return redirect("/")

    return render(request, "core/invite_accept.html", {"email": email, "subdomain": subdomain})


def profile_view(request):
    if not request.user.is_authenticated:
        return redirect("login")

    # Ensure user preferences exist
    preferences, _ = UserPreferences.objects.get_or_create(user=request.user)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "profile":
            full_name = request.POST.get("full_name", "").strip()
            email = request.POST.get("email", "").strip()

            if not email:
                messages.error(request, "O e-mail é obrigatório.")
            else:
                user_model = get_user_model()
                # Check email uniqueness within tenant scope
                duplicate_email = user_model.objects.filter(
                    tenant=request.tenant,
                    email=email
                ).exclude(id=request.user.id).exists()

                if duplicate_email:
                    messages.error(request, "Este e-mail já está em uso por outro usuário nesta empresa.")
                else:
                    request.user.full_name = full_name
                    request.user.email = email
                    request.user.save()
                    messages.success(request, "Perfil atualizado com sucesso!")
                    return redirect("settings_profile")

        elif action == "password":
            current_password = request.POST.get("current_password", "")
            new_password = request.POST.get("new_password", "")
            confirm_password = request.POST.get("confirm_password", "")

            if not request.user.check_password(current_password):
                messages.error(request, "Senha atual incorreta.")
            elif not new_password:
                messages.error(request, "A nova senha não pode ser vazia.")
            elif new_password != confirm_password:
                messages.error(request, "A nova senha e a confirmação não coincidem.")
            else:
                request.user.set_password(new_password)
                request.user.save()
                update_session_auth_hash(request, request.user)
                messages.success(request, "Senha alterada com sucesso!")
                return redirect("settings_profile")

        elif action == "appearance":
            dark_mode = request.POST.get("dark_mode") == "on"
            sidebar_compact = request.POST.get("sidebar_compact") == "on"
            visual_theme = request.POST.get("visual_theme", "default")

            preferences.dark_mode = dark_mode
            preferences.sidebar_compact = sidebar_compact
            preferences.visual_theme = visual_theme
            preferences.save()

            messages.success(request, "Preferências de aparência atualizadas com sucesso!")
            return redirect("settings_profile")

        elif action == "privacy":
            language = request.POST.get("language", "pt-br")
            privacy_consent = request.POST.get("privacy_consent") == "on"

            preferences.language = language
            
            if privacy_consent and not preferences.privacy_consent_accepted:
                preferences.privacy_consent_accepted = True
                preferences.privacy_consent_at = timezone.now()
                # Get client IP securely taking Cloudflare into account
                ip = request.META.get('HTTP_CF_CONNECTING_IP')
                if not ip:
                    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
                    if x_forwarded_for:
                        ip = x_forwarded_for.split(',')[0]
                    else:
                        ip = request.META.get('REMOTE_ADDR')
                preferences.privacy_consent_ip = ip
            elif not privacy_consent:
                preferences.privacy_consent_accepted = False
                preferences.privacy_consent_at = None
                preferences.privacy_consent_ip = None

            preferences.save()
            messages.success(request, "Preferências de privacidade atualizadas com sucesso!")
            return redirect(f"{request.path}?tab=privacy")

    return render(
        request,
        "core/settings_profile.html",
        {
            "preferences": preferences,
            "active_tab": request.GET.get("tab", "profile"),
            "devices": TOTPDevice.objects.filter(user=request.user)
        }
    )

@tenant_permission_required("core.change_tenant")
def tenant_settings_view(request):
    if request.method == "POST":
        form = TenantSettingsForm(request.POST, instance=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, "Configurações da empresa (DPO/LGPD) atualizadas com sucesso!")
            return redirect("settings_tenant")
    else:
        form = TenantSettingsForm(instance=request.tenant)
    return render(request, "core/settings_tenant.html", {"form": form})

def setup_2fa_view(request):
    if not request.user.is_authenticated:
        return redirect("login")
    
    device, created = TOTPDevice.objects.get_or_create(user=request.user, name="default")
    
    if request.method == "POST":
        token = request.POST.get("token")
        if device.verify_token(token):
            device.confirmed = True
            device.save()
            messages.success(request, "2FA ativado com sucesso!")
            return redirect(f"/settings/profile/?tab=privacy")
        else:
            messages.error(request, "Código inválido. Tente novamente.")

    url = device.config_url
    factory = qrcode.image.svg.SvgPathImage
    img = qrcode.make(url, image_factory=factory)
    stream = BytesIO()
    img.save(stream)
    svg_data = stream.getvalue().decode()

    return render(request, "core/setup_2fa.html", {"svg_data": svg_data, "device": device})

from django_otp import login as otp_login

def verify_2fa_view(request):
    if not request.user.is_authenticated:
        return redirect("login")
        
    device = TOTPDevice.objects.filter(user=request.user, confirmed=True).first()
    if not device:
        return redirect("/")

    if request.method == "POST":
        token = request.POST.get("token")
        if device.verify_token(token):
            otp_login(request, device)
            messages.success(request, "Acesso verificado com 2FA!")
            next_url = request.GET.get("next", "/")
            return redirect(next_url)
        else:
            messages.error(request, "Código inválido. Tente novamente.")
            
    return render(request, "core/verify_2fa.html")

def export_data_view(request):
    if not request.user.is_authenticated:
        return redirect("login")
        
    json_data = export_user_data_json(request.user)
    response = HttpResponse(json_data, content_type="application/json")
    response["Content-Disposition"] = f'attachment; filename="solai_data_export_{request.user.username}.json"'
    return response




@tenant_permission_required("core.view_role")
def role_list_view(request):
    search_query = request.GET.get("search", "")
    roles = Role.objects.filter(tenant=request.tenant)
    if search_query:
        roles = roles.filter(Q(name__icontains=search_query))
    roles = roles.order_by("-level", "name")
    
    # Check if there are active users assigned to deactivated roles
    user_model = get_user_model()
    active_users_in_inactive_roles = user_model.objects.filter(
        tenant=request.tenant,
        is_active=True,
        role__in=roles.filter(is_active=False)
    ).select_related("role")
    
    warn_admin = active_users_in_inactive_roles.exists()

    return render(
        request,
        "core/role_list.html",
        {
            "roles": roles,
            "search_query": search_query,
            "warn_admin": warn_admin,
            "active_users_in_inactive_roles": active_users_in_inactive_roles,
        }
    )

@tenant_permission_required("core.add_role")
def role_create_view(request):
    if request.method == "POST":
        form = RoleForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            role = form.save(commit=False)
            role.tenant = request.tenant
            role.save()
            messages.success(request, f"Cargo '{role.friendly_name}' criado com sucesso!")
            return redirect("settings_roles")
    else:
        form = RoleForm(tenant=request.tenant)

    return render(
        request,
        "core/role_form.html",
        {
            "form": form,
            "title": "Criar Novo Cargo",
        }
    )

@tenant_permission_required("core.change_role")
def role_edit_view(request, pk):
    role = get_object_or_404(Role, pk=pk, tenant=request.tenant)
    
    if request.method == "POST":
        form = RoleForm(request.POST, instance=role, tenant=request.tenant)
        if form.is_valid():
            role = form.save()
            messages.success(request, f"Cargo '{role.friendly_name}' atualizado com sucesso!")
            return redirect("settings_roles")
    else:
        form = RoleForm(instance=role, tenant=request.tenant)

    return render(
        request,
        "core/role_form.html",
        {
            "form": form,
            "title": f"Editar Cargo: {role.friendly_name}",
            "role": role,
        }
    )

@tenant_permission_required("core.change_role")
def role_toggle_active_view(request, pk):
    role = get_object_or_404(Role, pk=pk, tenant=request.tenant)
    role.is_active = not role.is_active
    role.save()
    
    status_str = "ativado" if role.is_active else "desativado"
    messages.success(request, f"Cargo '{role.friendly_name}' foi {status_str} com sucesso!")
    return redirect("settings_roles")


@tenant_permission_required("core.change_role")
def role_permissions_view(request, pk):
    role = get_object_or_404(Role, pk=pk, tenant=request.tenant)
    
    # Define our targeted apps and models for the permissions grid
    app_modules = {
        "assets": {
            "label": "Estoque & Ativos",
            "models": {
                "item": "Itens",
                "batch": "Lotes",
                "brand": "Marcas",
                "category": "Categorias",
                "model": "Modelos",
                "techsheettemplate": "Templates de Ficha Técnica",
            }
        },
        "commercial": {
            "label": "Comercial & CRM",
            "models": {
                "partner": "Parceiros",
                "contact": "Contatos",
                "address": "Endereços",
            }
        },
        "core": {
            "label": "Configurações",
            "models": {
                "user": "Usuários",
                "role": "Cargos",
                "tenant": "Empresas/Tenants",
            }
        }
    }
    
    actions = ["view", "add", "change", "delete"]
    
    # Fetch all relevant permissions
    all_perms = Permission.objects.filter(
        content_type__app_label__in=app_modules.keys()
    ).select_related("content_type")
    
    # Create a lookup dictionary of {(app_label, codename): Permission}
    perm_lookup = {
        (p.content_type.app_label, p.codename): p for p in all_perms
    }
    
    # Get the role's current permission IDs as a set for quick checking
    role_perm_ids = set(role.permissions.values_list("id", flat=True))
    
    if request.method == "POST":
        selected_perm_ids = []
        # Check standard format permission checkboxes from POST
        post_perms = request.POST.getlist("permissions")
        for perm_id in post_perms:
            try:
                selected_perm_ids.append(int(perm_id))
            except ValueError:
                pass
                
        # Validate that the selected permission IDs belong to our allowed modules/apps
        allowed_perms = Permission.objects.filter(
            id__in=selected_perm_ids,
            content_type__app_label__in=app_modules.keys()
        )
        
        # Atomically update role permissions
        role.permissions.set(allowed_perms)
        
        messages.success(request, f"Permissões do cargo '{role.friendly_name}' atualizadas com sucesso!")
        return redirect("settings_roles")
        
    # Build a clean data structure for the template grid
    grid_data = []
    for app_label, app_info in app_modules.items():
        module_rows = []
        for model_name, model_label in app_info["models"].items():
            row_perms = {}
            for action in actions:
                codename = f"{action}_{model_name}"
                perm = perm_lookup.get((app_label, codename))
                if perm:
                    row_perms[action] = {
                        "id": perm.id,
                        "codename": perm.codename,
                        "granted": perm.id in role_perm_ids,
                    }
                else:
                    row_perms[action] = None
            module_rows.append({
                "model_name": model_name,
                "model_label": model_label,
                "permissions": row_perms,
            })
        grid_data.append({
            "app_label": app_label,
            "app_label_display": app_info["label"],
            "rows": module_rows,
        })
        
    return render(
        request,
        "core/role_permissions.html",
        {
            "role": role,
            "grid_data": grid_data,
            "actions": actions,
        }
    )


@tenant_permission_required("core.view_user")
def user_list_view(request):
    search_query = request.GET.get("search", "")
    user_model = get_user_model()
    users = user_model.objects.filter(tenant=request.tenant).select_related("role", "role__sector")
    if search_query:
        users = users.filter(Q(username__icontains=search_query) | Q(first_name__icontains=search_query) | Q(last_name__icontains=search_query) | Q(email__icontains=search_query))
    users = users.order_by("username")
    return render(
        request,
        "core/user_list.html",
        {
            "users": users,
            "search_query": search_query,
        }
    )


@tenant_permission_required("core.add_user")
def user_create_view(request):
    if request.method == "POST":
        form = UserForm(request.POST, tenant=request.tenant, request_user=request.user)
        if form.is_valid():
            user = form.save(commit=False)
            user.tenant = request.tenant
            
            # Generate a secure random password for security
            temp_pass = get_random_string(32)
            user.set_password(temp_pass)
            
            user.save()
            messages.success(request, f"Usuário '{user.username}' criado com sucesso!")
            return redirect("settings_users")
    else:
        form = UserForm(tenant=request.tenant, request_user=request.user)

    return render(
        request,
        "core/user_form.html",
        {
            "form": form,
            "title": "Criar Novo Usuário",
        }
    )


@tenant_permission_required("core.change_user")
def user_edit_view(request, pk):
    user_model = get_user_model()
    user = get_object_or_404(user_model, pk=pk, tenant=request.tenant)
    
    # Validação de Hierarquia de Cargos
    if not request.user.is_superuser:
        editor_level = getattr(request.user.role, "level", 0)
        target_level = getattr(user.role, "level", 0)
        if user.id != request.user.id and target_level >= editor_level:
            raise PermissionDenied("Você não tem permissão para editar um usuário com cargo de nível superior ou igual ao seu.")

    if request.method == "POST":
        form = UserForm(request.POST, instance=user, tenant=request.tenant, request_user=request.user)
        if form.is_valid():
            user = form.save()
            messages.success(request, f"Usuário '{user.username}' atualizado com sucesso!")
            return redirect("settings_users")
    else:
        form = UserForm(instance=user, tenant=request.tenant, request_user=request.user)

    return render(
        request,
        "core/user_form.html",
        {
            "form": form,
            "title": f"Editar Usuário: {user.username}",
            "user_obj": user,
        }
    )


@tenant_permission_required("core.change_user")
def user_toggle_active_view(request, pk):
    if request.method != "POST":
        raise Http404("Método não permitido.")
        
    user_model = get_user_model()
    user = get_object_or_404(user_model, pk=pk, tenant=request.tenant)
    
    # Não permitir que um usuário desative a si próprio
    if user.id == request.user.id:
        messages.error(request, "Você não pode desativar o seu próprio usuário.")
        return redirect("settings_users")

    # Validação de Hierarquia de Cargos
    if not request.user.is_superuser:
        editor_level = getattr(request.user.role, "level", 0)
        target_level = getattr(user.role, "level", 0)
        if target_level >= editor_level:
            raise PermissionDenied("Você não tem permissão para alterar o status de um usuário com cargo de nível superior ou igual ao seu.")

    user.is_active = not user.is_active
    user.save()
    
    status_str = "ativado" if user.is_active else "desativado"
    messages.success(request, f"Usuário '{user.username}' foi {status_str} com sucesso!")
    return redirect("settings_users")


