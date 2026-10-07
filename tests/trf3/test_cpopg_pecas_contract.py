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
import requests
import responses
from responses import matchers

import juscraper as jus
from juscraper.core.exceptions import BotChallengeBlockedError
from juscraper.courts.trf3.download import BASE_URL_1G, BASE_URL_2G, baixar_documento, documento_download_url
from tests._helpers import load_sample_bytes
from tests.trf3._api import (
    carregar,
    documentos_em_duas_paginas,
    envelope_paginado,
    id_processo_do_cenario,
    registrar_busca,
    registrar_processo,
)

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


def _documentos_com(*docs: dict) -> list[dict]:
    """Página única de ``/documentos`` com os itens dados, no envelope da API."""
    return envelope_paginado(list(docs))


def _doc_real(endpoint: str = "cpopg", cenario: str = "paginado", indice: int = 0) -> dict:
    doc: dict = carregar(endpoint, f"{cenario}_documentos_page_0.json")["result"][indice]
    return doc


def _arquivos(raiz: Path) -> list[Path]:
    return sorted(p for p in raiz.rglob("*") if p.is_file())


@pytest.mark.parametrize("id_malicioso", ["../../fora", "/tmp/absoluto", "..", "a/b", "abc.pdf", ""])
@responses.activate
def test_download_pecas_pula_id_de_documento_fora_do_alfabeto(tmp_path, caplog, mocker, id_malicioso) -> None:
    """Id com ``/``, ``..`` ou caminho absoluto é pulado antes de montar URL e caminho.

    O id vem do JSON do servidor; sem a validação, ``../../fora`` gravaria fora
    de ``<diretorio>/<cnj>`` e ``/tmp/absoluto`` gravaria na raiz indicada.
    A peça válida do mesmo processo continua sendo baixada.
    """
    from juscraper.courts.trf3 import client

    valido = _doc_real()
    registrar_processo(
        BASE_URL_1G,
        "cpopg",
        "paginado",
        substituir={"documentos": _documentos_com({**valido, "id": id_malicioso}, valido)},
    )
    _registrar_pdf(BASE_URL_1G, "cpopg", "paginado", valido["id"], body=_pdf(), content_type="application/pdf")
    espiao = mocker.patch.object(client, "baixar_documento", wraps=client.baixar_documento)
    destino = tmp_path / "pecas"

    with caplog.at_level("WARNING", logger="juscraper.trf3"):
        df = jus.scraper("trf3", sleep_time=0).cpopg(CNJ_PAGINADO, download_pecas=True, diretorio=str(destino))

    assert df.iloc[0]["pecas"] == [str(destino / CNJ_PAGINADO / f"{valido['id']}.pdf")]
    assert _arquivos(tmp_path) == [destino / CNJ_PAGINADO / f"{valido['id']}.pdf"]
    assert [c.args[2] for c in espiao.call_args_list] == [valido["id"]]
    assert "id de documento inválido" in caplog.text
    assert not any("/v1/documentos/" in c.request.url and valido["id"] not in c.request.url for c in responses.calls)


@responses.activate
def test_download_pecas_pula_documento_sem_id(tmp_path, caplog) -> None:
    """Documento sem a chave ``id`` vira aviso e não derruba a chamada; os demais são baixados."""
    valido = _doc_real()
    sem_id = {k: v for k, v in valido.items() if k != "id"}
    registrar_processo(BASE_URL_1G, "cpopg", "paginado", substituir={"documentos": _documentos_com(sem_id, valido)})
    _registrar_pdf(BASE_URL_1G, "cpopg", "paginado", valido["id"], body=_pdf(), content_type="application/pdf")

    with caplog.at_level("WARNING", logger="juscraper.trf3"):
        df = jus.scraper("trf3", sleep_time=0).cpopg(CNJ_PAGINADO, download_pecas=True, diretorio=str(tmp_path))

    assert df.iloc[0]["pecas"] == [str(tmp_path / CNJ_PAGINADO / f"{valido['id']}.pdf")]
    assert "id de documento inválido None" in caplog.text


@responses.activate
def test_download_pecas_confere_que_o_arquivo_fica_no_diretorio_do_processo(tmp_path, caplog, mocker) -> None:
    """Segunda barreira: mesmo que um id escape da validação, nada é gravado fora de ``<diretorio>/<cnj>``."""
    from juscraper.courts.trf3 import client

    registrar_processo(
        BASE_URL_1G, "cpopg", "paginado", substituir={"documentos": _documentos_com({**_doc_real(), "id": "../fora"})}
    )
    mocker.patch.object(client, "token_valido", return_value=True)
    baixar = mocker.patch.object(client, "baixar_documento", return_value=_pdf())
    destino = tmp_path / "pecas"

    with caplog.at_level("WARNING", logger="juscraper.trf3"):
        df = jus.scraper("trf3", sleep_time=0).cpopg(CNJ_PAGINADO, download_pecas=True, diretorio=str(destino))

    assert df.iloc[0]["pecas"] == []
    assert _arquivos(tmp_path) == []
    baixar.assert_not_called()
    assert "sai do diretório do processo" in caplog.text


def test_baixar_documento_recusa_token_invalido_sem_requisitar() -> None:
    """``baixar_documento`` valida os dois tokens antes de montar a URL."""
    chamadas: list = []

    def request_fn(*args, **kwargs):  # pragma: no cover - não deve ser chamada
        chamadas.append((args, kwargs))

    valido = _doc_real()["id"]
    with pytest.raises(ValueError, match="id_documento inválido"):
        baixar_documento(request_fn, BASE_URL_1G, "../x", valido)
    with pytest.raises(ValueError, match="id_processo inválido"):
        baixar_documento(request_fn, BASE_URL_1G, valido, "/abs")
    assert chamadas == []


@responses.activate
def test_download_pecas_baixa_todas_as_paginas_de_documentos(tmp_path) -> None:
    """Com mais de 15 documentos, as peças da 2ª página de ``/documentos`` também são baixadas."""
    paginas_docs = documentos_em_duas_paginas()
    assert len(paginas_docs) == 2
    registrar_processo(BASE_URL_1G, "cpopg", "paginado", substituir={"documentos": paginas_docs})
    ids = [doc["id"] for pagina in paginas_docs for doc in pagina["result"]]
    for id_documento in ids:
        _registrar_pdf(BASE_URL_1G, "cpopg", "paginado", id_documento, body=_pdf(), content_type="application/pdf")

    df = jus.scraper("trf3", sleep_time=0).cpopg(CNJ_PAGINADO, download_pecas=True, diretorio=str(tmp_path))

    assert len(df.iloc[0]["documentos"]) == len(ids) > 15
    assert df.iloc[0]["pecas"] == [str(tmp_path / CNJ_PAGINADO / f"{i}.pdf") for i in ids]


@responses.activate
def test_download_pecas_bloqueio_akamai_interrompe(tmp_path) -> None:
    """403 ``Access Denied`` no PDF levanta ``BotChallengeBlockedError`` em vez de pular a peça."""
    registrar_processo(BASE_URL_1G, "cpopg", "paginado")
    ids = _ids_documentos("cpopg", "paginado")
    _registrar_pdf(
        BASE_URL_1G,
        "cpopg",
        "paginado",
        ids[0],
        body=b"<HTML><HEAD><TITLE>Access Denied</TITLE></HEAD><BODY><H1>Access Denied</H1></BODY></HTML>",
        status=403,
        content_type="text/html",
    )

    with pytest.raises(BotChallengeBlockedError):
        jus.scraper("trf3", sleep_time=0).cpopg(CNJ_PAGINADO, download_pecas=True, diretorio=str(tmp_path))
    url_pdf = documento_download_url(BASE_URL_1G, ids[0])
    assert sum(c.request.url == url_pdf for c in responses.calls) == 1


@pytest.mark.parametrize(
    "falha",
    [requests.ReadTimeout("sem resposta"), requests.ConnectionError("caiu")],
    ids=["timeout", "conexao"],
)
@responses.activate
def test_download_pecas_retenta_timeout_e_erro_de_conexao(tmp_path, falha) -> None:
    """O perfil ``documento`` retenta timeout de leitura e erro de conexão, como diz o CHANGELOG."""
    registrar_processo(BASE_URL_1G, "cpopg", "paginado")
    ids = _ids_documentos("cpopg", "paginado")
    _registrar_pdf(BASE_URL_1G, "cpopg", "paginado", ids[0], body=falha)
    for id_documento in ids:
        _registrar_pdf(BASE_URL_1G, "cpopg", "paginado", id_documento, body=_pdf(), content_type="application/pdf")

    df = jus.scraper("trf3", sleep_time=0).cpopg(CNJ_PAGINADO, download_pecas=True, diretorio=str(tmp_path))

    assert df.iloc[0]["pecas"] == [str(tmp_path / CNJ_PAGINADO / f"{i}.pdf") for i in ids]
