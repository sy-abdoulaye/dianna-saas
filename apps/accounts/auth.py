"""Connexion liée à l'hôte : un compte ne se connecte que sur le sous-domaine de son
entreprise, et l'administration éditeur n'accepte que l'équipe Dianna (T-09, T-22)."""

from allauth.account.auth_backends import AuthenticationBackend

from apps.core.middleware import PLATFORM, PUBLIC, TENANT


def user_can_use_host(user, request) -> bool:
    if user is None or not user.is_active or request is None:
        return False
    kind = getattr(request, "host_kind", None)
    if kind == TENANT:
        employee = getattr(user, "employee", None)
        return (
            employee is not None
            and employee.company_id == request.company.pk
            and employee.can_sign_in
        )
    if kind == PLATFORM:
        return user.is_staff
    if kind == PUBLIC:
        from django.conf import settings

        return settings.DEBUG and user.is_staff  # /editeur/ en développement (L0-13)
    return False


class HostAwareBackend(AuthenticationBackend):
    def authenticate(self, request, **credentials):
        user = super().authenticate(request, **credentials)
        if user is not None and not user_can_use_host(user, request):
            # Même réponse qu'un mauvais mot de passe : ne révèle pas l'existence du compte.
            return None
        return user
