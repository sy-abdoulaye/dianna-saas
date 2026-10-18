from django.contrib.staticfiles.apps import StaticFilesConfig as BaseStaticFilesConfig


class StaticFilesConfig(BaseStaticFilesConfig):
    """La source Tailwind (static/css/app.css) n'est pas servie : seule la feuille compilée
    static/build/app.css est collectée."""

    ignore_patterns = [*BaseStaticFilesConfig.ignore_patterns, "css/app.css"]
