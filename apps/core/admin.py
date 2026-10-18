"""Administration éditeur (T-22) : servie uniquement sur admin.<BASE_DOMAIN>.

Elle crée les entreprises, active les modules et invite le premier administrateur. Elle
n'affiche aucune donnée métier (fiches, demandes, journal) : l'accès support tracé arrive
au lot 8."""

from django import forms
from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _

from apps.core import services
from apps.core.models import Company, CompanyModule
from apps.core.tenancy import tenant_context


class CompanyCreationForm(forms.ModelForm):
    admin_first_name = forms.CharField(label=_("Prénom du premier administrateur"), max_length=60)
    admin_last_name = forms.CharField(label=_("Nom du premier administrateur"), max_length=60)
    admin_email = forms.EmailField(label=_("E-mail du premier administrateur"))

    class Meta:
        model = Company
        fields = ["name", "slug"]

    def clean_admin_email(self):
        from apps.accounts.services import EMAIL_TAKEN, email_is_taken

        email = self.cleaned_data["admin_email"]
        if email_is_taken(email):
            raise forms.ValidationError(EMAIL_TAKEN)
        return email


class CompanyModuleInline(admin.TabularInline):
    model = CompanyModule
    fields = ["module", "enabled"]
    readonly_fields = ["module"]
    extra = 0
    can_delete = False

    def get_queryset(self, request):
        return CompanyModule.all_companies.all()

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "status", "created_at"]
    list_filter = ["status"]
    search_fields = ["name", "slug"]
    fields = [
        "name",
        "slug",
        "status",
        "telework_max_per_week",
        "telework_auto_approve",
        "summer_leave_hr_step",
    ]

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            kwargs["form"] = CompanyCreationForm
            kwargs["fields"] = None
        return super().get_form(request, obj, **kwargs)

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return [
                (None, {"fields": ["name", "slug"]}),
                (
                    _("Premier administrateur (reçoit une invitation par e-mail)"),
                    {"fields": ["admin_first_name", "admin_last_name", "admin_email"]},
                ),
            ]
        return [(None, {"fields": self.fields})]

    def get_inlines(self, request, obj):
        return [CompanyModuleInline] if obj is not None else []

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        company = Company.objects.filter(pk=object_id).first() if object_id else None
        if company is None:
            return super().changeform_view(request, object_id, form_url, extra_context)
        # Les validations des modules (contraintes d'unicité) passent par TenantManager.
        with tenant_context(company):
            response = super().changeform_view(request, object_id, form_url, extra_context)
            # Rendu immédiat : la réponse différée lirait les modules hors du contexte.
            if hasattr(response, "render"):
                response.render()
            return response

    def save_model(self, request, obj, form, change):
        if change:
            super().save_model(request, obj, form, change)
            return
        company, _admin, _token = services.create_company(
            name=form.cleaned_data["name"],
            slug=form.cleaned_data["slug"],
            admin_first_name=form.cleaned_data["admin_first_name"],
            admin_last_name=form.cleaned_data["admin_last_name"],
            admin_email=form.cleaned_data["admin_email"],
            request=request,
        )
        obj.pk = company.pk
        messages.success(request, _("Invitation envoyée au premier administrateur."))

    def save_formset(self, request, form, formset, change):
        # Activation et désactivation des modules : journalisées dans l'espace du client.
        for inline_form in formset.forms:
            if inline_form.has_changed():
                row = inline_form.instance
                services.set_module(form.instance, row.module, row.enabled, request=request)


admin.site.site_header = _("Dianna · administration éditeur")
admin.site.site_title = _("Dianna éditeur")
admin.site.index_title = _("Entreprises clientes")
