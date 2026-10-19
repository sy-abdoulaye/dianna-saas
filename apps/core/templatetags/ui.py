"""Balises du design system (docs/05-design-system.md).

{% load ui %}
{% icon "home" %}                               icône 20 px décorative
{% icon "search" size=16 label="Rechercher" %}  icône porteuse de sens
{% button "Envoyer la demande" variant="primary" icon="send" type="submit" %}
{% button "Fermer" variant="ghost" icon="x" icon_only=True size="sm" data_modal_close=True %}
{% status_badge "request" obj.status %}
{% control form.email %}                        widget avec classes et attributs ARIA
"""

from django import forms, template
from django.forms.utils import flatatt
from django.templatetags.static import static
from django.utils.html import conditional_escape, escape, format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from apps.core.status import get_status

register = template.Library()

ICON_SIZES = {16: "ic-sm", 20: "", 24: "ic-lg", 28: "ic-xl"}
BUTTON_VARIANTS = {"primary", "secondary", "ghost", "danger"}


def _attr_name(key: str) -> str:
    # hx_post → hx-post, data_modal_close → data-modal-close, aria_label → aria-label
    return key.replace("_", "-")


def _extra_attrs(kwargs: dict) -> dict:
    """Attributs hx-*, data-* et aria-*. Les valeurs sont toujours échappées, même si elles
    sont marquées sûres (chaîne littérale d'un gabarit) : une valeur JSON comme
    hx_vals='{"kind": "ok"}' ne doit jamais pouvoir fermer l'attribut."""
    attrs = {}
    for key, value in kwargs.items():
        if not key.startswith(("hx_", "data_", "aria_")) or value in (None, False, ""):
            continue
        attrs[_attr_name(key)] = True if value is True else escape(str(value))
    return attrs


def render_icon(name: str, size: int = 20, label: str = "", css: str = ""):
    """Icône du sprite Lucide. Décorative par défaut (aria-hidden) ; avec `label`, elle est
    annoncée (role="img" + aria-label)."""
    classes = " ".join(c for c in ("ic", ICON_SIZES.get(int(size), ""), css) if c)
    href = f"{static('icons/sprite.svg')}#i-{name}"
    if label:
        return format_html(
            '<svg class="{}" role="img" aria-label="{}" focusable="false">'
            '<use href="{}"></use></svg>',
            classes,
            escape(str(label)),
            href,
        )
    return format_html(
        '<svg class="{}" aria-hidden="true" focusable="false"><use href="{}"></use></svg>',
        classes,
        href,
    )


@register.simple_tag(name="icon")
def icon_tag(name: str, size: int = 20, label: str = "", css: str = ""):
    return render_icon(name, size, label, css)


@register.simple_tag
def brand_mark(size: int = 28):
    return format_html(
        '<svg class="brand-mark" width="{0}" height="{0}" aria-hidden="true" focusable="false">'
        '<use href="{1}#mark"></use></svg>',
        int(size),
        static("icons/sprite.svg"),
    )


@register.inclusion_tag("components/button.html")
def button(
    label: str,
    variant: str = "secondary",
    icon: str = "",
    icon_only: bool = False,
    size: str = "",
    type: str = "button",
    href: str = "",
    name: str = "",
    value: str = "",
    disabled: bool = False,
    loading: bool = False,
    block: bool = False,
    id: str = "",
    css: str = "",
    **kwargs,
):
    """Bouton du design system. `variant` : primary, secondary, ghost, danger ; `size="sm"`.
    Un bouton icône seule (`icon_only`) porte son libellé en aria-label. Les arguments
    hx_*, data_* et aria_* deviennent des attributs (hx_post → hx-post)."""
    if variant not in BUTTON_VARIANTS:
        raise template.TemplateSyntaxError(f"Variante de bouton inconnue : {variant}")
    classes = ["btn", f"btn-{variant}"]
    if size == "sm":
        classes.append("btn-sm")
    if icon_only:
        classes.append("btn-icon")
    if block:
        classes.append("btn-block")
    if loading:
        classes.append("is-loading")
    if css:
        classes.append(css)
    attrs = {"class": " ".join(classes)}
    if id:
        attrs["id"] = id
    if icon_only:
        attrs["aria-label"] = escape(str(label))
    attrs.update(_extra_attrs(kwargs))
    if "hx-post" in attrs or "hx-delete" in attrs:
        # Pas de double envoi : le bouton est désactivé pendant la requête.
        attrs.setdefault("hx-disabled-elt", "this")
    if loading:
        attrs["aria-busy"] = "true"
    is_link = bool(href) and not disabled
    if is_link:
        attrs["href"] = conditional_escape(href)
    else:
        if name:
            attrs["name"] = name
            attrs["value"] = value
        if disabled or loading:
            attrs["disabled"] = True
    return {
        "is_link": is_link,
        "type": type,
        "attrs": flatatt(attrs),
        "icon": icon,
        "icon_size": 16 if size == "sm" else 20,
        "label": label,
        "icon_only": icon_only,
    }


@register.inclusion_tag("components/status_badge.html")
def status_badge(domain: str, value: str, label: str = ""):
    status = get_status(domain, value)
    return {"kind": status.kind, "label": label or status.label}


@register.simple_tag
def control(bound_field, **kwargs):
    """Rend le widget d'un champ avec les classes du design system et les attributs
    d'accessibilité : aria-invalid et aria-describedby (aide et message d'erreur)."""
    widget = bound_field.field.widget
    attrs = {}
    if isinstance(widget, (forms.Select, forms.SelectMultiple)):
        attrs["class"] = "select"
    elif isinstance(widget, (forms.CheckboxInput, forms.RadioSelect, forms.FileInput)):
        attrs["class"] = ""
    else:
        attrs["class"] = "input"
    described = []
    if bound_field.help_text:
        described.append(f"{bound_field.auto_id}-hint")
    if bound_field.errors:
        attrs["class"] += " is-invalid"
        attrs["aria-invalid"] = "true"
        described.append(f"{bound_field.auto_id}-error")
    if described:
        attrs["aria-describedby"] = " ".join(described)
    if bound_field.field.required:
        attrs["required"] = True
    attrs.update(_extra_attrs(kwargs))
    css = kwargs.get("css")
    if css:
        attrs["class"] = f"{attrs['class']} {css}".strip()
    if not attrs["class"]:
        del attrs["class"]
    html = bound_field.as_widget(attrs=attrs)
    if isinstance(widget, forms.Select) and not isinstance(widget, forms.SelectMultiple):
        return format_html('<span class="select-wrap">{}</span>', html)
    return html


@register.filter
def private_url(field_file) -> str:
    """URL signée d'un fichier privé (logo sur la page de connexion, photo déjà autorisée)."""
    from apps.core.files import signed_url

    return signed_url(field_file) if field_file else ""


@register.filter
def initials(person) -> str:
    """Initiales d'une personne (objet avec first_name et last_name, ou chaîne « Prénom Nom »)."""
    if not person:
        return "?"
    if isinstance(person, str):
        parts = person.split()
        first, last = (parts[0], parts[-1]) if len(parts) > 1 else (person, "")
    else:
        first, last = getattr(person, "first_name", ""), getattr(person, "last_name", "")
    return ((first[:1] + last[:1]) or "?").upper()


@register.filter
def error_count(form) -> int:
    """Nombre d'informations à corriger : champs en erreur + erreurs générales."""
    if not form.errors:
        return 0
    fields = sum(1 for name in form.errors if name != "__all__")
    return fields + (1 if form.non_field_errors() else 0)


@register.inclusion_tag("components/pagination.html", takes_context=True)
def pagination(context, page_obj, target: str = "#results"):
    """Pagination « 1 à 8 sur 24 » avec numéros et ellipses. Les liens conservent les filtres
    de l'URL et mettent à jour la zone `target` par HTMX (hx-push-url : bouton Retour)."""
    paginator = page_obj.paginator
    numbers = list(paginator.get_elided_page_range(page_obj.number, on_each_side=1, on_ends=1))
    return {
        "request": context.get("request"),
        "page_obj": page_obj,
        "numbers": numbers,
        "ellipsis": paginator.ELLIPSIS,
        "target": target,
        "first": page_obj.start_index() if paginator.count else 0,
        "last": page_obj.end_index() if paginator.count else 0,
    }


THEME_OPTIONS = (
    ("light", _("Clair"), "sun"),
    ("dark", _("Sombre"), "moon"),
    ("system", _("Système"), "monitor"),
)


@register.inclusion_tag("components/segmented.html")
def theme_switch(save_url: str = ""):
    """Choix Clair / Sombre / Système (menu utilisateur). ui.js l'applique, le mémorise dans le
    navigateur et, avec `save_url`, l'enregistre dans User.theme."""
    if save_url:
        attrs = format_html('data-theme-switch data-theme-url="{}"', save_url)
    else:
        attrs = mark_safe("data-theme-switch")
    return {
        "name": "theme",
        "legend": _("Thème"),
        "options": THEME_OPTIONS,
        "selected": "system",
        "data_attr": attrs,
    }
