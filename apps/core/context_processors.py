from django.contrib.auth import get_user_model
from apps.core.models import Role

def role_warnings_context(request):
    if not request.user.is_authenticated:
        return {}
    
    context = {}
    
    # Check if current user's role is deactivated
    if hasattr(request.user, "role") and request.user.role and not request.user.role.is_active:
        context["current_user_role_deactivated"] = True
        
    # Check if the user is tenant admin (has view_role permission)
    if request.user.has_perm("core.view_role") and getattr(request, "tenant", None):
        user_model = get_user_model()
        
        # Check if there are active users in inactive roles for this tenant
        has_inactive_roles_assigned = user_model.objects.filter(
            tenant=request.tenant,
            is_active=True,
            role__tenant=request.tenant,
            role__is_active=False
        ).exists()
        
        if has_inactive_roles_assigned:
            context["admin_has_inactive_roles_warning"] = True
            
    return context
