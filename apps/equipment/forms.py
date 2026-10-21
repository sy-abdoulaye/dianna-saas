"""Formulaires du matériel (docs/modules/07-materiel.md). Les contrôles qui dépendent des
autres données (numéro de série déjà pris, équipement déjà attribué) sont faits par les
services, sous verrou (A3-02)."""

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.approvals.forms import RequestForm
from apps.equipment.models import EquipmentKind
from apps.people.models import IN_POST_STATUSES, Employee


class EquipmentRequestForm(RequestForm):
    kind = forms.ChoiceField(label=_("Équipement"), choices=EquipmentKind.choices)
    reason = forms.CharField(
        label=_("Motif"),
        widget=forms.Textarea(attrs={"rows": 3}),
        max_length=1000,
        error_messages={"required": _("Indiquez le motif de la demande.")},
    )

    def model_data(self):
        return {"kind": self.cleaned_data["kind"], "reason": self.cleaned_data["reason"]}


class ItemForm(forms.Form):
    kind = forms.ChoiceField(label=_("Type"), choices=EquipmentKind.choices)
    model = forms.CharField(
        label=_("Modèle"), max_length=120, error_messages={"required": _("Indiquez le modèle.")}
    )
    serial_number = forms.CharField(
        label=_("N° de série"),
        max_length=60,
        widget=forms.TextInput(attrs={"placeholder": _("Ex. DN-01400")}),
        error_messages={"required": _("Indiquez le numéro de série.")},
    )

    def clean_serial_number(self):
        # Sans espaces ni différence de casse (L5-09) ; l'unicité est vérifiée par le service.
        return "".join(self.cleaned_data["serial_number"].split()).upper()


class AssignForm(forms.Form):
    employee = forms.ModelChoiceField(
        label=_("Collaborateur"),
        queryset=Employee.objects.none(),
        empty_label=_("Choisir…"),
        error_messages={
            "required": _("Choisissez un collaborateur."),
            "invalid_choice": _("Choisissez un collaborateur."),
        },
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = Employee.objects.filter(
            status__in=IN_POST_STATUSES
        ).order_by("last_name", "first_name")


class StockChoiceForm(forms.Form):
    """« Attribuer un équipement » depuis une demande validée : stock du type demandé."""

    item = forms.ModelChoiceField(
        label=_("Équipement en stock"),
        queryset=None,
        empty_label=_("Choisir…"),
        error_messages={
            "required": _("Choisissez un équipement."),
            "invalid_choice": _("Choisissez un équipement."),
        },
    )

    def __init__(self, *args, kind, **kwargs):
        from apps.equipment.models import EquipmentItem

        super().__init__(*args, **kwargs)
        self.fields["item"].queryset = EquipmentItem.objects.filter(
            kind=kind, status=EquipmentItem.Status.IN_STOCK
        )
        self.fields["item"].label_from_instance = lambda i: f"{i.model} · {i.serial_number}"


class IssueForm(forms.Form):
    description = forms.CharField(
        label=_("Que se passe-t-il ?"),
        widget=forms.Textarea(attrs={"rows": 3}),
        max_length=2000,
        error_messages={"required": _("Décrivez le problème.")},
    )


class CloseIssueForm(forms.Form):
    resolution = forms.CharField(
        label=_("Résolution"),
        widget=forms.Textarea(attrs={"rows": 3}),
        max_length=2000,
        error_messages={"required": _("Indiquez la résolution.")},
    )
