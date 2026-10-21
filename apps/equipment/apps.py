from django.apps import AppConfig


class EquipmentConfig(AppConfig):
    name = "apps.equipment"
    label = "equipment"
    verbose_name = "Matériel"

    def ready(self):
        """Les demandes de matériel passent par le moteur commun (L5-04)."""
        from django.utils.translation import gettext_lazy as _

        from apps.approvals import forms, kinds
        from apps.equipment.forms import EquipmentRequestForm
        from apps.equipment.models import EquipmentRequest

        kinds.register_kind(
            kinds.Kind(
                "equipment",
                EquipmentRequest,
                _("Demandes de matériel"),
                _("matériel"),
                _("Équipements remis aux collaborateurs"),
                _("Demander du matériel"),
                "laptop",
                _("Demande"),
                "equipment:home",
                todo_tab="demandes",
            )
        )
        kinds.SUMMARIES["equipment"] = lambda request: (
            f"{request.get_kind_display()} · {request.reason[:80]}"
        )
        forms.FORMS["equipment"] = EquipmentRequestForm
