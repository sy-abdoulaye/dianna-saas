from django.db import models

from apps.core.models import TenantModel


class Tag(TenantModel):
    name = models.CharField(max_length=30)


class Badge(TenantModel):
    site = models.OneToOneField("core.Site", on_delete=models.CASCADE, null=True)
    tags = models.ManyToManyField(Tag, related_name="badges")


class Owned(TenantModel):
    """Objet qui a à la fois `employee` et `author` : le propriétaire est celui déclaré."""

    employee = models.ForeignKey(
        "people.Employee", on_delete=models.CASCADE, null=True, related_name="+"
    )
    author = models.ForeignKey(
        "people.Employee", on_delete=models.CASCADE, null=True, related_name="+"
    )
    permission_owner_field = "author"


class Undeclared(TenantModel):
    employee = models.ForeignKey("people.Employee", on_delete=models.CASCADE, related_name="+")
