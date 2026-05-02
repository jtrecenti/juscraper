"""Filters propagation for ``DatajudScraper.listar_processos`` (issue #140).

DataJud has no deprecated aliases (rule 6a of the contract checklist
in CLAUDE.md is N/A here): the API is recent and was designed with
the canonical names from day one.

``InputListarProcessosDataJud`` is wired into the client — unknown
kwargs are converted to ``TypeError`` via ``raise_on_extra_kwargs``;
other validation errors (bad date format, mutually-exclusive filters,
out-of-range ``tamanho_pagina``) surface as ``ValidationError``.
"""
import pandas as pd
import pytest
import responses
from pydantic import ValidationError
from responses.matchers import header_matcher, json_params_matcher

import juscraper as jus
from juscraper.aggregators.datajud.client import DatajudScraper
from tests._helpers import load_sample
from tests.fixtures.capture.datajud import build_payload as _payload

BASE = DatajudScraper.BASE_API_URL
API_KEY = DatajudScraper.DEFAULT_API_KEY

CNJ_TJSP_FORMATTED = "1000413-22.2017.8.26.0415"
CNJ_TJSP_CLEAN = "10004132220178260415"


@responses.activate
def test_listar_processos_all_filters_land_in_body(mocker):
    """All filters propagate simultaneously: numero_processo + ano +
    classe + assuntos + mostrar_movs + tamanho_pagina. The matcher
    confirms the body has the four ``must_conditions`` in canonical order
    plus the dual ``dataAjuizamento`` range and ``_source: True``."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        f"{BASE}/api_publica_tjsp/_search",
        body=load_sample("datajud", "listar_processos/single_page.json"),
        status=200,
        content_type="application/json",
        match=[
            json_params_matcher(_payload(
                numero_processo=CNJ_TJSP_CLEAN,
                ano_ajuizamento=2023,
                classe="436",
                assuntos=["1127", "1156"],
                mostrar_movs=True,
                tamanho_pagina=50,
            )),
            header_matcher(
                {"Authorization": f"APIKey {API_KEY}"}, strict_match=False
            ),
        ],
    )

    df = jus.scraper("datajud").listar_processos(
        tribunal="TJSP",
        numero_processo=CNJ_TJSP_FORMATTED,
        ano_ajuizamento=2023,
        classe="436",
        assuntos=["1127", "1156"],
        mostrar_movs=True,
        tamanho_pagina=50,
        paginas=range(1, 2),
    )

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_listar_processos_cnj_invalido_nao_chama_api():
    """CNJ shorter than 20 digits fails ``clean_cnj`` length check; the
    client emits a ``UserWarning`` and returns an empty DataFrame
    *without* ever calling the API. With no ``responses.add`` registered,
    a hit on the API would surface as ``ConnectionError``."""
    with pytest.warns(UserWarning):
        df = jus.scraper("datajud").listar_processos(
            numero_processo="123-invalido"
        )

    assert isinstance(df, pd.DataFrame)
    assert df.empty
    assert len(responses.calls) == 0


def test_listar_processos_unknown_kwarg_raises():
    """Unknown kwargs raise ``TypeError`` via ``raise_on_extra_kwargs`` —
    ``InputListarProcessosDataJud`` is wired and ``extra="forbid"``
    rejects unknown kwargs before any HTTP request is built."""
    with pytest.raises(TypeError, match=r"got unexpected keyword argument\(s\): 'parametro_inventado'"):
        jus.scraper("datajud").listar_processos(
            tribunal="TJSP", parametro_inventado="xyz"
        )


def test_listar_processos_tamanho_pagina_acima_do_cap():
    """``tamanho_pagina`` acima do cap documentado da API (10000) e
    rejeitado pelo schema antes da requisicao."""
    with pytest.raises(ValidationError):
        jus.scraper("datajud").listar_processos(
            tribunal="TJSP", tamanho_pagina=20000
        )


def test_listar_processos_tamanho_pagina_abaixo_do_minimo():
    """``tamanho_pagina`` abaixo do minimo documentado da API (10) e
    rejeitado pelo schema. Cobre os tres regimes: zero, negativo e o
    intervalo (1..9) deixado de fora pela doc oficial."""
    for valor in (0, -100, 5):
        with pytest.raises(ValidationError):
            jus.scraper("datajud").listar_processos(
                tribunal="TJSP", tamanho_pagina=valor
            )


# =============================================================================
# Filtros novos da issue #49: data_ajuizamento_*, tipos_movimentacao,
# movimentos_codigo, orgao_julgador, query (override).
# =============================================================================


@responses.activate
def test_data_ajuizamento_range_propaga(mocker):
    """Filtro ``data_ajuizamento_inicio/fim`` propaga como ``bool.should``
    com 2 ``range`` (ISO + compacto, mesmo padrao da issue #51 para
    ``ano_ajuizamento``)."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        f"{BASE}/api_publica_tjsp/_search",
        body=load_sample("datajud", "listar_processos/single_page.json"),
        status=200,
        content_type="application/json",
        match=[
            json_params_matcher(_payload(
                data_ajuizamento_inicio="2024-01-15",
                data_ajuizamento_fim="2024-03-31",
                tamanho_pagina=10,
            )),
        ],
    )
    df = jus.scraper("datajud").listar_processos(
        tribunal="TJSP",
        data_ajuizamento_inicio="2024-01-15",
        data_ajuizamento_fim="2024-03-31",
        tamanho_pagina=10,
        paginas=range(1, 2),
    )
    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_tipos_movimentacao_resolve_para_codigos(mocker):
    """``tipos_movimentacao=['decisao']`` vira lista de codigos TPU
    no body Elasticsearch via ``TIPOS_MOVIMENTACAO``."""
    from juscraper.aggregators.datajud.mappings import TIPOS_MOVIMENTACAO
    mocker.patch("time.sleep")
    codigos_esperados = TIPOS_MOVIMENTACAO["decisao"]
    responses.add(
        responses.POST,
        f"{BASE}/api_publica_tjsp/_search",
        body=load_sample("datajud", "listar_processos/single_page.json"),
        status=200,
        content_type="application/json",
        match=[
            json_params_matcher(_payload(
                movimentos_codigo=codigos_esperados,
                tamanho_pagina=10,
            )),
        ],
    )
    df = jus.scraper("datajud").listar_processos(
        tribunal="TJSP",
        tipos_movimentacao=["decisao"],
        tamanho_pagina=10,
        paginas=range(1, 2),
    )
    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_tipos_movimentacao_e_movimentos_codigo_concatenam(mocker):
    """Passar ``tipos_movimentacao`` + ``movimentos_codigo`` -> uniao no
    ``terms``. Dedup mantem ordem (categoria primeiro, codigos extras depois)."""
    from juscraper.aggregators.datajud.mappings import TIPOS_MOVIMENTACAO
    mocker.patch("time.sleep")
    codigos_decisao = TIPOS_MOVIMENTACAO["decisao"]
    extras = [99999]
    codigos_esperados = list(dict.fromkeys(codigos_decisao + extras))
    responses.add(
        responses.POST,
        f"{BASE}/api_publica_tjsp/_search",
        body=load_sample("datajud", "listar_processos/single_page.json"),
        status=200,
        content_type="application/json",
        match=[
            json_params_matcher(_payload(
                movimentos_codigo=codigos_esperados,
                tamanho_pagina=10,
            )),
        ],
    )
    df = jus.scraper("datajud").listar_processos(
        tribunal="TJSP",
        tipos_movimentacao=["decisao"],
        movimentos_codigo=extras,
        tamanho_pagina=10,
        paginas=range(1, 2),
    )
    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_query_override_propaga(mocker):
    """``query`` (dict) vira a chave ``query`` do payload Elasticsearch
    literalmente, sem wrapping. Outros campos do payload (size/sort/source)
    continuam controlados pela biblioteca."""
    mocker.patch("time.sleep")
    custom_query = {
        "bool": {
            "must_not": [{"exists": {"field": "orgaoJulgador.nome"}}],
            "should": [{"match": {"classe.nome": "tutela"}}],
            "minimum_should_match": 1,
        }
    }
    expected_body = {
        "query": custom_query,
        "size": 10,
        "track_total_hits": True,
        "sort": [{"id.keyword": "asc"}],
        "_source": {"excludes": ["movimentacoes", "movimentos"]},
    }
    responses.add(
        responses.POST,
        f"{BASE}/api_publica_tjsp/_search",
        body=load_sample("datajud", "listar_processos/single_page.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(expected_body)],
    )
    df = jus.scraper("datajud").listar_processos(
        tribunal="TJSP",
        query=custom_query,
        tamanho_pagina=10,
        paginas=range(1, 2),
    )
    assert isinstance(df, pd.DataFrame)


# -----------------------------------------------------------------------------
# Validacoes pydantic (sem rede — falha antes do builder).
# -----------------------------------------------------------------------------


def test_data_e_ano_ajuizamento_excluem():
    with pytest.raises(ValidationError, match="mutuamente exclusivos"):
        jus.scraper("datajud").listar_processos(
            tribunal="TJSP",
            ano_ajuizamento=2023,
            data_ajuizamento_inicio="2023-01-01",
        )


@pytest.mark.parametrize(
    "valor",
    ["2023-13-01", "01/01/2023", "2023-1-1", "2023", "abacate"],
)
def test_data_ajuizamento_formato_invalido(valor):
    with pytest.raises(ValidationError, match="YYYY-MM-DD"):
        jus.scraper("datajud").listar_processos(
            tribunal="TJSP",
            data_ajuizamento_inicio=valor,
        )


def test_data_ajuizamento_range_invertido():
    with pytest.raises(ValidationError, match=r"deve ser <="):
        jus.scraper("datajud").listar_processos(
            tribunal="TJSP",
            data_ajuizamento_inicio="2024-12-31",
            data_ajuizamento_fim="2024-01-01",
        )


def test_tipo_movimentacao_desconhecido_lista_validos():
    with pytest.raises(ValidationError) as excinfo:
        jus.scraper("datajud").listar_processos(
            tribunal="TJSP",
            tipos_movimentacao=["decisao", "inexistente_xyz"],
        )
    msg = str(excinfo.value)
    assert "inexistente_xyz" in msg
    # A mensagem lista os nomes validos para guiar o usuario.
    assert "decisao" in msg
    assert "sentenca" in msg


@pytest.mark.parametrize(
    "kwarg_extra,valor",
    [
        ("numero_processo", "10004132220178260415"),
        ("ano_ajuizamento", 2023),
        ("classe", "436"),
        ("assuntos", ["1127"]),
        ("data_ajuizamento_inicio", "2024-01-01"),
        ("data_ajuizamento_fim", "2024-03-31"),
        ("tipos_movimentacao", ["decisao"]),
        ("movimentos_codigo", [193]),
        ("orgao_julgador", "Vara X"),
    ],
)
def test_query_exclusivo_com_filtros_amigaveis(kwarg_extra, valor):
    with pytest.raises(ValidationError, match="mutuamente exclusivo"):
        jus.scraper("datajud").listar_processos(
            tribunal="TJSP",
            query={"match_all": {}},
            **{kwarg_extra: valor},
        )


def test_query_exige_tribunal():
    with pytest.raises(ValidationError, match="exige 'tribunal'"):
        jus.scraper("datajud").listar_processos(
            query={"match_all": {}},
        )


def test_query_dict_vazio_rejeitado():
    with pytest.raises(ValidationError, match="nao-vazio"):
        jus.scraper("datajud").listar_processos(
            tribunal="TJSP",
            query={},
        )
