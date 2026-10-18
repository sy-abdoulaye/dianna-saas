import pytest
from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError

pytestmark = pytest.mark.django_db
User = get_user_model()


def test_user_logs_in_with_email_and_email_is_normalized():
    user = User.objects.create_user("  Camille.Durand@Exemple.FR ", "demo-dianna-2026")
    assert user.email == "camille.durand@exemple.fr"
    assert user.check_password("demo-dianna-2026")
    assert not user.is_staff and not user.is_superuser and not user.is_platform_staff
    assert authenticate(username="CAMILLE.DURAND@exemple.fr", password="demo-dianna-2026") == user


def test_email_is_unique_regardless_of_case():
    User.objects.create_user("louise.martin@exemple.fr", "x" * 12)
    with pytest.raises(IntegrityError):
        User.objects.create(email="Louise.Martin@exemple.fr")


def test_superuser_is_platform_staff():
    admin = User.objects.create_superuser("equipe@dianna.fr", "x" * 12)
    assert admin.is_staff and admin.is_superuser and admin.is_platform_staff


def test_email_is_required():
    with pytest.raises(ValueError):
        User.objects.create_user("", "x" * 12)


def test_theme_defaults_to_system():
    assert User.objects.create_user("a@b.fr", "x" * 12).theme == "system"
