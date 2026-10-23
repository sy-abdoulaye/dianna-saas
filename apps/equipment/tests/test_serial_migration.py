"""Migration des numéros de série (L5-09) : doublons après normalisation renommés."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db(transaction=True)

BEFORE = [("equipment", "0001_initial")]
AFTER = [("equipment", "0002_serial_normalized")]


def migrate(targets):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(targets)
    return executor.loader.project_state(targets).apps


def test_duplicates_after_normalization_get_a_suffix_and_are_logged(company_a, capsys):
    old_apps = migrate(BEFORE)
    item_model = old_apps.get_model("equipment", "EquipmentItem")
    for serial in ("AB 123", "ab123", "ＡＢ１２３"):
        item_model.objects.create(
            company_id=company_a.company.pk, kind="laptop", model="X", serial_number=serial
        )
    try:
        new_apps = migrate(AFTER)
        items = new_apps.get_model("equipment", "EquipmentItem").objects.filter(
            company_id=company_a.company.pk, serial_number__startswith="AB"
        )
        assert sorted(items.values_list("serial_number", flat=True)) == [
            "AB123",
            "AB123-DOUBLON-2",
            "AB123-DOUBLON-3",
        ]
        assert items.order_by("pk").first().serial_number == "AB123"  # le premier garde
        log = new_apps.get_model("core", "AuditLog").objects.get(
            company_id=company_a.company.pk, action="equipment.serials_deduplicated"
        )
        assert "ab123 → AB123-DOUBLON-2" in log.summary
        assert "AB123-DOUBLON-3" in capsys.readouterr().out
    finally:
        migrate(AFTER)
