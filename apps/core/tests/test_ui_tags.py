import pytest
from django import forms
from django.template import Context, Template, TemplateSyntaxError


def render(source, **context):
    return Template("{% load ui %}" + source).render(Context(context))


def test_icon_is_decorative_by_default():
    html = render('{% icon "home" %}')
    assert 'aria-hidden="true"' in html
    assert "sprite.svg#i-home" in html


def test_icon_with_label_is_announced():
    html = render('{% icon "search" 16 label="Rechercher" %}')
    assert 'role="img"' in html and 'aria-label="Rechercher"' in html
    assert "ic-sm" in html


def test_button_variants_and_icon_only_label():
    html = render(
        '{% button "Modifier" variant="secondary" icon="edit" icon_only=True size="sm" %}'
    )
    assert 'class="btn btn-secondary btn-sm btn-icon"' in html
    assert 'aria-label="Modifier"' in html
    assert 'type="button"' in html
    assert "<span>Modifier</span>" not in html


def test_button_with_hx_post_is_protected_against_double_submit():
    html = render('{% button "Valider" variant="primary" hx_post="/x/" hx_swap="none" %}')
    assert 'hx-post="/x/"' in html
    assert 'hx-disabled-elt="this"' in html


def test_button_link_and_loading_state():
    assert render('{% button "Voir" href="/a/" %}').startswith("<a")
    html = render('{% button "Envoi" variant="primary" loading=True %}')
    assert "is-loading" in html and "disabled" in html and 'aria-busy="true"' in html


def test_button_attributes_are_escaped_even_for_template_literals():
    html = render("""{% button "Succès" hx_post="/t/" hx_vals='{"kind": "ok"}' %}""")
    assert 'hx-vals="{&quot;kind&quot;: &quot;ok&quot;}"' in html
    html = render('{% button "X" data_info=value %}', value='" onmouseover="alert(1)')
    assert 'onmouseover="' not in html


def test_unknown_button_variant_is_refused():
    with pytest.raises(TemplateSyntaxError):
        render('{% button "X" variant="rainbow" %}')


def test_button_escapes_label():
    assert "<script>" not in render("{% button label %}", label="<script>alert(1)</script>")


class SampleForm(forms.Form):
    email = forms.EmailField(label="E-mail", help_text="Pour se connecter.")
    service = forms.ChoiceField(label="Service", choices=[("", "Choisir"), ("a", "A")])


def test_control_links_hint_and_error_to_the_field():
    form = SampleForm(data={"email": "faux"})
    form.is_valid()
    html = render("{% control form.email %}", form=form)
    assert 'aria-invalid="true"' in html
    assert 'aria-describedby="id_email-hint id_email-error"' in html
    assert "is-invalid" in html and "required" in html


def test_field_component_renders_label_star_and_error_message():
    form = SampleForm(data={"email": "faux"})
    form.is_valid()
    html = render('{% include "components/field.html" with field=form.email %}', form=form)
    assert '<label class="label" for="id_email">' in html
    assert 'class="req" aria-hidden="true"' in html
    assert 'id="id_email-error"' in html
    assert 'id="id_email-hint"' in html


def test_select_is_wrapped_for_its_chevron():
    html = render("{% control form.service %}", form=SampleForm())
    assert html.startswith('<span class="select-wrap"><select')


def test_form_errors_summary_counts_fields():
    form = SampleForm(data={})
    form.is_valid()
    html = render('{% include "components/form_errors.html" %}', form=form)
    assert "2 informations sont à corriger." in html
    assert 'role="alert"' in html


def test_form_errors_summary_singular():
    form = SampleForm(data={"service": "a"})
    form.is_valid()
    html = render('{% include "components/form_errors.html" %}', form=form)
    assert "1 information est à corriger." in html


def test_initials():
    assert render("{{ name|initials }}", name="Hélène Faure") == "HF"
    assert render("{{ name|initials }}", name="") == "?"


def test_kpi_uses_native_progress_element():
    html = render(
        '{% include "components/kpi.html" with label="Campagne" value="40 %" progress=40 %}'
    )
    assert '<progress class="progress" max="100" value="40"' in html
    assert "style=" not in html
