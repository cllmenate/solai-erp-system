import pytest
from django.template import Context, Template


@pytest.mark.django_db
def test_design_tokens_render():
    template = Template('{% include "components/tokens.html" %}')
    context = Context({})
    rendered = template.render(context)
    assert "<style>" in rendered
    assert "--ds-transition-normal" in rendered


@pytest.mark.django_db
@pytest.mark.parametrize("variant,expected_class", [
    ("primary", "bg-brand-500"),
    ("secondary", "bg-slate-200"),
    ("danger", "bg-rose-500"),
    ("ghost", "bg-transparent"),
    ("outline", "border-slate-300"),
])
def test_btn_component_variants(variant, expected_class):
    template = Template('{% include "components/btn.html" with variant=variant label="Clique Aqui" %}')
    context = Context({"variant": variant})
    rendered = template.render(context)
    assert "Clique Aqui" in rendered
    assert expected_class in rendered


@pytest.mark.django_db
def test_input_component_rendering():
    template = Template('{% include "components/input.html" with name="username" label="Nome de Usuário" error="Campo obrigatório" %}')
    context = Context({})
    rendered = template.render(context)
    assert "Nome de Usuário" in rendered
    assert "Campo obrigatório" in rendered
    assert 'name="username"' in rendered
    assert "border-rose-500" in rendered


@pytest.mark.django_db
def test_card_component_rendering():
    template = Template('{% include "components/card.html" with title="Meu Card" card_body="<p>Conteúdo</p>" %}')
    context = Context({})
    rendered = template.render(context)
    assert "Meu Card" in rendered
    assert "Conteúdo" in rendered


@pytest.mark.django_db
@pytest.mark.parametrize("variant,expected_class", [
    ("success", "bg-emerald-50"),
    ("warning", "bg-amber-50"),
    ("danger", "bg-rose-50"),
    ("info", "bg-sky-50"),
])
def test_badge_component_variants(variant, expected_class):
    template = Template('{% include "components/badge.html" with variant=variant label="Status" %}')
    context = Context({"variant": variant})
    rendered = template.render(context)
    assert "Status" in rendered
    assert expected_class in rendered


@pytest.mark.django_db
def test_table_component_rendering():
    headers = ["Coluna 1", "Coluna 2"]
    rows_html = "<tr><td>Dado 1</td><td>Dado 2</td></tr>"
    template = Template('{% include "components/table.html" with headers=headers rows_html=rows_html %}')
    context = Context({"headers": headers, "rows_html": rows_html})
    rendered = template.render(context)
    assert "Coluna 1" in rendered
    assert "Dado 1" in rendered


@pytest.mark.django_db
def test_modal_component_rendering():
    template = Template('{% include "components/modal.html" with id="my-modal" title="Confirmar" modal_body="<p>Corpo</p>" %}')
    context = Context({})
    rendered = template.render(context)
    assert 'id="my-modal"' in rendered
    assert "Confirmar" in rendered
    assert "Corpo" in rendered


@pytest.mark.django_db
def test_alert_component_rendering():
    template = Template('{% include "components/alert.html" with type="success" message="Sucesso!" %}')
    context = Context({})
    rendered = template.render(context)
    assert "Sucesso!" in rendered
    assert "bg-emerald-50" in rendered
