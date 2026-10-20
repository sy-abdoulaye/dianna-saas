from datetime import timedelta

import pytest
from django.utils import timezone

from apps.approvals import workflow
from apps.approvals.models import LeaveRequest, OnCallDeclaration, TeleworkRequest
from apps.core.tenancy import tenant_context


def next_weekday(offset_days=7, weekday=0):
    """Un jour ouvré à venir (lundi de la semaine suivante par défaut)."""
    today = timezone.localdate()
    monday = today + timedelta(days=7 - today.weekday())
    return monday + timedelta(days=weekday + offset_days - 7)


@pytest.fixture
def submit():
    """submit(company_data, employee, model, **data) dans l'entreprise de la fiche."""

    def _submit(company_data, employee, model=TeleworkRequest, **data):
        if model is TeleworkRequest:
            data.setdefault("date", next_weekday(weekday=2))
        if model is LeaveRequest:
            data.setdefault(
                "start", company_data.requests["campaign"].period_start + timedelta(days=30)
            )
            data.setdefault("end", data["start"] + timedelta(days=9))
            data.setdefault("campaign", company_data.requests["campaign"])
        if model is OnCallDeclaration:
            data.setdefault("start", next_weekday())
            data.setdefault("end", data["start"] + timedelta(days=6))
        with tenant_context(company_data.company):
            return workflow.submit(model, employee, data)

    return _submit
