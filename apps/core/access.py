"""Contrôle d'accès des vues (règle 2 de CLAUDE.md).

- Entreprise : TenantManager filtre déjà ; un objet d'une autre entreprise donne 404.
- Profil : `permission_required` / PermissionRequiredMixin → 403 « Accès non autorisé ».
- Module : `module_required` → page « Module désactivé ».
Masquer un bouton dans un gabarit ne suffit jamais : chaque vue appelle ces contrôles.
"""

from functools import wraps

from django.core.exceptions import PermissionDenied

from apps.core import permissions
from apps.core.models import CompanyModule, Module


def enabled_modules(request) -> set[str]:
    """Modules activés de l'entreprise courante, mis en cache sur la requête."""
    cached = getattr(request, "_enabled_modules", None)
    if cached is None:
        if getattr(request, "company", None) is None:
            cached = set()
        else:
            disabled = set(
                CompanyModule.objects.filter(enabled=False).values_list("module", flat=True)
            )
            cached = set(Module.values) - disabled
        request._enabled_modules = cached
    return cached


def module_is_enabled(request, module: str) -> bool:
    return module in enabled_modules(request)


def require(request, action: str, obj=None):
    employee = getattr(request, "employee", None)
    if employee is None or not permissions.can(employee, action, obj):
        raise PermissionDenied
    return employee


def permission_required(action: str):
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            require(request, action)
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def module_required(module: str):
    from apps.core.views import module_disabled

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not module_is_enabled(request, module):
                return module_disabled(request, Module(module).label)
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


class PermissionRequiredMixin:
    """Vues de classe : `permission = "people.manage"` ; `module = "telework"` (facultatif).
    Le contrôle objet se fait dans get_object() avec `require(request, action, obj)`."""

    permission: str | None = None
    module: str | None = None

    def dispatch(self, request, *args, **kwargs):
        if self.module and not module_is_enabled(request, self.module):
            from apps.core.views import module_disabled

            return module_disabled(request, Module(self.module).label)
        if self.permission:
            require(request, self.permission)
        return super().dispatch(request, *args, **kwargs)
