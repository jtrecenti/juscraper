"""Filter-propagation contract for TJES cjsg/cjpg."""
from datetime import date

import pandas as pd
import pytest
import responses

import juscraper as jus
from tests._helpers import assert_unknown_kwarg_raises
from tests.tjes.test_cjsg_contract import _add_page


@responses.activate
def test_cjsg_all_supported_filters_land_in_query_params(mocker):
    """All TJES cjsg filters supported by the endpoint must reach query params."""
    mocker.patch("time.sleep")
    _add_page(
        "dano moral",
        1,
        "cjsg/no_results.json",
        core="pje2g_mono",
        tamanho_pagina=5,
        busca_exata=True,
        data_inicio="2024-01-01",
        data_fim="2024-03-31",
        relator="FULANO DE TAL",
        orgao_julgador="PRIMEIRA CAMARA",
        classe="APELACAO",
        jurisdicao="VITORIA",
        assunto="DANO MORAL",
        ordenacao="dt_juntada desc",
    )

    df = jus.scraper("tjes").cjsg(
        "dano moral",
        paginas=1,
        core="pje2g_mono",
        tamanho_pagina=5,
        busca_exata=True,
        data_julgamento_inicio="2024-01-01",
        data_julgamento_fim="2024-03-31",
        relator="FULANO DE TAL",
        orgao_julgador="PRIMEIRA CAMARA",
        classe="APELACAO",
        jurisdicao="VITORIA",
        assunto="DANO MORAL",
        ordenacao="dt_juntada desc",
    )

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjpg_all_supported_filters_land_in_query_params(mocker):
    """cjpg uses the same filter mapping as cjsg, fixed to core pje1g."""
    mocker.patch("time.sleep")
    _add_page(
        "obrigacao de fazer",
        1,
        "cjpg/no_results.json",
        core="pje1g",
        tamanho_pagina=5,
        busca_exata=True,
        data_inicio="2024-01-01",
        data_fim="2024-03-31",
        relator="JUIZ FULANO",
        orgao_julgador="1A VARA CIVEL",
        classe="PROCEDIMENTO COMUM",
        jurisdicao="VITORIA",
        assunto="OBRIGACAO DE FAZER",
        ordenacao="dt_juntada desc",
    )

    df = jus.scraper("tjes").cjpg(
        "obrigacao de fazer",
        paginas=1,
        tamanho_pagina=5,
        busca_exata=True,
        data_julgamento_inicio="2024-01-01",
        data_julgamento_fim="2024-03-31",
        relator="JUIZ FULANO",
        orgao_julgador="1A VARA CIVEL",
        classe="PROCEDIMENTO COMUM",
        jurisdicao="VITORIA",
        assunto="OBRIGACAO DE FAZER",
        ordenacao="dt_juntada desc",
    )

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_deprecated_relator_and_classe_aliases_emit_warnings(mocker):
    """Deprecated raw Solr aliases map to canonical public names before the request."""
    mocker.patch("time.sleep")
    _add_page(
        "dano moral",
        1,
        "cjsg/no_results.json",
        relator="FULANO DE TAL",
        classe="APELACAO",
    )

    with pytest.warns(DeprecationWarning) as warning_list:
        df = jus.scraper("tjes").cjsg(
            "dano moral",
            paginas=1,
            magistrado="FULANO DE TAL",
            classe_judicial="APELACAO",
        )

    assert isinstance(df, pd.DataFrame)
    messages = [str(w.message) for w in warning_list]
    assert any("magistrado" in m and "deprecado" in m for m in messages)
    assert any("classe_judicial" in m and "deprecado" in m for m in messages)


def test_cjsg_unknown_kwarg_raises():
    """Kwargs not declared in :class:`InputCJSGTJES` raise ``TypeError`` with
    the field name, instead of being silently dropped (refs #84, #93, #165)."""
    assert_unknown_kwarg_raises(
        jus.scraper("tjes").cjsg,
        "kwarg_inventado",
        "dano moral",
        paginas=1,
    )


def test_cjpg_unknown_kwarg_raises():
    """Same as ``test_cjsg_unknown_kwarg_raises`` for the cjpg endpoint
    (validates :class:`InputCJPGTJES`)."""
    assert_unknown_kwarg_raises(
        jus.scraper("tjes").cjpg,
        "kwarg_inventado",
        "dano moral",
        paginas=1,
    )


def test_cjsg_data_publicacao_raises_typeerror():
    """TJES backend nao expoe filtro de data de publicacao — passar
    ``data_publicacao_*`` deve levantar ``TypeError`` em vez de silently drop
    (refs #165, #173, #186)."""
    assert_unknown_kwarg_raises(
        jus.scraper("tjes").cjsg,
        "data_publicacao_inicio",
        "dano moral",
        paginas=1,
    )


def test_cjpg_data_publicacao_raises_typeerror():
    """Mesmo que ``test_cjsg_data_publicacao_raises_typeerror`` para cjpg."""
    assert_unknown_kwarg_raises(
        jus.scraper("tjes").cjpg,
        "data_publicacao_inicio",
        "dano moral",
        paginas=1,
    )


# --- Auto-fill de data parcial (TJES não passa por run_auto_chunk) -----------
# Refs bug TJSP cjpg: o pipeline canônico (``apply_input_pipeline_search``)
# autopreenche a data faltante, garantindo que TJES (backend Solr, formato
# ISO) também receba ambas as datas no query param.


@responses.activate
def test_cjpg_so_data_inicio_autopreenche_fim_com_hoje(mocker):
    """Só ``data_julgamento_inicio`` → backend recebe ``dataFim=hoje`` em ISO."""
    mocker.patch("time.sleep")
    hoje_iso = date.today().strftime("%Y-%m-%d")
    _add_page(
        "dano moral",
        1,
        "cjpg/no_results.json",
        core="pje1g",
        data_inicio="2024-01-01",
        data_fim=hoje_iso,
    )

    with pytest.warns(UserWarning, match=r"data_julgamento_fim"):
        df = jus.scraper("tjes").cjpg(
            "dano moral", paginas=1,
            data_julgamento_inicio="2024-01-01",
        )

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjpg_so_data_fim_autopreenche_inicio_com_1990(mocker):
    """Só ``data_julgamento_fim`` → backend recebe ``dataIni=1990-01-01``."""
    mocker.patch("time.sleep")
    _add_page(
        "dano moral",
        1,
        "cjpg/no_results.json",
        core="pje1g",
        data_inicio="1990-01-01",
        data_fim="2024-12-31",
    )

    with pytest.warns(UserWarning, match=r"1990-01-01"):
        df = jus.scraper("tjes").cjpg(
            "dano moral", paginas=1,
            data_julgamento_fim="2024-12-31",
        )

    assert isinstance(df, pd.DataFrame)


# --- Aliases deprecados de tamanho_pagina (refs #211) ------------------------


@responses.activate
def test_cjsg_per_page_alias_emits_deprecation_warning(mocker):
    """``per_page`` e alias deprecado de ``tamanho_pagina`` em cjsg (refs #211)."""
    mocker.patch("time.sleep")
    _add_page("dano moral", 1, "cjsg/no_results.json", tamanho_pagina=5)

    with pytest.warns(DeprecationWarning, match="per_page.*deprecado"):
        df = jus.scraper("tjes").cjsg("dano moral", paginas=1, per_page=5)

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjpg_per_page_alias_emits_deprecation_warning(mocker):
    """``per_page`` e alias deprecado de ``tamanho_pagina`` em cjpg (refs #211)."""
    mocker.patch("time.sleep")
    _add_page("dano moral", 1, "cjpg/no_results.json", core="pje1g", tamanho_pagina=5)

    with pytest.warns(DeprecationWarning, match="per_page.*deprecado"):
        df = jus.scraper("tjes").cjpg("dano moral", paginas=1, per_page=5)

    assert isinstance(df, pd.DataFrame)


def test_cjsg_tamanho_pagina_collision_raises():
    """Passar canonico + alias simultaneamente levanta ValueError (refs #211)."""
    with pytest.raises(ValueError, match=r"tamanho_pagina.*per_page"):
        jus.scraper("tjes").cjsg(
            "dano moral", paginas=1, tamanho_pagina=5, per_page=10
        )


def test_cjpg_tamanho_pagina_collision_raises():
    """Mesmo que cjsg, mas para cjpg (refs #211)."""
    with pytest.raises(ValueError, match=r"tamanho_pagina.*per_page"):
        jus.scraper("tjes").cjpg(
            "dano moral", paginas=1, tamanho_pagina=5, per_page=10
        )


@responses.activate
def test_cjsg_data_julgamento_aceita_formato_brasileiro(mocker):
    """Datas em ``DD/MM/YYYY`` chegam coercidas em ISO ao backend Solr.

    Cobre o caminho end-to-end de ``apply_input_pipeline_search`` lendo
    ``BACKEND_DATE_FORMAT='%Y-%m-%d'`` declarado em :class:`InputCJSGTJES`
    e convertendo via ``coerce_brazilian_date``. Se o schema esquecer de
    declarar o ``BACKEND_DATE_FORMAT``, o backend recebe ``dataIni=01/01/2024``
    em vez de ``dataIni=2024-01-01`` e o matcher dispara ``ConnectionError``
    (refs #182, #173, #167)."""
    mocker.patch("time.sleep")
    _add_page(
        "dano moral",
        1,
        "cjsg/no_results.json",
        data_inicio="2024-01-01",
        data_fim="2024-03-31",
    )

    df = jus.scraper("tjes").cjsg(
        "dano moral",
        paginas=1,
        data_julgamento_inicio="01/01/2024",
        data_julgamento_fim="31/03/2024",
    )

    assert isinstance(df, pd.DataFrame)
