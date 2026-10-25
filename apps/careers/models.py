"""Carrière et évaluations (docs/modules/10-carriere.md).

Un entretien suit ses étapes dans un ordre propre à son type (STEPS) ; un seul entretien en
cours par personne et par type, garanti en base. Les notes de suivi privées ne sont visibles
que par leur auteur (`author`), y compris pour les RH : le propriétaire au sens des
permissions reste la personne suivie (`employee`), la confidentialité est appliquée par un
seul sélecteur (selectors.visible_notes).
"""

import uuid

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _

from apps.core.models import TenantModel

TEXT_MAX = 5000  # longueur maximale d'un texte saisi (borne aussi les exports PDF)


class ReviewKind(models.TextChoices):
    INDIVIDUAL = "individual", _("Entretien individuel")
    # Loi n° 2025-989 du 24 octobre 2025 : l'entretien professionnel devient l'entretien de
    # parcours professionnel (article L6315-1 du Code du travail, M-08).
    PROFESSIONAL = "professional", _("Entretien de parcours professionnel")


class ReviewReason(models.TextChoices):
    """Motif d'un entretien de parcours professionnel (M-08)."""

    PERIODIC = "periodic", _("Périodique")
    RETURN = "return", _("Retour d'absence")
    MID_CAREER = "mid_career", _("Mi-carrière")
    END_CAREER = "end_career", _("Fin de carrière")
    SUMMARY = "summary", _("État des lieux")


class ReviewStep(models.TextChoices):
    SELF = "self", _("Auto-évaluation")
    MANAGER = "manager", _("Évaluation du manager")
    MEETING = "meeting", _("Entretien")
    SIGNATURE = "signature", _("Signatures")
    CLOSED = "closed", _("Clos")


STEPS = {
    ReviewKind.INDIVIDUAL: (
        ReviewStep.SELF,
        ReviewStep.MANAGER,
        ReviewStep.MEETING,
        ReviewStep.SIGNATURE,
    ),
    ReviewKind.PROFESSIONAL: (
        ReviewStep.SELF,
        ReviewStep.MEETING,
        ReviewStep.MANAGER,
        ReviewStep.SIGNATURE,
    ),
}

# Libellés des étapes de l'entretien de parcours, différents de l'entretien individuel.
PROFESSIONAL_STEP_LABELS = {
    ReviewStep.SELF: _("Préparation du salarié"),
    ReviewStep.MANAGER: _("Compte rendu"),
}


class ReviewCampaign(TenantModel):
    label = models.CharField(_("libellé"), max_length=80)
    start = models.DateField(_("début"))
    end = models.DateField(_("fin"))

    class Meta:
        verbose_name = _("campagne d'entretiens")
        verbose_name_plural = _("campagnes d'entretiens")
        ordering = ["-start"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end__gte=F("start")), name="careers_campaign_end_after_start"
            )
        ]

    def __str__(self):
        return self.label


class Competency(TenantModel):
    """Compétence évaluée en entretien individuel, paramétrée par l'entreprise. Une compétence
    désactivée garde ses notes passées et n'est plus demandée."""

    name = models.CharField(_("nom"), max_length=80)
    description = models.CharField(_("description"), max_length=160, blank=True)
    order = models.PositiveSmallIntegerField(_("ordre"), default=0)
    active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("compétence")
        verbose_name_plural = _("compétences")
        ordering = ["order", "pk"]
        constraints = [
            models.UniqueConstraint(
                Lower("name"), "company", name="careers_competency_name_ci_unique"
            )
        ]

    def __str__(self):
        return self.name


class Review(TenantModel):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    campaign = models.ForeignKey(
        ReviewCampaign,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="reviews",
        verbose_name=_("campagne"),
    )
    employee = models.ForeignKey(
        "people.Employee",
        on_delete=models.RESTRICT,
        related_name="reviews",
        verbose_name=_("collaborateur"),
    )
    # Manager copié au lancement (fiche 10) : s'il n'est plus en poste ou plus le manager de
    # la personne, les RH agissent (selectors.acting_manager).
    manager = models.ForeignKey(
        "people.Employee",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("manager"),
    )
    launched_by = models.ForeignKey(
        "people.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("lancé par"),
    )
    kind = models.CharField(_("type"), max_length=12, choices=ReviewKind)
    reason = models.CharField(_("motif"), max_length=12, choices=ReviewReason, blank=True)
    step = models.CharField(_("étape"), max_length=10, choices=ReviewStep, default=ReviewStep.SELF)
    meeting_date = models.DateField(_("date de l'entretien"), null=True, blank=True)
    meeting_place = models.CharField(_("lieu"), max_length=120, blank=True)
    held_at = models.DateTimeField(_("réalisé le"), null=True, blank=True)
    self_summary = models.TextField(_("bilan du salarié"), max_length=TEXT_MAX, blank=True)
    self_project = models.TextField(_("projet professionnel"), max_length=TEXT_MAX, blank=True)
    manager_summary = models.TextField(_("bilan du manager"), max_length=TEXT_MAX, blank=True)
    strengths = models.TextField(_("points forts"), max_length=TEXT_MAX, blank=True)
    improvements = models.TextField(_("axes de progrès"), max_length=TEXT_MAX, blank=True)
    report = models.TextField(_("compte rendu"), max_length=TEXT_MAX, blank=True)
    # État des lieux récapitulatif (motif « état des lieux », M-08) : trois critères.
    summary_training = models.BooleanField(_("au moins une action de formation"), null=True)
    summary_certification = models.BooleanField(_("une certification"), null=True)
    summary_progression = models.BooleanField(
        _("une progression salariale ou professionnelle"), null=True
    )
    next_review_due = models.DateField(_("prochain entretien de parcours"), null=True, blank=True)
    next_summary_due = models.DateField(_("prochain état des lieux"), null=True, blank=True)
    employee_comment = models.TextField(
        _("commentaire du salarié"), max_length=TEXT_MAX, blank=True
    )
    employee_signed_at = models.DateTimeField(_("signé par le salarié le"), null=True, blank=True)
    manager_signed_at = models.DateTimeField(_("signé côté manager le"), null=True, blank=True)
    manager_signed_by = models.ForeignKey(
        "people.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("signé côté manager par"),
    )
    signed_by_hr = models.BooleanField(_("signé par les RH à la place du manager"), default=False)
    closed_at = models.DateTimeField(_("clos le"), null=True, blank=True)
    permission_owner_field = "employee"

    class Meta:
        verbose_name = _("entretien")
        verbose_name_plural = _("entretiens")
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "employee", "kind"],
                condition=~Q(step="closed"),
                name="careers_one_open_review_per_kind",
            ),
            models.CheckConstraint(
                condition=Q(kind="individual", reason="")
                | (Q(kind="professional") & ~Q(reason="")),
                name="careers_reason_matches_kind",
            ),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} · {self.employee}"

    @property
    def steps(self) -> tuple[str, ...]:
        return STEPS[ReviewKind(self.kind)]

    def step_label(self, step: str | None = None) -> str:
        step = step or self.step
        if self.kind == ReviewKind.PROFESSIONAL and step in PROFESSIONAL_STEP_LABELS:
            return str(PROFESSIONAL_STEP_LABELS[ReviewStep(step)])
        return str(ReviewStep(step).label)

    @property
    def step_index(self) -> int:
        return len(self.steps) if self.step == ReviewStep.CLOSED else self.steps.index(self.step)

    @property
    def step_number(self) -> int:
        """Étape affichée (« Étape 2 sur 4 ») ; un entretien clos est à la dernière."""
        return min(self.step_index + 1, len(self.steps))

    @property
    def is_closed(self) -> bool:
        return self.step == ReviewStep.CLOSED

    @property
    def is_summary(self) -> bool:
        return self.reason == ReviewReason.SUMMARY


class ReviewRating(TenantModel):
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="ratings")
    competency = models.ForeignKey(Competency, on_delete=models.RESTRICT, related_name="+")
    score = models.PositiveSmallIntegerField(
        _("note"), validators=[MinValueValidator(1), MaxValueValidator(4)]
    )

    class Meta:
        ordering = ["competency__order", "competency__pk"]
        constraints = [
            models.UniqueConstraint(fields=["review", "competency"], name="careers_rating_unique"),
            models.CheckConstraint(
                condition=Q(score__gte=1, score__lte=4), name="careers_rating_score_range"
            ),
        ]


class ReviewObjective(TenantModel):
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="objectives")
    order = models.PositiveSmallIntegerField(_("ordre"), default=0)
    title = models.CharField(_("objectif"), max_length=200)
    due_date = models.DateField(_("échéance"))
    result = models.TextField(_("résultat"), max_length=TEXT_MAX, blank=True)

    class Meta:
        ordering = ["order", "pk"]


class ReviewTraining(TenantModel):
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="trainings")
    order = models.PositiveSmallIntegerField(_("ordre"), default=0)
    label = models.CharField(_("formation"), max_length=200)

    class Meta:
        ordering = ["order", "pk"]


class FollowUpNote(TenantModel):
    class Kind(models.TextChoices):
        FOLLOW_UP = "follow_up", _("Point de suivi")
        WISH = "wish", _("Souhait salarié")
        TRAINING = "training", _("Formation")
        REVIEW = "review", _("Entretien")

    employee = models.ForeignKey(
        "people.Employee",
        on_delete=models.RESTRICT,
        related_name="follow_up_notes",
        verbose_name=_("collaborateur"),
    )
    author = models.ForeignKey(
        "people.Employee",
        on_delete=models.RESTRICT,
        related_name="+",
        verbose_name=_("auteur"),
    )
    date = models.DateField(_("date"))
    kind = models.CharField(_("type"), max_length=10, choices=Kind)
    text = models.TextField(_("note"), max_length=TEXT_MAX)
    # Visible par son seul auteur, y compris pour les RH (docs/04-permissions.md).
    is_private = models.BooleanField(_("note privée"), default=False)
    review = models.ForeignKey(
        Review, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    permission_owner_field = "employee"

    class Meta:
        verbose_name = _("note de suivi")
        verbose_name_plural = _("notes de suivi")
        ordering = ["-date", "-pk"]

    def __str__(self):
        return f"{self.get_kind_display()} · {self.employee}"
