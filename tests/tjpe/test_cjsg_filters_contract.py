"""Filter-propagation contract for TJPE cjsg.

TJPE e JSF/RichFaces: filtros viajam como campos form-urlencoded no corpo do
``POST consulta.xhtml``. O scraper carrega o ``ViewState`` do GET inicial, entao
a suite usa ``OrderedRegistry`` (mesmo padrao do
:mod:`tests.tjpe.test_cjsg_contract`) e cada teste registra GET + POST em ordem.

Cada teste responde o POST com ``no_results.html`` ("Nenhum documento
encontrado"). A sample nao bate em ``_is_results_page`` nem em
``_is_escolha_page``, entao o scraper retorna lista vazia antes de qualquer
AJAX de paginacao — duas chamadas HTTP bastam para fechar o contrato dos
campos do form, sem precisar fixar pagina seguinte.

Wiring de :class:`InputCJSGTJPE` (etapa 2 da #197) ligou o pydantic ao
``cjsg_download`` — kwargs desconhecidos viram ``TypeError``, verificado
em :func:`test_cjsg_unknown_kwarg_raises`.
"""
from __future__ import annotations

import logging
import warnings
from urllib.parse import parse_qs

import pandas as pd
import pytest
import responses
from responses.registries import OrderedRegistry

import juscraper as jus
from tests._helpers import assert_unknown_kwarg_raises, load_sample, urlencoded_body_subset_matcher
from tests.tjpe.test_cjsg_contract import CONSULTA_URL

FORM = "formPesquisaJurisprudencia"


@pytest.fixture(autouse=True)
def _silence_unexpected_response_warning(caplog):
    # ``no_results.html`` nao casa com ``_is_results_page`` nem com
    # ``_is_escolha_page``, entao o scraper cai no ramo "unexpected response"
    # e emite ``logger.warning``. Limita a captura do caplog para que o ruido
    # nao polua a saida se algum teste vier a falhar.
    caplog.set_level(logging.ERROR, logger="juscraper.courts.tjpe.download")


def _add_get_consulta() -> None:
    responses.add(
        responses.GET,
        CONSULTA_URL,
        body=load_sample("tjpe", "cjsg/step_01_consulta.html"),
        status=200,
        content_type="text/html; charset=UTF-8",
    )


def _add_post_no_results(*, match=None) -> None:
    responses.add(
        responses.POST,
        CONSULTA_URL,
        body=load_sample("tjpe", "cjsg/no_results.html"),
        status=200,
        content_type="text/html; charset=UTF-8",
        match=match or [],
    )


@responses.activate(registry=OrderedRegistry)
def test_cjsg_all_filters_land_in_form_body(mocker):
    """Todos os filtros publicos chegam ao corpo do POST consulta.xhtml."""
    mocker.patch("time.sleep")
    expected = {
        f"{FORM}:inputBuscaSimples": "dano moral",
        f"{FORM}:j_id59InputDate": "01/01/2024",
        f"{FORM}:periodoFimInputDate": "31/03/2024",
        f"{FORM}:selectRelator": "REL-123",
        f"{FORM}:selectClasseCNJ": "100",
        f"{FORM}:selectAssuntoCNJ": "200",
        f"{FORM}:selectMeioTramitacao": "ELETRONICO",
        f"{FORM}:tipoAcordao": "on",
    }
    _add_get_consulta()
    _add_post_no_results(match=[urlencoded_body_subset_matcher(expected)])

    df = jus.scraper("tjpe").cjsg(
        "dano moral",
        paginas=1,
        data_julgamento_inicio="01/01/2024",
        data_julgamento_fim="31/03/2024",
        relator="REL-123",
        classe="100",
        assunto="200",
        meio_tramitacao="ELETRONICO",
        tipo_decisao="acordaos",
    )
    assert isinstance(df, pd.DataFrame)
    assert df.empty


@responses.activate(registry=OrderedRegistry)
def test_cjsg_tipo_decisao_monocraticas_marks_only_monocratica_checkbox(mocker):
    """``tipo_decisao='monocraticas'`` ativa so o checkbox tipoDecisaoMonocratica."""
    mocker.patch("time.sleep")

    monocratica = f"{FORM}:tipoDecisaoMonocratica"
    acordao = f"{FORM}:tipoAcordao"
    todos = f"{FORM}:tipoTodos"

    def assert_only_monocratica(request):
        body = request.body or b""
        if isinstance(body, bytes):
            body = body.decode("utf-8")
        parsed = {
            k: v[0] if v else ""
            for k, v in parse_qs(body, keep_blank_values=True).items()
        }
        if parsed.get(monocratica) != "on":
            return False, "tipoDecisaoMonocratica ausente"
        if acordao in parsed:
            return False, "tipoAcordao nao deveria estar presente"
        if todos in parsed:
            return False, "tipoTodos nao deveria estar presente"
        return True, ""

    _add_get_consulta()
    _add_post_no_results(match=[assert_only_monocratica])

    df = jus.scraper("tjpe").cjsg("dano moral", paginas=1, tipo_decisao="monocraticas")
    assert df.empty


@responses.activate(registry=OrderedRegistry)
def test_cjsg_tipo_decisao_todos_marks_all_three_checkboxes(mocker):
    """``tipo_decisao='todos'`` ativa tipoAcordao + tipoDecisaoMonocratica + tipoTodos."""
    mocker.patch("time.sleep")
    expected = {
        f"{FORM}:tipoAcordao": "on",
        f"{FORM}:tipoDecisaoMonocratica": "on",
        f"{FORM}:tipoTodos": "on",
    }
    _add_get_consulta()
    _add_post_no_results(match=[urlencoded_body_subset_matcher(expected)])

    df = jus.scraper("tjpe").cjsg("dano moral", paginas=1, tipo_decisao="todos")
    assert df.empty


@responses.activate(registry=OrderedRegistry)
def test_cjsg_query_alias_emits_deprecation_warning(mocker):
    """O alias deprecado ``query`` e normalizado antes do form ser montado."""
    mocker.patch("time.sleep")
    _add_get_consulta()
    _add_post_no_results(
        match=[urlencoded_body_subset_matcher({f"{FORM}:inputBuscaSimples": "dano moral"})]
    )

    with pytest.warns(DeprecationWarning, match="query.*deprecado"):
        df = jus.scraper("tjpe").cjsg(pesquisa=None, query="dano moral", paginas=1)

    assert df.empty


@responses.activate(registry=OrderedRegistry)
def test_cjsg_termo_alias_emits_deprecation_warning(mocker):
    """O alias deprecado ``termo`` tambem e normalizado para ``pesquisa``."""
    mocker.patch("time.sleep")
    _add_get_consulta()
    _add_post_no_results(
        match=[urlencoded_body_subset_matcher({f"{FORM}:inputBuscaSimples": "dano moral"})]
    )

    with pytest.warns(DeprecationWarning, match="termo.*deprecado"):
        df = jus.scraper("tjpe").cjsg(pesquisa=None, termo="dano moral", paginas=1)

    assert df.empty


@responses.activate(registry=OrderedRegistry)
def test_cjsg_classe_cnj_alias_emits_deprecation_warning(mocker):
    """``classe_cnj`` e alias deprecado de ``classe`` (consumido por
    :func:`resolve_deprecated_alias` no client antes do envio)."""
    mocker.patch("time.sleep")
    _add_get_consulta()
    _add_post_no_results(
        match=[urlencoded_body_subset_matcher({f"{FORM}:selectClasseCNJ": "100"})]
    )

    with pytest.warns(DeprecationWarning, match="classe_cnj.*deprecado"):
        df = jus.scraper("tjpe").cjsg("dano moral", paginas=1, classe_cnj="100")

    assert df.empty


@responses.activate(registry=OrderedRegistry)
def test_cjsg_assunto_cnj_alias_emits_deprecation_warning(mocker):
    """``assunto_cnj`` e alias deprecado de ``assunto``."""
    mocker.patch("time.sleep")
    _add_get_consulta()
    _add_post_no_results(
        match=[urlencoded_body_subset_matcher({f"{FORM}:selectAssuntoCNJ": "200"})]
    )

    with pytest.warns(DeprecationWarning, match="assunto_cnj.*deprecado"):
        df = jus.scraper("tjpe").cjsg("dano moral", paginas=1, assunto_cnj="200")

    assert df.empty


@responses.activate(registry=OrderedRegistry)
def test_cjsg_data_inicio_alias_maps_to_data_julgamento(mocker):
    """``data_inicio`` / ``data_fim`` mapeiam para ``data_julgamento_inicio`` /
    ``data_julgamento_fim`` via :func:`normalize_datas` e chegam ao form com o
    mesmo formato passado pelo usuario (``DD/MM/AAAA``)."""
    mocker.patch("time.sleep")
    expected = {
        f"{FORM}:j_id59InputDate": "01/01/2024",
        f"{FORM}:periodoFimInputDate": "31/03/2024",
    }
    _add_get_consulta()
    _add_post_no_results(match=[urlencoded_body_subset_matcher(expected)])

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        df = jus.scraper("tjpe").cjsg(
            "dano moral",
            paginas=1,
            data_inicio="01/01/2024",
            data_fim="31/03/2024",
        )

    assert df.empty
    msgs = [str(w.message) for w in caught if issubclass(w.category, DeprecationWarning)]
    assert any("data_inicio" in m and "deprecado" in m for m in msgs)
    assert any("data_fim" in m and "deprecado" in m for m in msgs)


def test_cjsg_unknown_kwarg_raises():
    """Kwargs nao declarados em :class:`InputCJSGTJPE` levantam ``TypeError``
    com o nome do campo, em vez de serem silenciosamente descartados pelo
    ``**kwargs`` (refs #93, #197).
    """
    assert_unknown_kwarg_raises(
        jus.scraper("tjpe").cjsg,
        "kwarg_inventado",
        "dano moral",
        paginas=1,
    )
