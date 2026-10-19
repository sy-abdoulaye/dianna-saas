from django.apps import AppConfig


class TenancyTestConfig(AppConfig):
    """Modèles réservés aux tests : relations un-à-un et plusieurs-à-plusieurs entre objets
    métier, que le lot 1 n'a pas encore."""

    name = "tests.tenancy_app"
    label = "tenancy_test"
