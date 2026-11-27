"""Offline contract tests for TRF5 ``cpopg`` (PJe consulta pública).

Same shape as ``tests/trf1/test_cpopg_contract.py``. Distinct from the TRF1
suite to keep sample fixtures and matchers independent — TRF5 ships
different form field IDs (``j_id162`` vs ``j_id165``).
"""
from __future__ import annotations

from urllib.parse import parse_qsl

import pandas as pd
import pytest
import responses

import juscraper as jus
from juscraper.courts._trf.parse import COLUNAS_DETALHE, parse_detail
from tests._helpers import load_sample, load_sample_bytes


def _subset_form_matcher(expected: dict[str, str]):
    """``responses`` 0.x lacks ``strict_match`` — homemade subset matcher."""

    def _match(request) -> tuple[bool, str]:
        body = request.body or b""
        if isinstance(body, bytes):
            body = body.decode("utf-8")
        actual = dict(parse_qsl(body, keep_blank_values=True))
        for key, value in expected.items():
            if actual.get(key) != value:
                return False, (
                    f"expected {key!r}={value!r}, got {actual.get(key)!r}"
                )
        return True, ""

    return _match


LIST_URL = "https://pje1g.trf5.jus.br/pjeconsulta/ConsultaPublica/listView.seam"
DETAIL_URL = (
    "https://pje1g.trf5.jus.br/pjeconsulta/"
    "ConsultaPublica/DetalheProcessoConsultaPublica/listView.seam"
)


@responses.activate
def test_cpopg_returns_dataframe_with_canonical_columns() -> None:
    """Happy path: one CNJ → one row with parties, movements and documents."""
    responses.add(
        responses.GET,
        LIST_URL,
        body=load_sample("trf5", "cpopg/form_initial.html"),
        content_type="text/html; charset=utf-8",
    )
    responses.add(
        responses.POST,
        LIST_URL,
        body=load_sample("trf5", "cpopg/search_one_result.html"),
        content_type="text/xml; charset=utf-8",
        match=[
            _subset_form_matcher(
                {
                    "fPP:numProcesso-inputNumeroProcessoDecoration:"
                    "numProcesso-inputNumeroProcesso": "0058457-31.2025.4.05.8000",
                    "AJAXREQUEST": "_viewRoot",
                    "fPP:j_id244": "fPP:j_id244",
                    # Desde 11/2026 o TRF5 usa o autocomplete ``classeJudicial``
                    # e o bloco de datas, como o resto da família.
                    "fPP:j_id189:classeJudicial": "",
                    "fPP:j_id189:sgbClasseJudicial_selection": "",
                    "fPP:dataAutuacaoDecoration:dataAutuacaoInicioInputDate": "",
                    "fPP:dataAutuacaoDecoration:dataAutuacaoFimInputDate": "",
                },
            ),
        ],
    )
    responses.add(
        responses.GET,
        DETAIL_URL,
        body=load_sample_bytes("trf5", "cpopg/detail_normal.html"),
        content_type="text/html",
    )

    scraper = jus.scraper("trf5", sleep_time=0)
    df = scraper.cpopg("00584573120254058000")

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    expected = {
        "id_cnj",
        "processo",
        "classe",
        "assunto",
        "data_distribuicao",
        "orgao_julgador",
        "polo_ativo",
        "polo_passivo",
        "movimentacoes",
        "documentos",
    }
    assert expected <= set(df.columns)
    row = df.iloc[0]
    assert row["id_cnj"] == "00584573120254058000"
    assert row["processo"] == "0058457-31.2025.4.05.8000"
    # Órgão e endereço vêm em negrito num painel de rótulo vazio.
    assert row["orgao_julgador"] == "Ambiente do Centro de Conciliação de Maceió"
    assert row["endereco_orgao"] == "Avenida Menino Marcelo, Serraria, MACEIó - AL - CEP: 57046-000"  # grafia da fonte
    # TRF5 sample has 2 active polo (party + lawyer) and 1 passive (defendant).
    assert isinstance(row["polo_ativo"], list) and len(row["polo_ativo"]) >= 1
    assert isinstance(row["polo_passivo"], list) and len(row["polo_passivo"]) >= 1


@responses.activate
def test_cpopg_missing_process_keeps_detail_columns_empty() -> None:
    """CNJ ausente sai numa linha com ``id_cnj``, sem pedir o detalhe.

    As colunas do detalhe continuam no DataFrame, vazias, mesmo quando
    nenhum CNJ do lote foi lido (#442: o notebook selecionava
    ``df[["processo", "classe", "orgao_julgador"]]`` e caía em ``KeyError``).
    """
    responses.add(
        responses.GET,
        LIST_URL,
        body=load_sample("trf5", "cpopg/form_initial.html"),
    )
    responses.add(
        responses.POST,
        LIST_URL,
        body=load_sample("trf5", "cpopg/search_no_results.html"),
    )

    scraper = jus.scraper("trf5", sleep_time=0)
    df = scraper.cpopg("00000000020994050000")
    assert len(df) == 1
    assert df.iloc[0]["id_cnj"] == "00000000020994050000"
    assert list(df.columns) == [*COLUNAS_DETALHE, "id_cnj", "motivo_falha"]
    assert all(v is None for v in df[list(COLUNAS_DETALHE)].to_numpy().ravel())
    assert df.iloc[0]["motivo_falha"] is None


@responses.activate
def test_cpopg_lote_sem_nenhuma_resposta_mantem_colunas_do_detalhe() -> None:
    """Falha de requisição em todo o lote: colunas do detalhe vazias, motivo na linha."""
    responses.add(responses.GET, LIST_URL, status=404)

    scraper = jus.scraper("trf5", sleep_time=0)
    with pytest.warns(UserWarning, match="http_404"):
        df = scraper.cpopg(["00000000020994050000", "00584573120254058000"])
    assert list(df.columns) == [*COLUNAS_DETALHE, "id_cnj", "motivo_falha"]
    assert list(df["motivo_falha"]) == ["http_404", "http_404"]
    assert all(v is None for v in df[list(COLUNAS_DETALHE)].to_numpy().ravel())


def test_cpopg_parse_sem_html_mantem_colunas_do_detalhe() -> None:
    """``cpopg_parse`` só com ``None`` sai com as colunas do detalhe vazias."""
    scraper = jus.scraper("trf5", sleep_time=0)
    df = scraper.cpopg_parse([None], ["00000000020994050000"])
    assert len(df) == 1
    assert list(df.columns) == [*COLUNAS_DETALHE, "id_cnj"]
    assert all(v is None for v in df[list(COLUNAS_DETALHE)].to_numpy().ravel())


def test_colunas_detalhe_sao_as_chaves_de_parse_detail() -> None:
    """``COLUNAS_DETALHE`` acompanha o registro de ``parse_detail``, na mesma ordem."""
    record = parse_detail(load_sample_bytes("trf5", "cpopg/detail_normal.html").decode("latin-1"))
    assert tuple(record) == COLUNAS_DETALHE


@pytest.mark.parametrize("metodo", ["cpopg", "cpopg_download"])
def test_cpopg_rejects_unknown_kwargs(metodo: str) -> None:
    """Kwarg desconhecido vira ``TypeError`` que cita o método público chamado."""
    scraper = jus.scraper("trf5", sleep_time=0)
    with pytest.raises(TypeError, match=rf"^TRF5Scraper\.{metodo} got unexpected keyword"):
        getattr(scraper, metodo)("00584573120254058000", magistrado="x")


@responses.activate
def test_fetch_movs_page_decodes_fragment_as_utf8() -> None:
    """The Richfaces AJAX fragment is UTF-8; ``fetch_movs_page`` must not latin-1 it.

    Regression for the double-encoding bug where accented movimentação text came
    back mojibaked (``petição`` -> ``petiÃ§Ã£o``) because the UTF-8 partial
    response was decoded as latin-1. Serves the *raw bytes* of a fragment
    captured live (TRF5 process with 505 movs) and asserts the decoded text
    carries clean accents.

    TRF5 ships no paginated-detail sample, so we build a synthetic
    ``MovsPagination`` — the focus here is the decode, not the slider extraction
    (covered live by ``test_cpopg_returns_all_movs_pages``).
    """
    from juscraper.courts._trf.download import DETAIL_PATH, MovsPagination, fetch_movs_page

    info = MovsPagination(
        form_id="j_id156",
        slider_input_name="j_id156:j_id220:j_id221Slider",
        ajax_source_name="j_id156:j_id220:j_id221",
        container_id="j_id156:processoEventoPanel",
        max_pages=2,
        view_state="-1234567890",
    )

    scraper = jus.scraper("trf5", sleep_time=0)
    responses.add(
        responses.POST,
        scraper.BASE_URL + DETAIL_PATH,
        body=load_sample_bytes("trf5", "cpopg/movs_page_2.html"),  # raw UTF-8 bytes
        status=200,
        content_type="text/xml; charset=UTF-8",
    )

    fragment = fetch_movs_page(scraper, scraper.BASE_URL, info, 2, "ca-token")

    assert "ç" in fragment, "fragmento sem acento — decode suspeito"
    assert "Ã§" not in fragment and "Ã£" not in fragment, (
        "mojibake: fragmento UTF-8 decodificado como latin-1"
    )


@responses.activate
def test_cpopg_batch_continues_after_download_error() -> None:
    """Erro de rede num CNJ não derruba o batch — vira linha só com ``id_cnj``."""
    responses.add(
        responses.GET,
        LIST_URL,
        body=load_sample("trf5", "cpopg/form_initial.html"),
    )
    responses.add(responses.POST, LIST_URL, body=ConnectionError("kaboom"))
    responses.add(
        responses.POST,
        LIST_URL,
        body=load_sample("trf5", "cpopg/search_one_result.html"),
    )
    responses.add(
        responses.GET,
        DETAIL_URL,
        body=load_sample_bytes("trf5", "cpopg/detail_normal.html"),
    )

    scraper = jus.scraper("trf5", sleep_time=0)
    # ConnectionError nativo, e não o do requests: fora do vocabulário de motivos.
    with pytest.warns(UserWarning, match="resposta_inesperada"):
        df = scraper.cpopg(["00000000020994050000", "00584573120254058000"])
    assert list(df["motivo_falha"]) == ["resposta_inesperada", None]
    assert list(df["id_cnj"]) == ["00000000020994050000", "00584573120254058000"]
    assert pd.isna(df.iloc[0].get("processo")) or df.iloc[0].get("processo") is None
    assert df.iloc[1]["processo"] == "0058457-31.2025.4.05.8000"


@responses.activate
def test_cpopg_batch_continues_after_parse_error(monkeypatch) -> None:
    """Erro no parser de um item vira linha só com ``id_cnj`` e o batch segue."""
    responses.add(
        responses.GET,
        LIST_URL,
        body=load_sample("trf5", "cpopg/form_initial.html"),
    )
    responses.add(
        responses.POST,
        LIST_URL,
        body=load_sample("trf5", "cpopg/search_one_result.html"),
    )
    responses.add(
        responses.GET,
        DETAIL_URL,
        body=load_sample_bytes("trf5", "cpopg/detail_normal.html"),
    )
    responses.add(
        responses.POST,
        LIST_URL,
        body=load_sample("trf5", "cpopg/search_one_result.html"),
    )
    responses.add(
        responses.GET,
        DETAIL_URL,
        body=load_sample_bytes("trf5", "cpopg/detail_normal.html"),
    )

    # ``parse_detail`` é resolvido no namespace de ``_trf.base`` (onde
    # ``cpopg_parse`` o chama).
    from juscraper.courts._trf import base as trf_base

    real_parse = trf_base.parse_detail
    calls = {"n": 0}

    def flaky_parse(html):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError("HTML inesperado")
        return real_parse(html)

    monkeypatch.setattr(trf_base, "parse_detail", flaky_parse)

    scraper = jus.scraper("trf5", sleep_time=0)
    with pytest.warns(UserWarning, match="resposta_inesperada"):
        df = scraper.cpopg(["00584573120254058000", "00584573120254058001"])
    assert list(df["motivo_falha"]) == ["resposta_inesperada", None]
    assert list(df["id_cnj"]) == ["00584573120254058000", "00584573120254058001"]
    assert pd.isna(df.iloc[0].get("processo")) or df.iloc[0].get("processo") is None
    assert df.iloc[1]["processo"] == "0058457-31.2025.4.05.8000"
