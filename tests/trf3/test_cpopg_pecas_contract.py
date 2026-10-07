"""Contratos offline do download de peças do TRF3 (``download_pecas=True``).

Cada documento listado em ``/documentos`` é baixado em PDF por
``/v1/documentos/<id>/download``, que exige ``Content-Type: application/json``
e ``Accept: application/pdf``. O PDF de exemplo foi capturado por
``tests/fixtures/capture/trf3.py``.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest
import responses
from responses import matchers

import juscraper as jus
from juscraper.courts.trf3.download import BASE_URL_1G, BASE_URL_2G, documento_download_url
from tests._helpers import load_sample_bytes
from tests.trf3._api import carregar, id_processo_do_cenario, registrar_busca, registrar_processo

CNJ_PAGINADO = "50035362120254036342"


@pytest.fixture(autouse=True)
def _sem_espera(mocker):
    mocker.patch("time.sleep")


def _ids_documentos(endpoint: str, cenario: str) -> list[str]:
    return [doc["id"] for doc in carregar(endpoint, f"{cenario}_documentos_page_0.json")["result"]]


def _registrar_pdf(base_url: str, endpoint: str, cenario: str, id_documento: str, **kwargs) -> None:
    id_processo = id_processo_do_cenario(endpoint, cenario)
    responses.add(
        responses.GET,
        documento_download_url(base_url, id_documento),
        match=[
            matchers.header_matcher(
                {
                    "Content-Type": "application/json",
                    "Accept": "application/pdf",
                    "x-pagina-origem": f"{base_url}/processo/{id_processo}",
                }
            )
        ],
        **kwargs,
    )


def _pdf() -> bytes:
    return load_sample_bytes("trf3", "cpopg_pecas/documento.pdf")


def test_cpopg_download_pecas_default_false() -> None:
    """A assinatura pública mantém ``download_pecas=False`` e ``diretorio=None``."""
    for metodo in ("cpopg", "cposg"):
        sig = inspect.signature(getattr(jus.scraper("trf3"), metodo))
        assert sig.parameters["download_pecas"].default is False
        assert sig.parameters["diretorio"].default is None


@responses.activate
def test_cpopg_sem_download_pecas_nao_pede_documento(tmp_path) -> None:
    """Sem a flag, nenhuma peça é pedida nem gravada e não há coluna ``pecas``."""
    registrar_processo(BASE_URL_1G, "cpopg", "paginado")
    df = jus.scraper("trf3", sleep_time=0, download_path=str(tmp_path)).cpopg(CNJ_PAGINADO)

    assert "pecas" not in df.columns
    assert list(tmp_path.iterdir()) == []


@responses.activate
def test_cpopg_download_pecas_grava_pdfs(tmp_path) -> None:
    """Cada documento vira ``<diretorio>/<cnj>/<id>.pdf`` e a coluna ``pecas`` lista os caminhos."""
    registrar_processo(BASE_URL_1G, "cpopg", "paginado")
    ids = _ids_documentos("cpopg", "paginado")
    for id_documento in ids:
        _registrar_pdf(BASE_URL_1G, "cpopg", "paginado", id_documento, body=_pdf(), content_type="application/pdf")

    df = jus.scraper("trf3", sleep_time=0).cpopg(CNJ_PAGINADO, download_pecas=True, diretorio=str(tmp_path))

    salvos = df.iloc[0]["pecas"]
    assert salvos == [str(tmp_path / CNJ_PAGINADO / f"{i}.pdf") for i in ids]
    for caminho in salvos:
        assert Path(caminho).read_bytes() == _pdf()


@responses.activate
def test_cpopg_download_pecas_usa_download_path(tmp_path) -> None:
    """Sem ``diretorio``, as peças vão para o ``download_path`` do construtor."""
    registrar_processo(BASE_URL_1G, "cpopg", "paginado")
    for id_documento in _ids_documentos("cpopg", "paginado"):
        _registrar_pdf(BASE_URL_1G, "cpopg", "paginado", id_documento, body=_pdf(), content_type="application/pdf")

    df = jus.scraper("trf3", sleep_time=0, download_path=str(tmp_path)).cpopg(CNJ_PAGINADO, download_pecas=True)

    assert all(Path(p).parent == tmp_path / CNJ_PAGINADO for p in df.iloc[0]["pecas"])


@responses.activate
def test_cpopg_download_pecas_pula_peca_com_erro(tmp_path) -> None:
    """404 numa peça e resposta que não é PDF viram aviso; as demais são gravadas."""
    registrar_processo(BASE_URL_1G, "cpopg", "paginado")
    ids = _ids_documentos("cpopg", "paginado")
    _registrar_pdf(BASE_URL_1G, "cpopg", "paginado", ids[0], status=404)
    _registrar_pdf(BASE_URL_1G, "cpopg", "paginado", ids[1], body=b"<html></html>", content_type="text/html")
    _registrar_pdf(BASE_URL_1G, "cpopg", "paginado", ids[2], body=_pdf(), content_type="application/pdf")

    df = jus.scraper("trf3", sleep_time=0).cpopg(CNJ_PAGINADO, download_pecas=True, diretorio=str(tmp_path))

    assert df.iloc[0]["pecas"] == [str(tmp_path / CNJ_PAGINADO / f"{ids[2]}.pdf")]


@responses.activate
def test_cpopg_download_pecas_processo_ausente(tmp_path) -> None:
    """CNJ sem resultado ganha ``pecas`` vazia."""
    registrar_busca(BASE_URL_1G, "cpopg", "sem_resultado", "0000000-00.2099.4.03.0000")
    df = jus.scraper("trf3", sleep_time=0).cpopg("00000000020994030000", download_pecas=True, diretorio=str(tmp_path))

    assert df.iloc[0]["pecas"] == []


@responses.activate
def test_cposg_download_pecas_usa_host_de_2o_grau(tmp_path) -> None:
    """No ``cposg`` as peças vêm do host de 2º grau."""
    registrar_processo(BASE_URL_2G, "cposg", "pagina_unica")
    (id_documento,) = _ids_documentos("cposg", "pagina_unica")
    _registrar_pdf(BASE_URL_2G, "cposg", "pagina_unica", id_documento, body=_pdf(), content_type="application/pdf")

    df = jus.scraper("trf3", sleep_time=0).cposg(
        "50262427520264030000", download_pecas=True, diretorio=str(tmp_path)
    )

    assert df.iloc[0]["pecas"] == [str(tmp_path / "50262427520264030000" / f"{id_documento}.pdf")]
