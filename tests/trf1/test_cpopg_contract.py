"""Contratos offline do ``TRF1Scraper.cpopg`` (API JSON da consulta pública).

A camada HTTP é simulada com ``responses`` a partir dos samples gravados por
``tests/fixtures/capture/trf1.py``. Os matchers conferem a raiz da API do
TRF1, o número buscado e o parâmetro ``page`` de cada página. O fluxo é o da
família :mod:`juscraper.courts._pje_api`, coberto em detalhe pelos contratos
do TRF3; aqui ficam a ligação do TRF1 (raiz, ausência de ``x-pagina-origem``,
perfis HTTP) e o formato das colunas com respostas reais do TRF1.
"""
from __future__ import annotations

import errno
import itertools
import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import responses
from responses import matchers

import juscraper as jus
from juscraper.courts._pje_api.download import RECURSOS_PAGINADOS, busca_url, documento_download_url, recurso_url
from juscraper.courts._pje_api.parse import COLUNAS_DETALHE
from juscraper.courts.trf1.client import API_URL_1G, TRF1Scraper
from juscraper.courts.trf1.schemas import OutputCpopgTRF1
from tests._helpers import assert_unknown_kwarg_raises, load_sample_bytes

SAMPLES = Path(__file__).parent / "samples" / "cpopg"
CNJ_PAGINADO = "10030632720234013304"
CNJ_NORMAL = "10088283520214013502"
CNJ_SEM_RESULTADO = "00000000020994010000"


@pytest.fixture(autouse=True)
def _sem_espera(mocker):
    """Zera as esperas de paginação e de backoff do retry."""
    mocker.patch("time.sleep")


def _carregar(nome: str) -> dict[str, Any]:
    resultado: dict[str, Any] = json.loads((SAMPLES / nome).read_text(encoding="utf-8"))
    return resultado


def _sem_pagina_origem(request) -> tuple[bool, str]:
    """A aplicação do TRF1 não manda ``x-pagina-origem``; a requisição também não."""
    if "x-pagina-origem" in request.headers:
        return False, "x-pagina-origem não deveria ir ao TRF1"
    return True, ""


def _registrar(cenario: str) -> str:
    """Registra busca, ``/dados`` e as páginas de cada recurso; devolve o ``idProcesso``."""
    busca = _carregar(f"{cenario}_busca.json")
    numero = busca["result"][0]["numeroProcesso"] if busca["result"] else None
    responses.add(
        responses.GET,
        busca_url(API_URL_1G),
        json=busca,
        match=[matchers.query_param_matcher({"page": "0", "numeroProcesso": numero}), _sem_pagina_origem],
    )
    id_processo: str = busca["result"][0]["idProcesso"]
    responses.add(
        responses.GET,
        recurso_url(API_URL_1G, id_processo, "dados"),
        json=_carregar(f"{cenario}_dados.json"),
        match=[_sem_pagina_origem],
    )
    for recurso in RECURSOS_PAGINADOS:
        for arquivo in sorted(SAMPLES.glob(f"{cenario}_{recurso}_page_*.json")):
            responses.add(
                responses.GET,
                recurso_url(API_URL_1G, id_processo, recurso),
                json=json.loads(arquivo.read_text(encoding="utf-8")),
                match=[matchers.query_param_matcher({"page": arquivo.stem.rsplit("_", 1)[1]}), _sem_pagina_origem],
            )
    return id_processo


def _itens(cenario: str, recurso: str) -> list[dict[str, Any]]:
    itens: list[dict[str, Any]] = []
    for arquivo in sorted(SAMPLES.glob(f"{cenario}_{recurso}_page_*.json")):
        itens.extend(json.loads(arquivo.read_text(encoding="utf-8"))["result"])
    return itens


@responses.activate
def test_cpopg_paginado_traz_todas_as_paginas_e_colunas() -> None:
    """55 movimentações em 4 páginas viram uma lista só, com as colunas da família."""
    _registrar("paginado")
    df = jus.scraper("trf1", sleep_time=0).cpopg("1003063-27.2023.4.01.3304")

    assert len(df) == 1
    assert df.columns[0] == "id_cnj"
    assert df.columns[-1] == "motivo_falha"
    row = df.iloc[0]
    assert row["id_cnj"] == CNJ_PAGINADO
    assert row["motivo_falha"] is None
    assert row["processo"] == "1003063-27.2023.4.01.3304"
    assert row["classe"] == "PROCEDIMENTO DO JUIZADO ESPECIAL CÍVEL (436)"
    assert row["data_distribuicao"] == "23/02/2023"
    assert row["jurisdicao"] == "Subseção Judiciária de Feira de Santana-BA"
    assert row["orgao_julgador_colegiado"] is None  # "" na API
    assert row["endereco_orgao"].startswith("Rua Turquia")

    assert len(row["movimentacoes"]) == 55 == len(_itens("paginado", "movimentacoes"))
    assert set(row["movimentacoes"][0]) == {"data", "descricao", "documento"}
    assert [p["nome"] for p in row["polo_ativo"]] == [i["nome"] for i in _itens("paginado", "poloAtivo")]
    assert row["outros_interessados"] == []
    doc = row["documentos"][0]
    assert doc == {
        "id": _itens("paginado", "documentos")[0]["id"],
        "data": "01/04/2025 10:11:51",
        "descricao": "DESPACHO (DESPACHO)",
        "binario": False,
    }
    OutputCpopgTRF1.model_validate(row.to_dict())
    assert all(c.request.url.startswith(API_URL_1G + "/v1/processos") for c in responses.calls)


@responses.activate
def test_cpopg_lote_com_processo_ausente() -> None:
    """CNJ que a busca não acha vira linha só com ``id_cnj``, sem motivo, e o lote segue."""
    _registrar("normal")
    responses.add(
        responses.GET,
        busca_url(API_URL_1G),
        json=_carregar("sem_resultado_busca.json"),
        match=[matchers.query_param_matcher({"page": "0", "numeroProcesso": "0000000-00.2099.4.01.0000"})],
    )

    df = jus.scraper("trf1", sleep_time=0).cpopg([CNJ_SEM_RESULTADO, CNJ_NORMAL])

    assert list(df["id_cnj"]) == [CNJ_SEM_RESULTADO, CNJ_NORMAL]
    assert list(df["motivo_falha"]) == [None, None]
    assert pd.isna(df.iloc[0]["processo"])
    assert df.iloc[1]["processo"] == "1008828-35.2021.4.01.3502"
    assert len(df.iloc[1]["movimentacoes"]) == 106


@responses.activate
def test_cpopg_lote_sem_processo_lido_mantem_colunas_do_detalhe() -> None:
    """Sem nenhum CNJ lido, o DataFrame ainda traz as colunas do detalhe, vazias (#442)."""
    responses.add(responses.GET, busca_url(API_URL_1G), json=_carregar("sem_resultado_busca.json"))

    df = jus.scraper("trf1", sleep_time=0).cpopg(CNJ_SEM_RESULTADO)

    assert list(df.columns) == ["id_cnj", *COLUNAS_DETALHE, "motivo_falha"]
    assert df.iloc[0][list(COLUNAS_DETALHE)].isna().all()


@responses.activate
def test_cpopg_download_e_parse_igualam_o_cpopg() -> None:
    """O fluxo em duas etapas devolve os dicionários da API e o mesmo DataFrame, sem ``motivo_falha``."""
    _registrar("normal")
    scraper = jus.scraper("trf1", sleep_time=0)
    brutos = scraper.cpopg_download(CNJ_NORMAL)
    assert set(brutos[0]) == {"busca", "dados", *RECURSOS_PAGINADOS}

    df = scraper.cpopg_parse(brutos, [CNJ_NORMAL])
    assert "motivo_falha" not in df.columns
    assert df.iloc[0]["processo"] == "1008828-35.2021.4.01.3502"

    # O alias deprecado ``htmls`` avisa e devolve o mesmo DataFrame.
    with pytest.warns(DeprecationWarning, match="htmls"):
        pd.testing.assert_frame_equal(scraper.cpopg_parse(htmls=brutos, id_cnj_list=[CNJ_NORMAL]), df)


def test_cpopg_parse_recusa_html_do_portal_antigo() -> None:
    """O HTML que o ``cpopg_download`` devolvia antes levanta ``TypeError``; ``htmls`` é alias deprecado."""
    scraper = jus.scraper("trf1")
    with pytest.warns(DeprecationWarning, match="htmls"), pytest.raises(TypeError, match="não o HTML"):
        scraper.cpopg_parse(htmls=["<html></html>"], id_cnj_list=[CNJ_NORMAL])


def test_cpopg_kwargs_desconhecidos_e_download_pecas_so_por_nome() -> None:
    """Kwarg desconhecido levanta ``TypeError``; ``download_pecas`` não é posicional."""
    scraper = jus.scraper("trf1")
    assert_unknown_kwarg_raises(scraper.cpopg, "filtro_inexistente", CNJ_NORMAL)
    with pytest.raises(TypeError):
        scraper.cpopg(CNJ_NORMAL, True)  # noqa: FBT003 (o teste confere que o posicional é recusado)


def test_perfis_http_sem_retry_de_rede() -> None:
    """O TRF1 respondeu sem travar: timeout com teto e sem nova tentativa de rede (padrão do core)."""
    perfis = TRF1Scraper.perfis_http
    assert perfis["api"].timeout == (10.0, 60.0)
    assert perfis["api"].expect_json
    assert not perfis["api"].retry_on_timeout
    assert not perfis["documento"].retry_on_connection_error


@responses.activate
def test_cpopg_download_pecas_grava_pdf(tmp_path) -> None:
    """Com ``download_pecas=True``, cada documento vira ``<diretorio>/<cnj>/<id>.pdf``."""
    _registrar("paginado")
    pdf = load_sample_bytes("trf1", "cpopg_pecas/documento.pdf")
    ids = [d["id"] for d in _itens("paginado", "documentos")]
    for id_documento in ids:
        responses.add(
            responses.GET,
            documento_download_url(API_URL_1G, id_documento),
            body=pdf,
            content_type="application/pdf",
            match=[matchers.header_matcher({"Content-Type": "application/json", "Accept": "application/pdf"})],
        )

    df = jus.scraper("trf1", sleep_time=0).cpopg(CNJ_PAGINADO, download_pecas=True, diretorio=str(tmp_path))

    esperados = [str(tmp_path / CNJ_PAGINADO / f"{i}.pdf") for i in ids]
    assert df.iloc[0]["pecas"] == esperados
    assert df.iloc[0]["pecas_falhas"] == []
    assert (tmp_path / CNJ_PAGINADO / f"{ids[0]}.pdf").read_bytes().startswith(b"%PDF")


@responses.activate
def test_cpopg_erro_ao_gravar_peca_encerra_as_pecas_do_processo_e_o_lote_segue(tmp_path, mocker) -> None:
    """Disco cheio na 2ª peça do 1º CNJ: ele sai com detalhe, a 1ª peça e o motivo; o 2º CNJ sai completo.

    A gravação que falha no meio não deixa arquivo truncado nem apaga a cópia
    de uma coleta anterior.
    """
    _registrar("paginado")
    _registrar("normal")
    pdf = load_sample_bytes("trf1", "cpopg_pecas/documento.pdf")
    ids = [d["id"] for d in _itens("paginado", "documentos")]
    ids_normal = [d["id"] for d in _itens("normal", "documentos")]
    for id_documento in ids + ids_normal:
        responses.add(
            responses.GET, documento_download_url(API_URL_1G, id_documento), body=pdf, content_type="application/pdf"
        )
    anterior = tmp_path / CNJ_PAGINADO / f"{ids[1]}.pdf"
    anterior.parent.mkdir()
    anterior.write_bytes(b"coleta anterior")
    gravar = Path.write_bytes
    gravacoes = itertools.count(1)

    def disco_cheio_na_segunda(caminho: Path, conteudo: bytes) -> int:
        if next(gravacoes) == 2:
            gravar(caminho, conteudo[:10])  # o disco enche no meio da escrita
            raise OSError(errno.ENOSPC, "No space left on device")
        return gravar(caminho, conteudo)

    mocker.patch.object(Path, "write_bytes", autospec=True, side_effect=disco_cheio_na_segunda)

    with pytest.warns(UserWarning, match="resposta_inesperada"):
        df = jus.scraper("trf1", sleep_time=0).cpopg(
            [CNJ_PAGINADO, CNJ_NORMAL], download_pecas=True, diretorio=str(tmp_path)
        )

    paginado, normal = df.iloc[0], df.iloc[1]
    assert paginado["processo"] == "1003063-27.2023.4.01.3304"
    assert paginado["motivo_falha"] == "resposta_inesperada"
    assert paginado["pecas"] == [str(tmp_path / CNJ_PAGINADO / f"{ids[0]}.pdf")]
    assert paginado["pecas_falhas"] == [{"id": i, "motivo_falha": "resposta_inesperada"} for i in ids[1:]]
    assert anterior.read_bytes() == b"coleta anterior"
    assert not list((tmp_path / CNJ_PAGINADO).glob("*.tmp"))
    assert normal["motivo_falha"] is None
    assert len(normal["pecas"]) == len(ids_normal)
    assert not any(i in c.request.url for i in ids[2:] for c in responses.calls)
