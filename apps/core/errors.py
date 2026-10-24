"""Erreur métier commune des services : un message à afficher et, au besoin, le champ du
formulaire concerné. Les applications en dérivent leur propre erreur."""


class ServiceError(Exception):
    def __init__(self, message, field=None):
        super().__init__(str(message))
        self.message = message
        self.field = field
