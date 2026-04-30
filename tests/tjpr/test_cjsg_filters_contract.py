"""Filter-propagation contract for TJPR cjsg.

TJPR's ``cjsg`` exposes ``data_julgamento_inicio/fim`` and
``data_publicacao_inicio/fim``. Generic aliases ``data_inicio``/``data_fim``
ride ``normalize_datas`` to ``data_julgamento_*`` with a
``DeprecationWarning``. Search-term aliases are ``query`` and ``termo``.
"""
from urllib.parse import parse_qs, urlparse

import pandas as pd
import pytest
import responses

import juscraper as jus
from tests._helpers import load_sample

HOME_URL = "https://portal.tjpr.jus.br/jurisprudencia/"
SEARCH_URL = "https://portal.tjpr.jus.br/jurisprudencia/publico/pesquisa.do"


def _query_param_matcher(expected: dict[str, str]):
    def matcher(request):
        qs = parse_qs(urlparse(request.url).query, keep_blank_values=True)
        flat = {k: v[0] if v else "" for k, v in qs.items()}
        missing = {k: (expected[k], flat.get(k)) for k in expected if flat.get(k) != expected[k]}
        if missing:
            return False, f"query params mismatch: {missing}"
        return True, ""
    return matcher


def _post_body_subset_matcher(expected: dict[str, str]):
    def matcher(request):
        body = request.body or b""
        if isinstance(body, bytes):
            body = body.decode("utf-8")
        parsed = {k: v[0] if v else "" for k, v in parse_qs(body, keep_blank_values=True).items()}
        missing = {k: (expected[k], parsed.get(k)) for k in expected if parsed.get(k) != expected[k]}
        if missing:
            return False, f"body fields mismatch: {missing}"
        return True, ""
    return matcher


def _add_home():
    responses.add(
        responses.GET,
        HOME_URL,
        body=load_sample("tjpr", "cjsg/home.html"),
        status=200,
        content_type="text/html; charset=UTF-8",
    )


def _add_search(expected_body_subset: dict[str, str]):
    responses.add(
        responses.POST,
        SEARCH_URL,
        body=load_sample("tjpr", "cjsg/no_results.html"),
        status=200,
        content_type="text/html; charset=UTF-8",
        match=[
            _query_param_matcher({"actionType": "pesquisar"}),
            _post_body_subset_matcher(expected_body_subset),
        ],
    )


@responses.activate
def test_cjsg_all_filters_land_in_body(mocker):
    """Every TJPR public filter must reach the form body."""
    mocker.patch("time.sleep")
    _add_home()
    _add_search({
        "criterioPesquisa": "dano moral",
        "pageNumber": "1",
        "dataJulgamentoInicio": "01/01/2024",
        "dataJulgamentoFim": "31/03/2024",
        "dataPublicacaoInicio": "02/01/2024",
        "dataPublicacaoFim": "01/04/2024",
    })

    df = jus.scraper("tjpr").cjsg(
        "dano moral",
        paginas=1,
        data_julgamento_inicio="01/01/2024",
        data_julgamento_fim="31/03/2024",
        data_publicacao_inicio="02/01/2024",
        data_publicacao_fim="01/04/2024",
    )

    assert isinstance(df, pd.DataFrame)


# TJPR's ``cjsg`` re-passes ``**kwargs`` to ``cjsg_download`` without
# filtering the deprecated aliases that ``normalize_pesquisa`` already
# popped from its own copy. The second invocation of ``normalize_pesquisa``
# therefore sees both ``pesquisa`` (non-None) and ``query``/``termo``,
# which raises ``ValueError`` — the alias never reaches the wire.
# Compare with ``tjpi/client.py:108`` which explicitly drops the aliases
# before delegating. Tracked as a follow-up bug to fix during refactor #84.
ALIAS_BUG_REASON = (
    "TJPR cjsg re-passes deprecated aliases via **kwargs to cjsg_download; "
    "fixed during refactor #84 (see #144)."
)


@pytest.mark.xfail(strict=True, raises=ValueError, reason=ALIAS_BUG_REASON)
@responses.activate
def test_cjsg_query_alias_emits_deprecation_warning(mocker):
    """The deprecated ``query`` alias should normalize to ``pesquisa``."""
    mocker.patch("time.sleep")
    _add_home()
    _add_search({"criterioPesquisa": "dano moral", "pageNumber": "1"})

    with pytest.warns(DeprecationWarning, match="query.*deprecado"):
        df = jus.scraper("tjpr").cjsg(pesquisa=None, query="dano moral", paginas=1)

    assert isinstance(df, pd.DataFrame)


@pytest.mark.xfail(strict=True, raises=ValueError, reason=ALIAS_BUG_REASON)
@responses.activate
def test_cjsg_termo_alias_emits_deprecation_warning(mocker):
    """The deprecated ``termo`` alias should normalize to ``pesquisa``."""
    mocker.patch("time.sleep")
    _add_home()
    _add_search({"criterioPesquisa": "dano moral", "pageNumber": "1"})

    with pytest.warns(DeprecationWarning, match="termo.*deprecado"):
        df = jus.scraper("tjpr").cjsg(pesquisa=None, termo="dano moral", paginas=1)

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_data_inicio_alias_maps_to_data_julgamento(mocker):
    """``data_inicio``/``data_fim`` map to ``data_julgamento_*`` with a warning."""
    mocker.patch("time.sleep")
    _add_home()
    _add_search({
        "criterioPesquisa": "dano moral",
        "pageNumber": "1",
        "dataJulgamentoInicio": "01/01/2024",
        "dataJulgamentoFim": "31/03/2024",
    })

    with pytest.warns(DeprecationWarning) as warnings_list:
        df = jus.scraper("tjpr").cjsg(
            "dano moral",
            paginas=1,
            data_inicio="01/01/2024",
            data_fim="31/03/2024",
        )

    assert isinstance(df, pd.DataFrame)
    messages = [str(w.message) for w in warnings_list]
    assert any("data_inicio" in m and "deprecado" in m for m in messages)
    assert any("data_fim" in m and "deprecado" in m for m in messages)
