import re

from django import forms
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.files import clean_image
from apps.core.models import Service, Site
from apps.people.models import ContractType, Employee, EmployeeStatus, Role, WorkTime
from apps.people.services import would_loop

PHONE_RE = re.compile(r"^[0-9 +().-]{8,}$")
PHOTO_MAX_BYTES = 2 * 1024 * 1024
REQUIRED = _("Ce champ est obligatoire.")
INVALID_EMAIL = _("L'adresse n'est pas valide (exemple : prenom.nom@exemple.fr).")


class EmployeeForm(forms.ModelForm):
    """Fiche en page complète (RH, Admin). Le profil d'accès et l'invitation sont réservés à
    l'administrateur (`can_assign_role`)."""

    photo_upload = forms.FileField(
        label=_("Photo"),
        required=False,
        help_text=_("JPG ou PNG, 2 Mo maximum. Sans photo, les initiales sont affichées."),
        widget=forms.ClearableFileInput(attrs={"accept": "image/png,image/jpeg"}),
    )
    remove_photo = forms.BooleanField(label=_("Retirer la photo"), required=False)
    invite = forms.BooleanField(
        label=_("Envoyer une invitation par e-mail"), required=False, initial=True
    )

    class Meta:
        model = Employee
        fields = [
            "first_name",
            "last_name",
            "email",
            "phone",
            "office",
            "job_title",
            "service",
            "site",
            "manager",
            "arrival_date",
            "contract_type",
            "work_time",
            "registration_number",
            "role",
        ]
        labels = {
            "phone": _("Téléphone professionnel"),
            "job_title": _("Intitulé du poste"),
            "contract_type": _("Type de contrat"),
            "registration_number": _("Matricule"),
        }
        help_texts = {"role": _("Détermine ce que la personne voit et peut faire.")}
        widgets = {"arrival_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}
        error_messages = {"email": {"invalid": INVALID_EMAIL}}

    def __init__(self, *args, can_assign_role=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.can_assign_role = can_assign_role
        for name in (
            "first_name",
            "last_name",
            "email",
            "job_title",
            "service",
            "site",
            "arrival_date",
        ):
            self.fields[name].required = True
        for field in self.fields.values():
            field.error_messages.setdefault("required", REQUIRED)
            field.error_messages["required"] = REQUIRED
        # Querysets posés ici (jamais au niveau de la classe) : entreprise courante.
        self.fields["service"].queryset = Service.objects.order_by(Lower("name"))
        self.fields["site"].queryset = Site.objects.order_by(Lower("name"))
        self.fields["service"].empty_label = _("Choisir…")
        self.fields["site"].empty_label = _("Choisir…")
        managers = Employee.objects.exclude(status=EmployeeStatus.LEFT).order_by(
            "last_name", "first_name"
        )
        if self.instance.pk:
            managers = managers.exclude(pk=self.instance.pk)
        self.fields["manager"].queryset = managers
        self.fields["manager"].empty_label = _("Aucun")
        self.fields["contract_type"].choices = [("", _("Choisir…")), *ContractType.choices]
        self.fields["work_time"].choices = [("", _("Choisir…")), *WorkTime.choices]
        if not can_assign_role:
            del self.fields["role"]
            del self.fields["invite"]
        elif self.instance.pk:
            del self.fields["invite"]
        if not self.instance.photo:
            del self.fields["remove_photo"]

    def clean_email(self):
        email = self.cleaned_data["email"].strip()
        duplicate = (
            Employee.objects.annotate(email_ci=Lower("email"))
            .filter(email_ci=email.lower())
            .exclude(pk=self.instance.pk)
            .first()
        )
        if duplicate:
            raise forms.ValidationError(
                _("Cette adresse est déjà utilisée par %(name)s.") % {"name": duplicate.full_name}
            )
        return email

    def clean_registration_number(self):
        number = self.cleaned_data.get("registration_number", "").strip()
        if number and (
            Employee.objects.filter(registration_number=number)
            .exclude(pk=self.instance.pk)
            .exists()
        ):
            raise forms.ValidationError(_("Ce matricule est déjà utilisé."))
        return number

    def clean_manager(self):
        manager = self.cleaned_data.get("manager")
        if manager is not None and would_loop(self.instance, manager):
            raise forms.ValidationError(_("Ce choix créerait une boucle dans la hiérarchie."))
        return manager

    def clean_photo_upload(self):
        upload = self.cleaned_data.get("photo_upload")
        if not upload:
            return None
        return clean_image(upload, max_bytes=PHOTO_MAX_BYTES, max_side=512)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("invite") and cleaned.get("email"):
            from apps.accounts.services import EMAIL_TAKEN, email_is_taken

            if email_is_taken(cleaned["email"]):
                self.add_error("email", EMAIL_TAKEN)
        return cleaned

    def model_data(self) -> dict:
        """Valeurs à enregistrer (sans la photo ni l'invitation)."""
        return {
            name: self.cleaned_data[name] for name in self._meta.fields if name in self.cleaned_data
        }


class ContactForm(forms.Form):
    """« Modifier mes coordonnées » : téléphone et bureau seulement."""

    phone = forms.CharField(label=_("Téléphone professionnel"), max_length=30)
    office = forms.CharField(label=_("Bureau"), max_length=60, required=False)

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        if not PHONE_RE.match(phone):
            raise forms.ValidationError(_("Saisissez un numéro valide (au moins 8 chiffres)."))
        return phone


class ArchiveForm(forms.Form):
    departure_date = forms.DateField(
        label=_("Date de départ"),
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        initial=timezone.localdate,
    )


STATUS_IN_POST, STATUS_LEFT, STATUS_ALL = "en_poste", "partis", "tous"


class DirectoryFilterForm(forms.Form):
    q = forms.CharField(
        label=_("Recherche"),
        required=False,
        widget=forms.TextInput(
            attrs={"type": "search", "placeholder": _("Nom, poste, service ou e-mail")}
        ),
    )
    service = forms.ModelChoiceField(
        # Queryset réel posé dans __init__ (entreprise courante) ; jamais au niveau de la classe.
        label=_("Service"),
        required=False,
        queryset=Service.all_companies.none(),
        empty_label=_("Tous les services"),
    )
    site = forms.ModelChoiceField(
        label=_("Site"),
        required=False,
        queryset=Site.all_companies.none(),
        empty_label=_("Tous les sites"),
    )
    statut = forms.ChoiceField(
        label=_("Statut"),
        required=False,
        choices=[
            (STATUS_IN_POST, _("En poste")),
            (STATUS_LEFT, _("Partis")),
            (STATUS_ALL, _("Tous")),
        ],
    )

    def __init__(self, *args, show_status=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["service"].queryset = Service.objects.order_by(Lower("name"))
        self.fields["site"].queryset = Site.objects.order_by(Lower("name"))
        if not show_status:
            del self.fields["statut"]


class ImportUploadForm(forms.Form):
    file = forms.FileField(
        label=_("Fichier CSV"),
        help_text=_(
            "Colonnes : prenom;nom;email;poste;service;site;manager_email;date_arrivee;contrat. "
            "Séparateur point-virgule, UTF-8, 1 000 lignes au maximum."
        ),
        widget=forms.ClearableFileInput(attrs={"accept": ".csv,text/csv"}),
    )


ROLE_CHOICES = Role.choices
