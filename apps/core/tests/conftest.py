import pytest
from django.test import Client


@pytest.fixture
def client():
    """Les tests du socle sans entreprise passent par l'hôte de la vitrine (localhost)."""
    return Client(HTTP_HOST="localhost")
