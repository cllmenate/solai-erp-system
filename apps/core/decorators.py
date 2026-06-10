from functools import wraps

from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


def tenant_permission_required(perm):
    """
    Decorator for views that checks whether a user has a particular permission,
    raising PermissionDenied (which yields HTTP 403) if they don't.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect("login")
            if not request.user.has_perm(perm):
                raise PermissionDenied("Você não tem permissão para acessar esta página.")
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator
