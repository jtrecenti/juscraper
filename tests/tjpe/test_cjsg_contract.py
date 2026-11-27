"""Offline contract tests for TJPE cjsg.

TJPE's cjsg flow is JSF/RichFaces-based and spans **three different
XHTML endpoints** under ``/consultajurisprudenciaweb/xhtml/consulta/``:

1. ``GET consulta.xhtml`` — extracts the JSF ``ViewState``.
2. ``POST consulta.xhtml`` — search submission. The response is either
   the *escolha* page (chooser between Acordaos and Decisoes
   Monocraticas, when ``tipo_decisao="todos"`` enables both checkboxes)
   or the results page directly (when a single ``tipo_decisao`` is
   selected).
3. ``POST escolhaResultado.xhtml`` — only used when escolha is shown:
   picks the result type and returns results page 1.
4. ``POST resultado.xhtml`` — RichFaces AJAX pagination
   (``AJAXREQUEST=_viewRoot``). Response is XML wrapping HTML inside a
   ``<![CDATA[...]]>`` block; the parser unwraps it.

Because the same URL (``consulta.xhtml``) serves both the GET and the
POST that returns either escolha or results, and the scraper threads
the ``ViewState`` between requests, the contract uses
``OrderedRegistry`` so each ``responses.add`` call matches the next
request in sequence.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import pytest
import responses
from responses.registries import OrderedRegistry

import juscraper as jus
from juscraper.courts.tjpe.download import BASE_URL
from tests._helpers import load_sample, urlencoded_body_subset_matcher, urls_enviadas
from tests.tjpe.test_cjsg_pagination_unit import resultado_sem_cabecalho_com_aviso_na_ementa

CONSULTA_URL = f"{BASE_URL}/consulta.xhtml"
ESCOLHA_URL = f"{BASE_URL}/escolhaResultado.xhtml"
RESULTADO_URL = f"{BASE_URL}/resultado.xhtml"

CJSG_MIN_COLUMNS = {
    "processo", "classe", "assunto", "relator", "orgao_julgador",
    "data_julgamento", "data_publicacao", "ementa",
}

_SAMPLES_DIR = Path(__file__).parent / "samples" / "cjsg"
pytestmark = pytest.mark.skipif(
    not (_SAMPLES_DIR / "step_01_consulta.html").exists(),
    reason=(
        "TJPE samples ainda nao capturados — rode "
        "`python -m tests.fixtures.capture.tjpe` para popular "
        "tests/tjpe/samples/cjsg/."
    ),
)


def _add_get_consulta() -> None:
    """Initial GET on consulta.xhtml (carries ViewState the scraper extracts)."""
    responses.add(
        responses.GET,
        CONSULTA_URL,
        body=load_sample("tjpe", "cjsg/step_01_consulta.html"),
        status=200,
        content_type="text/html; charset=UTF-8",
    )


def _add_post_consulta(sample_path: str) -> None:
    """POST on consulta.xhtml — returns escolha page, results page, or zero hits."""
    _add_post_consulta_html(load_sample("tjpe", sample_path))


def _add_post_consulta_html(body: str) -> None:
    """POST on consulta.xhtml answered with ``body`` (a sample changed by the test)."""
    responses.add(
        responses.POST,
        CONSULTA_URL,
        body=body,
        status=200,
        content_type="text/html; charset=UTF-8",
    )


def _add_post_escolha(sample_path: str, *, match=None) -> None:
    """POST on escolhaResultado.xhtml — picks result type, returns results page 1."""
    responses.add(
        responses.POST,
        ESCOLHA_URL,
        body=load_sample("tjpe", sample_path),
        status=200,
        content_type="text/html; charset=UTF-8",
        match=match or [],
    )


def _add_post_ajax(sample_path: str) -> None:
    """POST on resultado.xhtml — AJAX pagination, returns RichFaces XML."""
    responses.add(
        responses.POST,
        RESULTADO_URL,
        body=load_sample("tjpe", sample_path),
        status=200,
        content_type="text/xml; charset=UTF-8",
    )


@responses.activate(registry=OrderedRegistry)
def test_cjsg_escolha_typical(mocker):
    """4-call flow: GET consulta + POST consulta=escolha + POST escolha + AJAX page 2.

    Triggered by ``tipo_decisao="todos"``, which marks both
    ``tipoAcordao`` and ``tipoDecisaoMonocratica`` checkboxes — the
    backend then routes the response through the chooser page.
    """
    mocker.patch("time.sleep")
    _add_get_consulta()
    _add_post_consulta("cjsg/step_02_escolha.html")
    # Botão de acórdãos da página de escolha capturada: com
    # ``tipo_decisao="todos"`` o scraper escolhe o rótulo padrão "Acórdãos".
    # Sem o matcher, um identificador errado no POST passaria despercebido.
    botao = "resultadoForm:j_id27"
    _add_post_escolha(
        "cjsg/step_03_resultado.html",
        match=[urlencoded_body_subset_matcher({"resultadoForm": "resultadoForm", botao: botao})],
    )
    _add_post_ajax("cjsg/step_04_pagina_02.xml")

    df = jus.scraper("tjpe").cjsg(
        "dano moral", paginas=range(1, 3), tipo_decisao="todos"
    )

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_MIN_COLUMNS
    assert len(df) > 0
    assert df["processo"].notna().all(), "processo nulo em alguma linha"
    assert (df["processo"].astype(str).str.len() > 0).mean() >= 0.5, (
        "mais da metade dos processos vazios — parser provavelmente quebrado"
    )
    assert df["processo"].nunique() > 1, (
        "todos os processos iguais — paginacao suspeita"
    )


@responses.activate(registry=OrderedRegistry)
def test_cjsg_simples_typical(mocker):
    """3-call flow: GET consulta + POST consulta=results + AJAX page 2.

    With the default ``tipo_decisao="acordaos"`` only one checkbox is
    marked, so the backend skips the chooser and returns the results
    page directly from the initial POST.
    """
    mocker.patch("time.sleep")
    _add_get_consulta()
    _add_post_consulta("cjsg/simples_resultado.html")
    _add_post_ajax("cjsg/simples_pagina_02.xml")

    df = jus.scraper("tjpe").cjsg("dano moral", paginas=range(1, 3))

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_MIN_COLUMNS
    assert len(df) > 0
    assert df["processo"].notna().all(), "processo nulo em alguma linha"
    assert (df["processo"].astype(str).str.len() > 0).mean() >= 0.5, (
        "mais da metade dos processos vazios — parser provavelmente quebrado"
    )
    assert df["processo"].nunique() > 1, (
        "todos os processos iguais — paginacao suspeita"
    )


@responses.activate(registry=OrderedRegistry)
def test_cjsg_pagina_repetida_uma_vez_e_alem_do_total_no_log(mocker, caplog):
    """A página 2 pedida duas vezes sai num POST só; a além do total vai para o log, sem POST."""
    mocker.patch("time.sleep")
    _add_get_consulta()
    _add_post_consulta("cjsg/simples_resultado.html")
    _add_post_ajax("cjsg/simples_pagina_02.xml")

    with caplog.at_level(logging.WARNING, logger="juscraper.tjpe"):
        brutos = jus.scraper("tjpe").cjsg_download("dano moral", paginas=[2, 2, 10**6])

    assert len(brutos) == 1
    assert urls_enviadas().count(RESULTADO_URL) == 1
    assert "TJPE: página 1000000 fora do intervalo" in caplog.text


@responses.activate(registry=OrderedRegistry)
def test_cjsg_monocraticas_typical(mocker):
    """3-call flow com ``tipo_decisao="monocraticas"``: ``ementa`` ausente, data e decisão preenchidas.

    O bloco das monocráticas não traz o rótulo ``Ementa``; sem a coluna, a
    junção com a saída dos acórdãos (e de outros tribunais) perdia o campo.
    """
    mocker.patch("time.sleep")
    _add_get_consulta()
    _add_post_consulta("cjsg/monocraticas_resultado.html")
    _add_post_ajax("cjsg/monocraticas_pagina_02.xml")

    df = jus.scraper("tjpe").cjsg("dano moral", paginas=range(1, 3), tipo_decisao="monocraticas")

    assert len(df) == 10
    assert df["processo"].nunique() == 10
    assert df["ementa"].map(pd.isna).all()
    assert df["data_publicacao"].notna().all()
    assert df["decisao"].map(lambda texto: isinstance(texto, str) and bool(texto)).all()


@responses.activate(registry=OrderedRegistry)
def test_cjsg_no_results(mocker):
    """Zero-hit query: GET consulta + POST consulta=zero, no AJAX follow-up."""
    mocker.patch("time.sleep")
    _add_get_consulta()
    _add_post_consulta("cjsg/no_results.html")

    with pytest.warns(UserWarning, match="Nenhum documento encontrado"):
        df = jus.scraper("tjpe").cjsg("juscraperprobeztzeroxyz", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert df.empty


@responses.activate(registry=OrderedRegistry)
def test_cjsg_sem_resultados_em_todos_os_tipos_avisa(mocker):
    """Escolha com 'Nenhum documento encontrado' nos dois tipos: vazio com aviso.

    Sample capturado ao vivo em 15/11/2026, quando o portal respondia assim a
    qualquer busca, inclusive no navegador.
    """
    mocker.patch("time.sleep")
    _add_get_consulta()
    _add_post_consulta("cjsg/no_results_todos.html")

    with pytest.warns(UserWarning, match="Nenhum documento.*'dano moral'"):
        df = jus.scraper("tjpe").cjsg("dano moral", paginas=1, tipo_decisao="todos")

    assert df.empty


@responses.activate(registry=OrderedRegistry)
def test_cjsg_pagina_desconhecida_levanta_erro(mocker):
    """Página fora dos formatos conhecidos levanta erro em vez de sair vazia."""
    mocker.patch("time.sleep")
    _add_get_consulta()
    _add_post_consulta("cjsg/step_01_consulta.html")

    with pytest.raises(ValueError, match="fora dos formatos conhecidos"):
        jus.scraper("tjpe").cjsg("dano moral", paginas=1)


@responses.activate(registry=OrderedRegistry)
def test_cjsg_resultado_sem_contagem_levanta_erro(mocker):
    """Resultado sem "Documentos encontrados: N" levanta, mesmo com o aviso numa ementa.

    Antes, a contagem virava 0 e a busca saía vazia sem aviso.
    """
    mocker.patch("time.sleep")
    _add_get_consulta()
    _add_post_consulta("cjsg/step_02_escolha.html")
    responses.add(
        responses.POST,
        ESCOLHA_URL,
        body=resultado_sem_cabecalho_com_aviso_na_ementa(),
        status=200,
        content_type="text/html; charset=UTF-8",
    )

    with pytest.raises(ValueError, match="TJPE cjsg: a página lida não traz a contagem"):
        jus.scraper("tjpe").cjsg("dano moral", paginas=1, tipo_decisao="todos")


def _escolha_com_tipo_zerado(botao_zerado: str) -> str:
    """Escolha capturada com um dos tipos trocado por 'Nenhum documento encontrado'.

    As duas capturas de escolha (``step_02_escolha.html``, com os dois tipos
    com documentos, e ``no_results_todos.html``, com os dois zerados) só
    diferem na célula do link de cada tipo: o portal monta a linha zerada com
    o texto no lugar do ``<a>``. A página mista junta as duas, linha a linha.
    """
    com_documentos = load_sample("tjpe", "cjsg/step_02_escolha.html").splitlines(keepends=True)
    zerada = load_sample("tjpe", "cjsg/no_results_todos.html").splitlines(keepends=True)
    linhas = [z if botao_zerado in c else c for c, z in zip(com_documentos, zerada, strict=True)]
    assert linhas != com_documentos, f"a captura deixou de ter a linha do botão {botao_zerado}"
    return "".join(linhas)


@pytest.mark.parametrize(
    ("botao_zerado", "botao_escolhido"),
    [
        pytest.param("resultadoForm:j_id27", "resultadoForm:j_id37", id="acordaos_zerados"),
        pytest.param("resultadoForm:j_id37", "resultadoForm:j_id27", id="monocraticas_zeradas"),
    ],
)
@responses.activate(registry=OrderedRegistry)
def test_cjsg_todos_escolhe_o_tipo_com_documentos(mocker, botao_zerado, botao_escolhido):
    """Em ``"todos"``, com um tipo zerado na escolha, vale o tipo que tem documentos.

    A página de resultados devolvida é a de acórdãos capturada: o que se
    confere é o botão pedido no POST da escolha.
    """
    mocker.patch("time.sleep")
    _add_get_consulta()
    _add_post_consulta_html(_escolha_com_tipo_zerado(botao_zerado))
    _add_post_escolha(
        "cjsg/step_03_resultado.html",
        match=[urlencoded_body_subset_matcher({"resultadoForm": "resultadoForm", botao_escolhido: botao_escolhido})],
    )

    df = jus.scraper("tjpe").cjsg("dano moral", paginas=1, tipo_decisao="todos")

    assert len(df) > 0


@responses.activate(registry=OrderedRegistry)
def test_cjsg_todos_com_linha_de_acordaos_fora_do_formato_levanta_erro(mocker):
    """A linha de acórdãos que não diz 'Nenhum documento encontrado' não cede a vez às monocráticas.

    Só o texto do link muda: sem o 'documentos encontrados' que o
    identifica, a linha sai do formato conhecido, mas não está zerada.
    """
    mocker.patch("time.sleep")
    _add_get_consulta()
    escolha = load_sample("tjpe", "cjsg/step_02_escolha.html")
    assert escolha.count("953 documentos encontrados") == 1
    _add_post_consulta_html(escolha.replace("953 documentos encontrados", "953 Documentos encontrados"))

    with pytest.raises(ValueError, match="Could not find escolha button for 'Acórdãos'"):
        jus.scraper("tjpe").cjsg("dano moral", paginas=1, tipo_decisao="todos")
