"""Contratos offline de ``cpopg(..., download_pecas=True)`` no TJSP.

O processo é o incidente de ``test_cpopg_contract.py``: as movimentações
saem em três páginas do ``carregarMovimentacoesAjax.do``, com um documento
sob senha na página 1 (190277046) e dois públicos (186579563 na página 1,
175634201 na página 3). Cada documento público passa por
``abrirDocumentoVinculadoMovimentacao.do``, que redireciona (302) para a pasta
digital gravada em ``samples/documentos/``, e por ``getPDF.do`` com os
``parametros`` daquela pasta.
"""

import json
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import pytest
import requests
import responses
from responses.matchers import query_param_matcher

import juscraper as jus
from juscraper.courts._esaj.pasta import parse_parametros_pasta
from tests._helpers import PDF_FALSO, load_sample, load_sample_bytes
from tests.tjsp.test_cpopg_contract import (
    CNJ_INCIDENTE,
    CURSOR_PAGINA_2,
    CURSOR_PAGINA_3,
    ESAJ,
    _chamadas,
    _registrar_busca_incidente,
    _registrar_pagina_movimentacoes,
)

PUBLICOS = ("186579563", "175634201")
SOB_SENHA = "190277046"
ROTA_DOCUMENTO = "abrirDocumentoVinculadoMovimentacao.do"
_REDIRECIONAMENTOS = json.loads(load_sample("tjsp", "documentos/redirecionamentos.json"))
_HTML = "text/html;charset=UTF-8"


def _registrar_processo():
    _registrar_busca_incidente()
    _registrar_pagina_movimentacoes(1)
    _registrar_pagina_movimentacoes(2, CURSOR_PAGINA_2)
    _registrar_pagina_movimentacoes(3, CURSOR_PAGINA_3)


def _registrar_documento(cd_documento, pasta=None, pdf=PDF_FALSO):
    """302 do eSAJ para a pasta gravada, a pasta (ou ``pasta``) e o ``getPDF.do`` dela."""
    destino = _REDIRECIONAMENTOS[f"movimentacao_{cd_documento}"]
    responses.add(
        responses.GET,
        f"{ESAJ}/cpopg/{ROTA_DOCUMENTO}",
        status=302,
        headers={"Location": destino},
        match=[query_param_matcher({"cdDocumento": cd_documento}, strict_match=False)],
    )
    corpo = pasta if pasta is not None else load_sample_bytes("tjsp", f"documentos/pasta_{cd_documento}.html")
    responses.add(
        responses.GET,
        destino.split("?")[0],
        body=corpo,
        content_type=_HTML,
        match=[query_param_matcher(dict(parse_qsl(urlsplit(destino).query, keep_blank_values=True)))],
    )
    parametros = parse_parametros_pasta(load_sample("tjsp", f"documentos/pasta_{cd_documento}.html"))
    responses.add(
        responses.GET,
        f"{ESAJ}/pastadigital/getPDF.do",
        body=pdf,
        match=[query_param_matcher(dict(parse_qsl(parametros, keep_blank_values=True)))],
    )


def _documentos_pedidos():
    return [r.params["cdDocumento"] for r in _chamadas(ROTA_DOCUMENTO)]


def _indices(rota):
    return [i for i, c in enumerate(responses.calls) if c.request.url.split("?")[0].endswith(rota)]


@responses.activate
def test_download_pecas_baixa_so_os_publicos_e_move_para_diretorio(tmp_path, mocker):
    mocker.patch("time.sleep")
    _registrar_processo()
    for cd in PUBLICOS:
        _registrar_documento(cd)
    download_path, diretorio = tmp_path / "download", tmp_path / "destino"

    result = jus.scraper("tjsp", download_path=str(download_path)).cpopg(
        CNJ_INCIDENTE, download_pecas=True, diretorio=str(diretorio)
    )

    assert _documentos_pedidos() == list(PUBLICOS)
    # A pasta só libera documento de página que a sessão já carregou: os
    # pedidos de documento vêm depois da última página de movimentações.
    assert min(_indices(ROTA_DOCUMENTO)) > max(_indices("carregarMovimentacoesAjax.do"))
    assert len(_chamadas("getPDF.do")) == 2
    assert not download_path.exists()

    movimentacoes = result["movimentacoes"].set_index("cd_documento", drop=False)
    assert len(result["movimentacoes"]) == 14
    assert movimentacoes.loc[SOB_SENHA, "documento_publico"] is False
    assert movimentacoes.loc[SOB_SENHA, "caminho_documento"] is None
    for cd in PUBLICOS:
        caminho = Path(movimentacoes.loc[cd, "caminho_documento"])
        assert movimentacoes.loc[cd, "documento_publico"] is True
        assert caminho.is_relative_to(diretorio)
        assert caminho.parts[-2:] == ("documentos", f"{cd}.pdf")
        assert caminho.read_bytes() == PDF_FALSO
    sem_documento = result["movimentacoes"]["cd_documento"].isna()
    assert sem_documento.sum() == 11
    assert result["movimentacoes"].loc[sem_documento, "caminho_documento"].isna().all()
    assert sorted(p.name for p in diretorio.rglob("*") if p.is_file()) == [f"{cd}.pdf" for cd in sorted(PUBLICOS)]


@responses.activate
def test_cpopg_sem_download_pecas_nao_pede_documento(tmp_path, mocker):
    mocker.patch("time.sleep")
    _registrar_processo()

    result = jus.scraper("tjsp", download_path=str(tmp_path)).cpopg(CNJ_INCIDENTE)

    assert _documentos_pedidos() == []
    movimentacoes = result["movimentacoes"].set_index("cd_documento", drop=False)
    assert movimentacoes.loc[PUBLICOS[0], "documento_publico"] is True
    assert result["movimentacoes"]["caminho_documento"].isna().all()


@responses.activate
def test_reexecucao_pede_so_o_pdf_que_falta(tmp_path, mocker):
    """Sem PDF faltando, o processo não é baixado de novo; com um faltando, só ele é pedido."""
    mocker.patch("time.sleep")
    _registrar_processo()
    for cd in PUBLICOS:
        _registrar_documento(cd)
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))

    scraper.cpopg_download(CNJ_INCIDENTE, download_pecas=True)
    pdfs = {p.stem: p for p in tmp_path.rglob("*.pdf")}
    assert set(pdfs) == set(PUBLICOS)

    responses.calls.reset()
    scraper.cpopg_download(CNJ_INCIDENTE, download_pecas=True)
    assert len(responses.calls) == 0

    pdfs[PUBLICOS[1]].unlink()
    scraper.cpopg_download(CNJ_INCIDENTE, download_pecas=True)
    assert _documentos_pedidos() == [PUBLICOS[1]]
    assert pdfs[PUBLICOS[1]].read_bytes() == PDF_FALSO


@responses.activate
def test_download_sem_pecas_e_reexecucao_com_pecas_completa_os_pdfs(tmp_path, mocker):
    """Um download anterior sem ``download_pecas`` não impede o pedido dos PDFs depois."""
    mocker.patch("time.sleep")
    _registrar_processo()
    for cd in PUBLICOS:
        _registrar_documento(cd)
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))

    scraper.cpopg_download(CNJ_INCIDENTE)
    assert _documentos_pedidos() == []

    scraper.cpopg_download(CNJ_INCIDENTE, download_pecas=True)
    assert _documentos_pedidos() == list(PUBLICOS)


@responses.activate
def test_falha_de_documento_vira_aviso_e_o_processo_fica(tmp_path, mocker):
    """Recusa da pasta e resposta sem ``%PDF`` não derrubam o processo nem gravam PDF."""
    mocker.patch("time.sleep")
    _registrar_processo()
    _registrar_documento(PUBLICOS[0], pasta=load_sample_bytes("tjsp", "documentos/acesso_nao_validado.html"))
    _registrar_documento(PUBLICOS[1], pdf=b"<html>sessao expirada</html>")

    with pytest.warns(UserWarning, match="documento") as avisos:
        result = jus.scraper("tjsp", download_path=str(tmp_path / "d")).cpopg(
            CNJ_INCIDENTE, download_pecas=True, diretorio=str(tmp_path / "destino")
        )

    mensagens = " ".join(str(a.message) for a in avisos)
    assert f"{PUBLICOS[0]}: resposta_inesperada" in mensagens
    assert f"{PUBLICOS[1]}: nao_pdf" in mensagens
    assert len(result["movimentacoes"]) == 14
    assert result["movimentacoes"]["caminho_documento"].isna().all()
    assert len(result["basicos"]) == 1
    assert not list((tmp_path / "destino").rglob("*.pdf"))
    assert not list(tmp_path.rglob("*.tmp"))


@responses.activate
def test_erro_de_rede_em_documento_vira_aviso(tmp_path, mocker):
    mocker.patch("time.sleep")
    _registrar_processo()
    _registrar_documento(PUBLICOS[0])
    responses.add(
        responses.GET,
        f"{ESAJ}/cpopg/{ROTA_DOCUMENTO}",
        status=500,
        match=[query_param_matcher({"cdDocumento": PUBLICOS[1]}, strict_match=False)],
    )

    with pytest.warns(UserWarning, match=f"{PUBLICOS[1]}: http_500"):
        jus.scraper("tjsp", download_path=str(tmp_path)).cpopg_download(CNJ_INCIDENTE, download_pecas=True)

    assert [p.stem for p in tmp_path.rglob("*.pdf")] == [PUBLICOS[0]]
    assert list(tmp_path.rglob("*.html"))


@pytest.mark.parametrize(
    ("kwargs", "mensagem"),
    [
        ({"method": "api", "download_pecas": True, "diretorio": "x"}, "method='html'"),
        ({"baixar_movimentacoes": False, "download_pecas": True, "diretorio": "x"}, "baixar_movimentacoes=True"),
        ({"download_pecas": True}, "exige diretorio"),
        ({"diretorio": "x"}, "exige diretorio"),
    ],
)
@responses.activate
def test_cpopg_recusa_combinacao_invalida_sem_pedido(tmp_path, kwargs, mensagem):
    kwargs = {**kwargs, **({"diretorio": str(tmp_path / "destino")} if "diretorio" in kwargs else {})}
    scraper = jus.scraper("tjsp", download_path=str(tmp_path / "download"))

    with pytest.raises(ValueError, match=mensagem):
        scraper.cpopg(CNJ_INCIDENTE, **kwargs)

    assert len(responses.calls) == 0


@responses.activate
def test_cpopg_recusa_diretorio_dentro_de_download_path(tmp_path):
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))

    with pytest.raises(ValueError, match="dentro de download_path"):
        scraper.cpopg(CNJ_INCIDENTE, download_pecas=True, diretorio=str(tmp_path / "sub"))

    assert len(responses.calls) == 0


@pytest.mark.parametrize(
    ("kwargs", "mensagem"),
    [
        ({"method": "api"}, "method='html'"),
        ({"baixar_movimentacoes": False}, "baixar_movimentacoes=True"),
    ],
)
@responses.activate
def test_cpopg_download_recusa_download_pecas_sem_links(tmp_path, kwargs, mensagem):
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))

    with pytest.raises(ValueError, match=mensagem):
        scraper.cpopg_download(CNJ_INCIDENTE, download_pecas=True, **kwargs)

    assert len(responses.calls) == 0


@pytest.mark.parametrize(
    "erro",
    [requests.exceptions.ChunkedEncodingError("corpo cortado"), requests.exceptions.TooManyRedirects("laço")],
)
@responses.activate
def test_erro_de_requests_fora_do_vocabulario_vira_aviso_e_nao_refaz_o_processo(tmp_path, mocker, erro):
    """Um erro de requests num documento não pode subir ao retry, que refaria o processo e o perderia."""
    mocker.patch("time.sleep")
    _registrar_processo()
    _registrar_documento(PUBLICOS[0])
    responses.add(
        responses.GET,
        f"{ESAJ}/cpopg/{ROTA_DOCUMENTO}",
        body=erro,
        match=[query_param_matcher({"cdDocumento": PUBLICOS[1]}, strict_match=False)],
    )

    with pytest.warns(UserWarning, match=f"{PUBLICOS[1]}: resposta_inesperada"):
        jus.scraper("tjsp", download_path=str(tmp_path)).cpopg_download(CNJ_INCIDENTE, download_pecas=True)

    assert len(_chamadas("search.do")) == 1
    assert [p.stem for p in tmp_path.rglob("*.pdf")] == [PUBLICOS[0]]
    assert len(list(tmp_path.rglob("*.html"))) == 1


def _show_antigo(codigo, cd_documento):
    """Página de processo no layout com a lista inteira, com uma movimentação e um documento público."""
    return (
        '<html><body><table><tbody id="tabelaTodasMovimentacoes">'
        '<tr class="containerMovimentacao"><td>01/01/2025</td><td></td><td>'
        f'<a class="linkMovVincProc" id="linkMovVincProc-{cd_documento}" '
        f'href="/cpopg/{ROTA_DOCUMENTO}?processo.codigo={codigo}&cdDocumento={cd_documento}">Sentença</a>'
        "</td></tr></tbody></table></body></html>"
    )


@responses.activate
def test_varios_incidentes_baixam_os_pdfs_de_cada_um_antes_do_show_seguinte(tmp_path, mocker):
    """Com a busca em lista, o PDF de cada incidente sai antes de a sessão abrir o incidente seguinte."""
    mocker.patch("time.sleep")
    incidentes = {"1W001AAAA0000": PUBLICOS[0], "1W001BBBB0000": PUBLICOS[1]}
    listagem = "".join(f'<a href="/cpopg/show.do?processo.codigo={codigo}">x</a>' for codigo in incidentes)
    responses.add(
        responses.GET,
        f"{ESAJ}/cpopg/search.do",
        body=f'<div id="listagemDeProcessos">{listagem}</div>',
        content_type=_HTML,
    )
    for codigo, cd_documento in incidentes.items():
        responses.add(
            responses.GET,
            re.compile(rf"{re.escape(ESAJ)}/+cpopg/show\.do\?processo\.codigo={codigo}$"),
            body=_show_antigo(codigo, cd_documento),
            content_type=_HTML,
        )
        responses.add(
            responses.GET,
            f"{ESAJ}/cpopg/{ROTA_DOCUMENTO}",
            body=load_sample_bytes("tjsp", f"documentos/pasta_{cd_documento}.html"),
            content_type=_HTML,
            match=[query_param_matcher({"cdDocumento": cd_documento}, strict_match=False)],
        )
        parametros = parse_parametros_pasta(load_sample("tjsp", f"documentos/pasta_{cd_documento}.html"))
        responses.add(
            responses.GET,
            f"{ESAJ}/pastadigital/getPDF.do",
            body=PDF_FALSO,
            match=[query_param_matcher(dict(parse_qsl(parametros, keep_blank_values=True)))],
        )

    jus.scraper("tjsp", download_path=str(tmp_path)).cpopg_download(CNJ_INCIDENTE, download_pecas=True)

    rotas = [c.request.url.split("?")[0].rsplit("/", 1)[-1] for c in responses.calls]
    assert rotas == [
        "search.do",
        "show.do",
        ROTA_DOCUMENTO,
        "getPDF.do",
        "show.do",
        ROTA_DOCUMENTO,
        "getPDF.do",
    ]
    assert _documentos_pedidos() == list(PUBLICOS)
    assert sorted(p.stem for p in tmp_path.rglob("*.pdf")) == sorted(PUBLICOS)
    assert len(list(tmp_path.rglob("*.html"))) == 2
