"""Offline contract tests for TJSP cjsg.

Mocks ``cjsg/resultadoCompleta.do`` (POST) + ``cjsg/trocaDePagina.do`` (GET)
with samples captured by ``tests/fixtures/capture/tjsp.py``. Validates the
public DataFrame contract and the POST body payload.

Also covers the pre-request guard that raises ``QueryTooLongError`` when
``pesquisa`` exceeds 120 characters — exercising it without any HTTP
interaction.
"""
import pandas as pd
import pytest
import responses
from responses.matchers import query_param_matcher, urlencoded_params_matcher
from responses.registries import OrderedRegistry

import juscraper as jus
from juscraper.courts.tjsp.exceptions import QueryTooLongError
from tests._helpers import load_sample_bytes
from tests.fixtures.capture._util import make_tjsp_cjsg_body

BASE = "https://esaj.tjsp.jus.br/cjsg"
CJSG_MIN_COLUMNS = {"processo", "cd_acordao", "cd_foro", "ementa"}


def _add_post(pesquisa: str) -> None:
    responses.add(
        responses.POST,
        f"{BASE}/resultadoCompleta.do",
        body=load_sample_bytes("tjsp", "cjsg/post_initial.html"),
        status=200,
        content_type="text/html; charset=latin-1",
        match=[urlencoded_params_matcher(make_tjsp_cjsg_body(pesquisa), allow_blank=True)],
    )


def _add_get(pagina: int, sample_path: str, *, conversation_id: str | None = None) -> None:
    params = {"tipoDeDecisao": "A", "pagina": str(pagina)}
    if conversation_id is not None:
        params["conversationId"] = conversation_id
    responses.add(
        responses.GET,
        f"{BASE}/trocaDePagina.do",
        body=load_sample_bytes("tjsp", sample_path),
        status=200,
        content_type="text/html; charset=latin-1",
        match=[query_param_matcher(params)],
    )


@responses.activate
def test_cjsg_typical_com_paginacao(tmp_path, mocker):
    """Typical multi-page query returns a DataFrame with the minimum schema."""
    mocker.patch("time.sleep")
    _add_post("dano moral")
    # Page 1 is fetched without conversationId; page 2 reuses it when the
    # first-page HTML exposes ``<input name='conversationId' value='...'>``.
    # Match the common case: page 1 has no conversationId, page 2 has it.
    _add_get(1, "cjsg/results_normal_page_01.html")
    _add_get(2, "cjsg/results_normal_page_02.html")

    df = jus.scraper("tjsp", download_path=str(tmp_path)).cjsg(
        "dano moral", paginas=range(1, 3)
    )

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_MIN_COLUMNS
    assert len(df) > 0


@responses.activate
def test_cjsg_single_page(tmp_path, mocker):
    """Query whose hits fit in a single page skips the per-page loop."""
    mocker.patch("time.sleep")
    _add_post("usucapiao extraordinario predio rural familia")
    _add_get(1, "cjsg/single_page.html")

    df = jus.scraper("tjsp", download_path=str(tmp_path)).cjsg(
        "usucapiao extraordinario predio rural familia", paginas=1
    )

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_MIN_COLUMNS
    assert len(df) > 0


@responses.activate
def test_cjsg_no_results(tmp_path, mocker):
    """Zero-result query returns an empty DataFrame instead of raising."""
    mocker.patch("time.sleep")
    _add_post("juscraper_probe_zero_hits_xyzqwe")
    _add_get(1, "cjsg/no_results.html")

    df = jus.scraper("tjsp", download_path=str(tmp_path)).cjsg(
        "juscraper_probe_zero_hits_xyzqwe", paginas=1
    )

    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_cjsg_query_too_long_raises(tmp_path):
    """Pre-request guard: a pesquisa > 120 chars must raise before any HTTP."""
    pesquisa = "a" * 121
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    with pytest.raises(QueryTooLongError):
        scraper.cjsg(pesquisa, paginas=1)


@responses.activate
def test_cjsg_busca_aberta_sem_pesquisa(tmp_path, mocker):
    """``cjsg(paginas=...)`` sem ``pesquisa`` deve funcionar (issue #229).

    Espelha o comportamento de :meth:`TJSPScraper.cjpg`: ``pesquisa`` tem
    default ``""``, permitindo busca aberta por filtros (classe, assunto,
    data) sem termo textual. Antes do fix, faltava o argumento e Python
    levantava ``TypeError: cjsg() missing 1 required positional argument:
    'pesquisa'``.
    """
    mocker.patch("time.sleep")
    _add_post("")
    _add_get(1, "cjsg/no_results.html")

    df = jus.scraper("tjsp", download_path=str(tmp_path)).cjsg(paginas=1)

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_post_inicial_retenta_403(tmp_path, mocker):
    """POST inicial retenta 403 transitorio do WAF e prossegue (refs #233, #255).

    Antes do #255, qualquer 403 no ``resultadoCompleta.do`` abortava a
    coleta na 1a tentativa. Agora a chamada delega ao retry centralizado
    em ``HTTPScraper._request_with_retry``.
    """
    mocker.patch("time.sleep")
    pesquisa = "usucapiao extraordinario predio rural familia"
    # Primeira tentativa: 403 (sem matcher de body — a transitoria nao precisa
    # validar payload). Segunda tentativa: 200 com o sample habitual (com matcher).
    responses.add(responses.POST, f"{BASE}/resultadoCompleta.do", status=403)
    _add_post(pesquisa)
    _add_get(1, "cjsg/single_page.html")

    df = jus.scraper("tjsp", download_path=str(tmp_path)).cjsg(pesquisa, paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_MIN_COLUMNS
    # POST 403 + POST 200 + GET 200 = 3 chamadas. Trava regressão caso o retry
    # do POST inicial pare de acontecer (ex.: alguém remove o wrapping em
    # ``_request_with_retry``).
    assert len(responses.calls) == 3


@responses.activate
def test_cjsg_count_only_returns_int(tmp_path, mocker):
    """``count_only=True`` short-circuits to an int after page 1 (issue #92)."""
    mocker.patch("time.sleep")
    _add_post("dano moral")
    _add_get(1, "cjsg/results_normal_page_01.html")

    n = jus.scraper("tjsp", download_path=str(tmp_path)).cjsg(
        "dano moral", count_only=True,
    )

    assert isinstance(n, int)
    assert n == 2571077  # totalResultadoAbaRetornoFiltro-A no sample
    # Garante que NAO houve fetch de pagina 2+. POST + 1 GET = 2 chamadas.
    assert len(responses.calls) == 2


@responses.activate
def test_cjsg_count_only_zero_results(tmp_path, mocker):
    """``count_only=True`` em busca sem hits retorna 0 (issue #92)."""
    mocker.patch("time.sleep")
    _add_post("juscraper_probe_zero_hits_xyzqwe")
    _add_get(1, "cjsg/no_results.html")

    n = jus.scraper("tjsp", download_path=str(tmp_path)).cjsg(
        "juscraper_probe_zero_hits_xyzqwe", count_only=True,
    )

    assert n == 0


@responses.activate
def test_cjsg_count_only_ignora_paginas_com_warning(tmp_path, mocker):
    """``count_only=True`` + ``paginas != None`` emite UserWarning e ignora."""
    mocker.patch("time.sleep")
    _add_post("dano moral")
    _add_get(1, "cjsg/results_normal_page_01.html")

    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    with pytest.warns(UserWarning, match="paginas e ignorado"):
        n = scraper.cjsg("dano moral", paginas=range(1, 5), count_only=True)

    assert isinstance(n, int)
    assert n == 2571077


def test_cjsg_count_only_query_too_long_raises(tmp_path):
    """TJSP cjsg + count_only=True mantem o guard de 120 chars (issue #92).

    O ramo ``count_only`` desvia em :meth:`EsajSearchScraper.cjsg` antes
    de chegar a :meth:`cjsg_download` (onde o caminho normal corre
    :func:`validate_pesquisa_length`). O override TJSP de
    ``_cjsg_count_only`` precisa preservar o check para que
    ``QueryTooLongError`` continue propagando limpo em vez de virar
    backend-reject opaco.
    """
    pesquisa = "a" * 121
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    with pytest.raises(QueryTooLongError):
        scraper.cjsg(pesquisa, count_only=True)


def test_cjsg_count_only_auto_chunk_false_raises_on_long_window(tmp_path):
    """auto_chunk=False + janela > 366d + count_only=True raises ValueError (#92).

    Replica o comportamento estrito do caminho normal — ``cjsg_download``
    valida via ``apply_input_pipeline_search(max_dias=366)``. Sem o check
    explicito em ``_cjsg_count_only``, o probe enviaria a janela longa pro
    backend e o usuario veria um erro opaco no probe em vez do
    ``ValueError`` canonico.
    """
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    with pytest.raises(ValueError, match="366"):
        scraper.cjsg(
            "dano moral",
            data_julgamento_inicio="01/01/2020",
            data_julgamento_fim="01/01/2022",
            auto_chunk=False,
            count_only=True,
        )


@responses.activate(registry=OrderedRegistry)
def test_cjsg_count_only_sums_across_chunks(tmp_path, mocker):
    """count_only=True + janela > 366d soma contagens cross-window (#92).

    Espelho do ``test_cjpg_count_only_sums_across_chunks`` para o caminho
    base eSAJ (compartilhado por TJAC/TJAL/TJAM/TJCE/TJMS/TJSP). Mocka 2
    POST+GET distintos por janela e afere a soma. Vai falhar se
    ``_cjsg_count_only`` deixar de iterar via ``iter_date_windows`` ou
    deixar de somar (ex.: regressao para usar so a primeira janela).
    """
    mocker.patch("time.sleep")

    # Janela 1: 02/01/2020 -> 02/01/2021 (HTML retorna 2_571_077)
    # Janela 2: 03/01/2021 -> 02/01/2022 (HTML retorna 78)
    body_w1 = make_tjsp_cjsg_body(
        "dano moral", data_inicio="02/01/2020", data_fim="02/01/2021",
    )
    responses.add(
        responses.POST,
        f"{BASE}/resultadoCompleta.do",
        body=load_sample_bytes("tjsp", "cjsg/post_initial.html"),
        status=200,
        content_type="text/html; charset=latin-1",
        match=[urlencoded_params_matcher(body_w1, allow_blank=True)],
    )
    responses.add(
        responses.GET,
        f"{BASE}/trocaDePagina.do",
        body=load_sample_bytes("tjsp", "cjsg/results_normal_page_01.html"),
        status=200,
        content_type="text/html; charset=latin-1",
        match=[query_param_matcher({"tipoDeDecisao": "A", "pagina": "1"})],
    )

    body_w2 = make_tjsp_cjsg_body(
        "dano moral", data_inicio="03/01/2021", data_fim="02/01/2022",
    )
    responses.add(
        responses.POST,
        f"{BASE}/resultadoCompleta.do",
        body=load_sample_bytes("tjsp", "cjsg/post_initial.html"),
        status=200,
        content_type="text/html; charset=latin-1",
        match=[urlencoded_params_matcher(body_w2, allow_blank=True)],
    )
    responses.add(
        responses.GET,
        f"{BASE}/trocaDePagina.do",
        body=load_sample_bytes("tjsp", "cjsg/single_page.html"),
        status=200,
        content_type="text/html; charset=latin-1",
        match=[query_param_matcher({"tipoDeDecisao": "A", "pagina": "1"})],
    )

    n = jus.scraper("tjsp", download_path=str(tmp_path)).cjsg(
        "dano moral",
        data_julgamento_inicio="02/01/2020",
        data_julgamento_fim="02/01/2022",
        count_only=True,
    )

    assert isinstance(n, int)
    assert n == 2571077 + 78  # soma bruta cross-janela
    assert len(responses.calls) == 4  # 2 POSTs + 2 GETs


@responses.activate
def test_cjsg_get_1a_pagina_retenta_503(tmp_path, mocker):
    """GET da pagina 1 retenta 503 transitorio (mesmo perfil das paginas >=2)."""
    mocker.patch("time.sleep")
    pesquisa = "usucapiao extraordinario predio rural familia"
    _add_post(pesquisa)
    # Primeira tentativa do GET pagina=1: 503. Segunda: 200 via _add_get.
    responses.add(responses.GET, f"{BASE}/trocaDePagina.do", status=503)
    _add_get(1, "cjsg/single_page.html")

    df = jus.scraper("tjsp", download_path=str(tmp_path)).cjsg(pesquisa, paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_MIN_COLUMNS
    # POST 200 + GET 503 + GET 200 = 3 chamadas. Trava regressão simétrica
    # à do POST inicial.
    assert len(responses.calls) == 3
