"""Filter-propagation contract for TJPI cjsg.

TJPI has no date filter on the backend — the client doesn't call
``normalize_datas``. Therefore the alias tests cover only ``query`` and
``termo``. Passing ``data_inicio`` kwargs today would raise ``TypeError``
from the downstream request function, not a friendly warning.
"""
import pandas as pd
import pytest
import responses
from responses.matchers import query_param_matcher

import juscraper as jus
from juscraper.courts.tjpi.download import BASE_URL, build_cjsg_params
from tests._helpers import load_sample


@responses.activate
def test_cjsg_all_filters_land_in_query_params(mocker):
    """Every TJPI public filter must reach the GET query-string."""
    mocker.patch("time.sleep")
    responses.add(
        responses.GET,
        BASE_URL,
        body=load_sample("tjpi", "cjsg/no_results.html"),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher(build_cjsg_params(
            "dano moral",
            page=1,
            tipo="Acordao",
            relator="FULANO DE TAL",
            classe="Apelacao",
            orgao="1a Camara Civel",
        ))],
    )

    df = jus.scraper("tjpi").cjsg(
        "dano moral",
        paginas=1,
        tipo="Acordao",
        relator="FULANO DE TAL",
        classe="Apelacao",
        orgao="1a Camara Civel",
    )

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_query_alias_emits_deprecation_warning(mocker):
    """The deprecated ``query`` alias is normalized before the request is built."""
    mocker.patch("time.sleep")
    responses.add(
        responses.GET,
        BASE_URL,
        body=load_sample("tjpi", "cjsg/no_results.html"),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher(build_cjsg_params("dano moral", page=1))],
    )

    with pytest.warns(DeprecationWarning, match="query.*deprecado"):
        df = jus.scraper("tjpi").cjsg(pesquisa=None, query="dano moral", paginas=1)

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_termo_alias_emits_deprecation_warning(mocker):
    """The deprecated ``termo`` alias is also normalized before the request is built."""
    mocker.patch("time.sleep")
    responses.add(
        responses.GET,
        BASE_URL,
        body=load_sample("tjpi", "cjsg/no_results.html"),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher(build_cjsg_params("dano moral", page=1))],
    )

    with pytest.warns(DeprecationWarning, match="termo.*deprecado"):
        df = jus.scraper("tjpi").cjsg(pesquisa=None, termo="dano moral", paginas=1)

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_data_inicio_kwarg_is_silently_dropped(mocker):
    """Locks current (buggy) behavior: TJPI has no date filter, and
    ``TJPIScraper.cjsg`` does not forward ``**kwargs`` to ``cjsg_download``,
    so passing ``data_inicio`` / ``data_fim`` today is a silent no-op —
    no ``TypeError``, no ``DeprecationWarning``, no ``UserWarning``. The
    request goes out with only the canonical filters.

    Ideal behavior per CLAUDE.md rule 6a is a ``DeprecationWarning`` from
    ``normalize_datas`` paired with a ``UserWarning`` from ``warn_unsupported``,
    but fixing that requires wiring ``normalize_datas`` into
    ``TJPIScraper.cjsg`` and forwarding ``**kwargs`` down the chain — work
    that belongs with the #84 refactor, not this contract PR. When that
    lands, replace this test with the warning-pair assertion the other
    1C tribunals already have.
    """
    mocker.patch("time.sleep")
    responses.add(
        responses.GET,
        BASE_URL,
        body=load_sample("tjpi", "cjsg/no_results.html"),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher(build_cjsg_params("dano moral", page=1))],
    )

    df = jus.scraper("tjpi").cjsg(
        "dano moral",
        paginas=1,
        data_inicio="2024-01-01",
        data_fim="2024-03-31",
    )

    assert isinstance(df, pd.DataFrame)
    # No ``page`` in the query other than ``page=1`` — confirms the date
    # kwargs were dropped upstream (not just ignored by the backend).
    assert len(responses.calls) == 1
    sent_url = responses.calls[0].request.url
    assert "data_inicio" not in sent_url
    assert "data_fim" not in sent_url
