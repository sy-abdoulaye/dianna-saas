import pytest
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory
from django.views import View

from apps.core import access
from apps.core.models import CompanyModule, Module
from apps.core.tenancy import tenant_context


@pytest.fixture
def make_request(company_a):
    def _make(employee):
        request = RequestFactory().get("/", HTTP_HOST="exemple.localhost")
        request.company = company_a.company
        request.employee = employee
        request.user = employee.user
        request.resolver_match = None
        return request

    return _make


def ok_view(request):
    return HttpResponse("ok")


def test_permission_required(make_request, company_a):
    view = access.permission_required("admin.manage")(ok_view)
    assert view(make_request(company_a.admin)).status_code == 200
    with pytest.raises(PermissionDenied):
        view(make_request(company_a.employee))


def test_module_required_shows_the_disabled_page(make_request, company_a):
    view = access.module_required(Module.TELEWORK)(ok_view)
    with tenant_context(company_a.company):
        assert view(make_request(company_a.employee)).status_code == 200
        CompanyModule.objects.filter(module=Module.TELEWORK).update(enabled=False)
        response = view(make_request(company_a.employee))
    assert response.status_code == 403
    assert "Module désactivé" in response.content.decode()
    assert "Un administrateur peut le réactiver." in response.content.decode()


def test_mixin_checks_module_then_permission(make_request, company_a):
    class AdminView(access.PermissionRequiredMixin, View):
        permission = "admin.manage"
        module = Module.SURVEYS

        def get(self, request):
            return HttpResponse("ok")

    with tenant_context(company_a.company):
        assert AdminView.as_view()(make_request(company_a.admin)).status_code == 200
        with pytest.raises(PermissionDenied):
            AdminView.as_view()(make_request(company_a.employee))
        CompanyModule.objects.filter(module=Module.SURVEYS).update(enabled=False)
        assert AdminView.as_view()(make_request(company_a.admin)).status_code == 403


def test_403_page_names_the_profile_and_uses_the_app_layout(make_request, company_a):
    from apps.core.views import permission_denied

    with tenant_context(company_a.company):  # posé par CompanyMiddleware en temps normal
        page = permission_denied(make_request(company_a.employee))
    assert page.status_code == 403
    content = page.content.decode()
    assert "Votre profil (Salarié) ne permet pas" in content
    assert 'id="side"' in content  # mise en page de l'application (utilisateur connecté)
