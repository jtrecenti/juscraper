"""Filter-propagation contract for TJDFT cjsg."""
import warnings

import pandas as pd
import pytest
import responses
from pydantic import ValidationError
from responses.matchers import json_params_matcher

import juscraper as jus
from tests._helpers import assert_unknown_kwarg_raises, load_sample
from tests.tjdft.test_cjsg_contract import BASE, _add_page, _payload


@responses.activate
def test_cjsg_all_filters_land_in_json_body(mocker):
    """TJDFT-specific public filters must reach the POST JSON payload."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        BASE,
        body=load_sample("tjdft", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[
            json_params_matcher(
                _payload(
                    "dano moral",
                    1,
                    sinonimos=False,
                    espelho=False,
                    inteiro_teor=True,
                    tamanho_pagina=25,
                )
            )
        ],
    )

    df = jus.scraper("tjdft").cjsg(
        "dano moral",
        paginas=1,
        sinonimos=False,
        espelho=False,
        inteiro_teor=True,
        tamanho_pagina=25,
    )

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_query_alias_emits_deprecation_warning(mocker):
    """The deprecated ``query`` alias is normalized before the request body is built."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        BASE,
        body=load_sample("tjdft", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(_payload("dano moral", 1))],
    )

    with pytest.warns(DeprecationWarning, match="query.*deprecado"):
        df = jus.scraper("tjdft").cjsg(pesquisa=None, query="dano moral", paginas=1)

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_data_inicio_alias_maps_to_data_julgamento(mocker):
    """Generic ``data_inicio``/``data_fim`` aliases map to
    ``data_julgamento_inicio``/``data_julgamento_fim`` via ``normalize_datas``
    and reach the request body as a ``termosAcessorios`` entry with the
    canonical ``"entre YYYY-MM-DD e YYYY-MM-DD"`` value.
    """
    mocker.patch("time.sleep")
    expected_termos = [
        {"campo": "dataJulgamento", "valor": "entre 2024-01-01 e 2024-03-31"},
    ]
    responses.add(
        responses.POST,
        BASE,
        body=load_sample("tjdft", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(_payload("dano moral", 1, termos_acessorios=expected_termos))],
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        df = jus.scraper("tjdft").cjsg(
            "dano moral",
            paginas=1,
            data_inicio="2024-01-01",
            data_fim="2024-03-31",
        )

    assert isinstance(df, pd.DataFrame)
    deprecation_messages = [str(w.message) for w in caught if issubclass(w.category, DeprecationWarning)]
    assert any("data_inicio" in m and "deprecado" in m for m in deprecation_messages)
    assert any("data_fim" in m and "deprecado" in m for m in deprecation_messages)


def test_cjsg_unknown_kwarg_raises():
    """Kwargs not declared in :class:`InputCJSGTJDFT` raise ``TypeError`` with
    the field name, instead of being silently dropped (refs #84, #93, #165)."""
    assert_unknown_kwarg_raises(
        jus.scraper("tjdft").cjsg,
        "kwarg_inventado",
        "dano moral",
        paginas=1,
    )


@responses.activate
def test_cjsg_quantidade_por_pagina_alias_emits_deprecation_warning(mocker):
    """``quantidade_por_pagina`` e alias deprecado de ``tamanho_pagina`` (refs #211)."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        BASE,
        body=load_sample("tjdft", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(_payload("dano moral", 1, tamanho_pagina=25))],
    )

    with pytest.warns(DeprecationWarning, match="quantidade_por_pagina.*deprecado"):
        df = jus.scraper("tjdft").cjsg(
            "dano moral", paginas=1, quantidade_por_pagina=25
        )

    assert isinstance(df, pd.DataFrame)


@pytest.mark.parametrize("tamanho_pagina", [25, 10], ids=["outro_valor", "igual_ao_default"])
def test_cjsg_tamanho_pagina_collision_raises(tamanho_pagina):
    """Passar canonico + alias simultaneamente levanta ValueError (refs #211).

    Inclusive com ``tamanho_pagina=10``, o default: antes, o 10 era a
    sentinela de "nao informado", e o alias passava por cima sem erro.
    """
    with pytest.raises(ValueError, match=r"tamanho_pagina.*quantidade_por_pagina"):
        jus.scraper("tjdft").cjsg(
            "dano moral", paginas=1, tamanho_pagina=tamanho_pagina, quantidade_por_pagina=50
        )


@responses.activate
@pytest.mark.parametrize(
    ("kwargs", "tamanho"),
    [({}, 10), ({"tamanho_pagina": 10}, 10), ({"tamanho_pagina": 25}, 25)],
    ids=["nenhum", "so_canonico_default", "so_canonico"],
)
def test_cjsg_tamanho_pagina_sem_alias_nao_conflita(mocker, kwargs, tamanho):
    """Sem o alias, ``tamanho_pagina`` (ou o default 10) vai direto ao payload."""
    mocker.patch("time.sleep")
    _add_page("dano moral", 1, "cjsg/no_results.json", tamanho_pagina=tamanho)

    df = jus.scraper("tjdft").cjsg("dano moral", paginas=1, **kwargs)

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_tamanho_pagina_40_e_o_maximo_aceito(mocker):
    """40 é o maior ``tamanho`` que a API aceita; vai ao payload sem ajuste."""
    mocker.patch("time.sleep")
    _add_page("dano moral", 1, "cjsg/no_results.json", tamanho_pagina=40)

    df = jus.scraper("tjdft").cjsg("dano moral", paginas=1, tamanho_pagina=40)

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_tamanho_pagina_acima_de_40_falha_antes_da_rede():
    """Acima de 40 a API responde HTTP 400; o schema recusa antes da requisição,
    também quando o valor vem pelo alias deprecado ``quantidade_por_pagina``."""
    with (
        pytest.warns(DeprecationWarning, match="quantidade_por_pagina"),
        pytest.raises(ValidationError, match="less than or equal to 40"),
    ):
        jus.scraper("tjdft").cjsg("dano moral", paginas=1, quantidade_por_pagina=41)

    assert len(responses.calls) == 0


@responses.activate
def test_cjsg_data_julgamento_aceita_formato_brasileiro(mocker):
    """Datas em ``DD/MM/YYYY`` chegam coercidas em ISO ao backend.

    Cobre o caminho end-to-end de ``apply_input_pipeline_search`` lendo
    ``BACKEND_DATE_FORMAT='%Y-%m-%d'`` declarado em :class:`InputCJSGTJDFT`
    e convertendo via ``coerce_brazilian_date``. A data isolada chega ao
    payload como ``termosAcessorios`` na forma canonica
    ``"entre 2024-01-01 e 2024-03-31"`` — se o pipeline esquecer de
    coagir, o termo carrega o formato BR cru e o matcher dispara
    ``ConnectionError`` (refs #182, #173, #167)."""
    mocker.patch("time.sleep")
    expected_termos = [
        {"campo": "dataJulgamento", "valor": "entre 2024-01-01 e 2024-03-31"},
    ]
    responses.add(
        responses.POST,
        BASE,
        body=load_sample("tjdft", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(_payload("dano moral", 1, termos_acessorios=expected_termos))],
    )

    df = jus.scraper("tjdft").cjsg(
        "dano moral",
        paginas=1,
        data_julgamento_inicio="01/01/2024",
        data_julgamento_fim="31/03/2024",
    )

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_data_publicacao_vai_em_termos_acessorios(mocker):
    """``data_publicacao_inicio``/``_fim`` chegam ao corpo como termo ``dataPublicacao``."""
    mocker.patch("time.sleep")
    expected_termos = [
        {"campo": "dataPublicacao", "valor": "entre 2024-01-01 e 2024-03-31"},
    ]
    _add_page("dano moral", 1, "cjsg/no_results.json", termos_acessorios=expected_termos)

    df = jus.scraper("tjdft").cjsg(
        "dano moral",
        paginas=1,
        data_publicacao_inicio="2024-01-01",
        data_publicacao_fim="2024-03-31",
    )

    assert isinstance(df, pd.DataFrame)
