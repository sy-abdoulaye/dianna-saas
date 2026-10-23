"""Champs de formulaire communs.

Nombres décimaux (L5-20) : un champ texte avec `inputmode="decimal"` (clavier numérique sur
mobile), jamais `type="number"`, qui refuse la virgule selon la langue du navigateur. Le
serveur accepte la virgule et le point (« 2,15 » et « 2.15 » donnent 2,15) et refuse tout
autre format avec un message qui montre un exemple."""

import re
from decimal import Decimal

from django import forms

DECIMAL_TEXT = re.compile(r"^\d{1,6}(?:[.,]\d+)?$")


class DecimalTextField(forms.Field):
    """Décimal saisi en texte. `format_message` : « Saisissez un montant comme 84,10. »."""

    def __init__(self, *, format_message, decimal_places=2, **kwargs):
        self.format_message = format_message
        self.decimal_places = decimal_places
        kwargs.setdefault(
            "widget",
            forms.TextInput(attrs={"inputmode": "decimal", "autocomplete": "off"}),
        )
        super().__init__(**kwargs)

    def to_python(self, value):
        if value in self.empty_values:
            return None
        text = "".join(str(value).split())  # espaces (y compris insécables) ignorés
        if not DECIMAL_TEXT.match(text):
            raise forms.ValidationError(self.format_message, code="format")
        number = Decimal(text.replace(",", "."))
        if -number.as_tuple().exponent > self.decimal_places:
            raise forms.ValidationError(self.format_message, code="format")
        return number

    def prepare_value(self, value):
        # Valeur initiale affichée à la française : 84.10 → « 84,10 ».
        if isinstance(value, Decimal):
            return str(value).replace(".", ",")
        return value
