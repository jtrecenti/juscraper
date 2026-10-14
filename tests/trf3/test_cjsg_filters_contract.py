"""Filter-propagation contract for TRF3 ``cjsg``.

Every public filter must reach the POST body of ``Home/ResultadoTotais``. The
expected bodies below are literal dicts, not calls to ``build_cjsg_payload``,
so a regression in the builder itself also fails here. Field shapes follow
the portal's own form: the ``hdn*`` fields carry the filter text
(``((NOME)).rel.``, ``(CLASSE).dclas.``, ``(ORGAO).org.``) and the dropdown IDs
stay ``"0"``, because the server ignores them. The órgão goes as the pair
the browser sends for the chosen dropdown option: its label in ``hdnOrgao``
and its indexed name (``data-val-jef``) in ``hdnOrgaoJef``, which the server
ORs together. The dropdown comes from the tab sample served on the opening
GET.
"""
from __future__ import annotations

import pandas as pd
import pytest
import responses
from pydantic import ValidationError
from responses.registries import OrderedRegistry

import juscraper as jus
from tests._helpers import assert_unknown_kwarg_raises
from tests.trf3._cjsg_mock import add_page, add_search


def _body(**campos: str) -> dict[str, str]:
    """POST body of the portal with every field empty or at its default."""
    body = {
        "txtPesquisaLivre": "",
        "chkAcordaos": "on",
        "chkMostrarLista": "on",
        "opcaoQtdePagina": "10",
        "numero": "",
        "magistrado": "0",
        "data_inicial": "",
        "data_final": "",
        "data_tipo": "1",
        "classe": "0",
        "orgao": "0",
        "ementa": "",
        "indexacao": "",
        "hdnMagistrado": "",
        "hdnClasse": "",
        "hdnOrgao": "",
        "hdnOrgaoJef": "",
    }
    body.update(campos)
    return body


@responses.activate(registry=OrderedRegistry)
def test_cjsg_all_filters_land_in_post_body(mocker):
    """All filters of the acórdãos base at once, each in its form field."""
    mocker.patch("time.sleep")
    add_search(
        _body(
            txtPesquisaLivre="medicamento",
            opcaoQtdePagina="50",
            numero="5001743-27.2026.4.03.0000",
            data_inicial="01/01/2026",
            data_final="30/06/2026",
            data_tipo="1",
            ementa="fornecimento",
            indexacao="saude",
            hdnMagistrado="((NERY JUNIOR)).rel.",
            hdnClasse="(AI - AGRAVO DE INSTRUMENTO).dclas.",
            hdnOrgao="(3ª Turma).org.",
            hdnOrgaoJef="(TERCEIRA TURMA).org.",
        ),
        "no_results.html",
    )

    df = jus.scraper("trf3").cjsg(
        "medicamento",
        paginas=1,
        base="acordaos",
        numero_processo="5001743-27.2026.4.03.0000",
        relator="NERY JUNIOR",
        classe="AI - AGRAVO DE INSTRUMENTO",
        orgao_julgador="3ª Turma",
        ementa="fornecimento",
        indexacao="saude",
        data_julgamento_inicio="2026-01-01",
        data_julgamento_fim="2026-06-30",
        tamanho_pagina=50,
    )

    assert isinstance(df, pd.DataFrame)


@responses.activate(registry=OrderedRegistry)
def test_cjsg_data_publicacao_usa_data_tipo_zero(mocker):
    """``data_publicacao_*`` fills the same date pair with ``data_tipo=0``."""
    mocker.patch("time.sleep")
    add_search(
        _body(txtPesquisaLivre="medicamento", data_inicial="01/01/2026", data_final="30/06/2026", data_tipo="0"),
        "no_results.html",
    )

    jus.scraper("trf3").cjsg(
        "medicamento", paginas=1,
        data_publicacao_inicio="01/01/2026", data_publicacao_fim="30/06/2026",
    )


@pytest.mark.parametrize(
    ("base", "indice", "caixas"),
    [
        ("turmas_recursais", 1, {}),
        ("monocraticas", 2, {"in_juizado_trf3": "on"}),
        ("monocraticas_turmas_recursais", 2, {"in_juizado_recursal": "on"}),
    ],
)
@responses.activate(registry=OrderedRegistry)
def test_cjsg_base_escolhe_aba_e_caixas(mocker, base, indice, caixas):
    """The base opens ``home/index/{n}``; monocráticas add exactly one origin box."""
    mocker.patch("time.sleep")
    body = _body(txtPesquisaLivre="medicamento", hdnMagistrado="((FULANO)).rel.", **caixas)
    add_search(body, "no_results.html", base=base)

    jus.scraper("trf3").cjsg("medicamento", paginas=1, base=base, relator="FULANO")

    assert responses.calls[0].request.url.endswith(f"/jurisprudencia/home/index/{indice}")


def test_cjsg_datas_de_julgamento_e_publicacao_juntas_levanta():
    with pytest.raises(ValueError, match="um só tipo de data"):
        jus.scraper("trf3").cjsg(
            "medicamento",
            data_julgamento_inicio="2026-01-01", data_julgamento_fim="2026-06-30",
            data_publicacao_inicio="2026-01-01", data_publicacao_fim="2026-06-30",
        )


@pytest.mark.parametrize("filtro", ["orgao_julgador", "ementa", "indexacao"])
@pytest.mark.parametrize("base", ["monocraticas", "monocraticas_turmas_recursais"])
def test_cjsg_monocraticas_recusam_filtros_sem_campo(filtro, base):
    with pytest.raises(ValueError, match=filtro):
        jus.scraper("trf3").cjsg("medicamento", base=base, **{filtro: "x"})


def test_cjsg_sem_criterio_levanta():
    with pytest.raises(ValueError, match="informe pesquisa"):
        jus.scraper("trf3").cjsg("   ")


def test_cjsg_base_invalida_levanta_validation_error():
    with pytest.raises(ValidationError, match="base"):
        jus.scraper("trf3").cjsg("medicamento", base="sumulas")


def test_cjsg_tamanho_pagina_invalido_levanta_validation_error():
    with pytest.raises(ValidationError, match="tamanho_pagina"):
        jus.scraper("trf3").cjsg("medicamento", tamanho_pagina=20)


def test_cjsg_unknown_kwarg_raises():
    assert_unknown_kwarg_raises(jus.scraper("trf3").cjsg, "kwarg_inventado", "medicamento", paginas=1)


def test_cjsg_download_unknown_kwarg_raises():
    assert_unknown_kwarg_raises(jus.scraper("trf3").cjsg_download, "kwarg_inventado", "medicamento", paginas=1)


@pytest.mark.parametrize("alias", ["query", "termo"])
@responses.activate(registry=OrderedRegistry)
def test_cjsg_alias_de_pesquisa_emite_deprecation(mocker, alias):
    mocker.patch("time.sleep")
    add_search(_body(txtPesquisaLivre="medicamento"), "no_results.html")

    with pytest.warns(DeprecationWarning, match=f"{alias}.*deprecado"):
        jus.scraper("trf3").cjsg(paginas=1, **{alias: "medicamento"})


@responses.activate(registry=OrderedRegistry)
def test_cjsg_alias_data_inicio_vira_data_de_julgamento(mocker):
    mocker.patch("time.sleep")
    add_search(
        _body(txtPesquisaLivre="medicamento", data_inicial="01/01/2026", data_final="30/06/2026", data_tipo="1"),
        "no_results.html",
    )

    with pytest.warns(DeprecationWarning, match=r"'data_(inicio|fim)' está deprecado") as avisos:
        jus.scraper("trf3").cjsg("medicamento", paginas=1, data_inicio="2026-01-01", data_fim="2026-06-30")

    mensagens = [str(w.message) for w in avisos]
    assert any("data_inicio" in m and "deprecado" in m for m in mensagens)
    assert any("data_fim" in m and "deprecado" in m for m in mensagens)


@responses.activate(registry=OrderedRegistry)
def test_cjsg_alias_data_julgamento_de_ate(mocker):
    mocker.patch("time.sleep")
    add_search(
        _body(txtPesquisaLivre="medicamento", data_inicial="01/01/2026", data_final="30/06/2026", data_tipo="1"),
        "no_results.html",
    )

    with pytest.warns(DeprecationWarning, match=r"'data_julgamento_(de|ate)' está deprecado") as avisos:
        jus.scraper("trf3").cjsg(
            "medicamento", paginas=1, data_julgamento_de="2026-01-01", data_julgamento_ate="2026-06-30",
        )

    mensagens = [str(w.message) for w in avisos]
    assert any("data_julgamento_de" in m for m in mensagens)
    assert any("data_julgamento_ate" in m for m in mensagens)


@responses.activate(registry=OrderedRegistry)
def test_cjsg_alias_data_publicacao_de_ate(mocker):
    mocker.patch("time.sleep")
    add_search(
        _body(txtPesquisaLivre="medicamento", data_inicial="01/01/2026", data_final="30/06/2026", data_tipo="0"),
        "no_results.html",
    )

    with pytest.warns(DeprecationWarning, match=r"'data_publicacao_(de|ate)' está deprecado") as avisos:
        jus.scraper("trf3").cjsg(
            "medicamento", paginas=1, data_publicacao_de="2026-01-01", data_publicacao_ate="2026-06-30",
        )

    mensagens = [str(w.message) for w in avisos]
    assert any("data_publicacao_de" in m for m in mensagens)
    assert any("data_publicacao_ate" in m for m in mensagens)


@responses.activate(registry=OrderedRegistry)
def test_cjsg_download_alias_query(mocker):
    """``cjsg_download`` runs the same pipeline as ``cjsg``."""
    mocker.patch("time.sleep")
    add_search(_body(txtPesquisaLivre="medicamento"), "no_results.html")

    with pytest.warns(DeprecationWarning, match="query.*deprecado"):
        brutos = jus.scraper("trf3").cjsg_download(query="medicamento", paginas=1)

    assert isinstance(brutos, list)
    assert len(brutos) == 1


@pytest.mark.parametrize(
    ("base", "orgao", "rotulo", "nome_indexado"),
    [
        ("acordaos", "3ª Turma", "3ª Turma", "TERCEIRA TURMA"),
        ("acordaos", "TERCEIRA TURMA", "3ª Turma", "TERCEIRA TURMA"),
        ("acordaos", "  terceira   turma ", "3ª Turma", "TERCEIRA TURMA"),
        ("acordaos", "QUINTA TURMA", "5ª Turma", "QUINTA TURMA"),
        ("acordaos", "QUINTA TURMA - 1A. SEÇÃO", "5ª Turma", "QUINTA TURMA - 1A"),
        ("acordaos", "QUINTA TURMA - 1a.  seção", "5ª Turma", "QUINTA TURMA - 1A"),
        ("acordaos", "QUINTA TURMA - 1A", "5ª Turma", "QUINTA TURMA - 1A"),
        ("acordaos", "TURMA SUPLEMENTAR DA PRIMEIRA SEÇÃO", "TURMA SUPLEMENTAR DA PRIMEIRA SEÇÃO",
         "TURMA SUPLEMENTAR DA PRIMEIRA SEÇÃO"),
        ("turmas_recursais", "11ª Turma Recursal da Seção Judiciária de São Paulo",
         "11ª Turma Recursal da Seção Judiciária de São Paulo", "11ª TURMA RECURSAL DE SÃO PAULO"),
        ("turmas_recursais", "11ª turma recursal de são paulo",
         "11ª Turma Recursal da Seção Judiciária de São Paulo", "11ª TURMA RECURSAL DE SÃO PAULO"),
    ],
)
@responses.activate(registry=OrderedRegistry)
def test_cjsg_orgao_manda_o_par_da_opcao_do_dropdown(mocker, base, orgao, rotulo, nome_indexado):
    """Label or indexed name selects one dropdown option; both fields come from it.

    Matching ignores case and spacing and applies the form's ``1a. seção`` ->
    ``1A`` rewrite on both sides, so the column value of old acórdãos
    (``QUINTA TURMA - 1A. SEÇÃO``) and the indexed form (``QUINTA TURMA - 1A``)
    select the option whose ``data-val-jef`` is ``QUINTA TURMA - 1a. SEÇÃO``.
    Measured on the portal with "medicamento": the pair finds 576 documents
    for ``QUINTA TURMA``, the label alone 443, the indexed name alone 133.
    """
    mocker.patch("time.sleep")
    add_search(
        _body(txtPesquisaLivre="medicamento", hdnOrgao=f"({rotulo}).org.", hdnOrgaoJef=f"({nome_indexado}).org."),
        "no_results.html",
        base=base,
    )

    jus.scraper("trf3").cjsg("medicamento", paginas=1, base=base, orgao_julgador=orgao)


@responses.activate(registry=OrderedRegistry)
def test_cjsg_orgao_rotulo_ambiguo_levanta_sem_buscar(mocker):
    """``5ª Turma`` labels two options; the error lists the indexed names to pick from."""
    mocker.patch("time.sleep")
    add_search(_body(txtPesquisaLivre="medicamento"), "no_results.html")

    with pytest.raises(ValueError, match="ambíguo") as exc_info:
        jus.scraper("trf3").cjsg("medicamento", paginas=1, orgao_julgador="5ª Turma")

    mensagem = str(exc_info.value)
    assert "'QUINTA TURMA'" in mensagem
    assert "'QUINTA TURMA - 1a. SEÇÃO'" in mensagem
    assert len(responses.calls) == 1


@responses.activate(registry=OrderedRegistry)
def test_cjsg_orgao_sem_opcao_vai_como_esta_e_avisa(mocker, caplog):
    """Text that matches no option keeps going in both fields, with an info log."""
    mocker.patch("time.sleep")
    esperado = "(TURMA QUE NAO EXISTE).org."
    add_search(_body(txtPesquisaLivre="medicamento", hdnOrgao=esperado, hdnOrgaoJef=esperado), "no_results.html")

    with caplog.at_level("INFO", logger="juscraper.trf3.cjsg"):
        jus.scraper("trf3").cjsg("medicamento", paginas=1, orgao_julgador="TURMA QUE NAO EXISTE")

    assert "não corresponde a nenhuma opção do formulário" in caplog.text


@pytest.mark.parametrize(
    ("datas", "data_tipo"),
    [
        ({"data_julgamento_inicio": "2026-01-01", "data_julgamento_fim": "2026-06-30"}, "1"),
        ({"data_publicacao_inicio": "2026-01-01", "data_publicacao_fim": "2026-06-30"}, "0"),
    ],
)
@responses.activate(registry=OrderedRegistry)
def test_cjsg_so_datas_sem_pesquisa_e_criterio_valido(mocker, datas, data_tipo):
    """A date range alone is a search criterion, as in the portal's form."""
    mocker.patch("time.sleep")
    add_search(_body(data_inicial="01/01/2026", data_final="30/06/2026", data_tipo=data_tipo), "no_results.html")

    df = jus.scraper("trf3").cjsg(paginas=1, **datas)

    assert df.empty
    assert len(responses.calls) == 3


@responses.activate(registry=OrderedRegistry)
def test_cjsg_tamanho_pagina_chega_ao_payload_e_a_conta_de_paginas(mocker):
    """``tamanho_pagina=50`` with 591 hits is 12 pages: 11 GETs after the POST.

    The total (591) comes from the sample; with 10 per page the client would
    ask for 60 pages, so a client that forwards the default instead of the
    chosen size requests ``np=13`` and finds no mock.
    """
    mocker.patch("time.sleep")
    add_search(_body(txtPesquisaLivre="medicamento", opcaoQtdePagina="50"), "results_normal_page_01.html")
    for pagina in range(2, 13):
        add_page(pagina, "results_normal_page_02.html")

    brutos = jus.scraper("trf3").cjsg_download("medicamento", tamanho_pagina=50, paginas=None)

    assert len(brutos) == 12
    pedidas = [c.request.params.get("np") for c in responses.calls if "ListaResumida/2" in c.request.url]
    assert pedidas == [str(n) for n in range(2, 13)]
