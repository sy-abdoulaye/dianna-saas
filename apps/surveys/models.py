"""Questionnaires (docs/modules/09-questionnaires.md), avec anonymat réel (M-10).

Qui a répondu (`SurveyReceipt`) et ce qui a été répondu (`SurveyResponse`, `Answer`) sont
stockés sans aucune clé commune. Les réponses héritent de `TenantBase` : ni horodatage ni
clé séquentielle (clé UUID4 aléatoire), pour qu'aucun champ ne permette de les ranger dans
l'ordre des reçus. Risque résiduel en base (ordre physique des lignes, numéro de
transaction) : L1-09."""

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import Module, TenantBase, TenantModel

# Seuil d'anonymat (L6-17) : à 3, deux répondants qui comparent leurs réponses déduisent
# celles du troisième ; 5 laisse au moins trois inconnus à toute paire de complices.
DEFAULT_THRESHOLD = 5
TITLE_MAX = 120
QUESTION_MAX = 300
MAX_SCALE_QUESTIONS = 20
COMMENT_MAX = 1000
TEXT_ANSWER_MAX = 2000


class Survey(TenantModel):
    class Audience(models.TextChoices):
        ALL = "all", _("Tous les salariés")
        MANAGERS = "managers", _("Managers")
        NEW_HIRES = "new_hires", _("Arrivés depuis moins d'un an")

    class Status(models.TextChoices):
        DRAFT = "draft", _("Brouillon")
        OPEN = "open", _("Ouvert")
        CLOSED = "closed", _("Clos")

    module = Module.SURVEYS
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    title = models.CharField(_("titre"), max_length=TITLE_MAX)
    audience = models.CharField(_("public"), max_length=10, choices=Audience, default=Audience.ALL)
    due_date = models.DateField(_("échéance"), null=True, blank=True)
    status = models.CharField(_("statut"), max_length=10, choices=Status, default=Status.DRAFT)
    created_by = models.ForeignKey(
        "people.Employee",
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
        verbose_name=_("créé par"),
    )
    published_at = models.DateTimeField(_("publié le"), null=True, blank=True)
    closed_at = models.DateTimeField(_("clos le"), null=True, blank=True)
    anonymity_threshold = models.PositiveSmallIntegerField(
        _("seuil d'anonymat"), default=DEFAULT_THRESHOLD
    )

    class Meta:
        verbose_name = _("questionnaire")
        verbose_name_plural = _("questionnaires")
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(anonymity_threshold__gte=DEFAULT_THRESHOLD),
                name="surveys_threshold_at_least_5",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["draft", "open", "closed"]),
                name="surveys_status_valid",
            ),
        ]

    def __str__(self):
        return self.title


class Question(TenantModel):
    class Kind(models.TextChoices):
        SCALE = "scale", _("Note de 1 à 5")
        TEXT = "text", _("Réponse libre")

    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="questions")
    order = models.PositiveSmallIntegerField(_("ordre"))
    kind = models.CharField(_("type"), max_length=5, choices=Kind)
    label = models.CharField(_("libellé"), max_length=QUESTION_MAX)

    class Meta:
        verbose_name = _("question")
        verbose_name_plural = _("questions")
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(fields=["survey", "order"], name="surveys_question_order")
        ]

    def __str__(self):
        return self.label


class SurveyInvitation(TenantModel):
    """Public figé à la publication (L6-04) : droit de répondre, bandeau « à remplir » et
    calcul de la participation. Ne dit rien de qui a répondu."""

    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="invitations")
    employee = models.ForeignKey("people.Employee", on_delete=models.CASCADE, related_name="+")

    class Meta:
        verbose_name = _("personne invitée")
        verbose_name_plural = _("personnes invitées")
        constraints = [
            models.UniqueConstraint(fields=["survey", "employee"], name="surveys_invited_once")
        ]


class SurveyReceipt(TenantModel):
    """Reçu : sert uniquement à empêcher une seconde réponse. Jamais affiché, à aucun profil :
    ni liste de répondants ni liste de non-répondants (L6-01)."""

    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="receipts")
    employee = models.ForeignKey("people.Employee", on_delete=models.CASCADE, related_name="+")

    class Meta:
        verbose_name = _("reçu de réponse")
        verbose_name_plural = _("reçus de réponse")
        constraints = [
            models.UniqueConstraint(fields=["survey", "employee"], name="surveys_answer_once")
        ]


class SurveyResponse(TenantBase):
    """Une réponse anonyme : aucun lien vers la personne ni vers son reçu, aucune date."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="responses")

    class Meta(TenantBase.Meta):
        verbose_name = _("réponse anonyme")
        verbose_name_plural = _("réponses anonymes")


class Answer(TenantBase):
    """Réponse à une question : note (et commentaire facultatif) ou texte libre."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    response = models.ForeignKey(SurveyResponse, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="answers")
    score = models.PositiveSmallIntegerField(_("note"), null=True, blank=True)
    text = models.TextField(_("réponse libre"), blank=True)
    comment = models.TextField(_("commentaire"), blank=True)

    class Meta(TenantBase.Meta):
        verbose_name = _("réponse à une question")
        verbose_name_plural = _("réponses aux questions")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(score__isnull=True) | models.Q(score__gte=1, score__lte=5),
                name="surveys_score_1_to_5",
            ),
            models.UniqueConstraint(
                fields=["response", "question"], name="surveys_one_answer_per_question"
            ),
        ]
