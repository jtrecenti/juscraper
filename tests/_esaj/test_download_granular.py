"""Testes granulares do download de cjsg da família eSAJ (``_esaj/download.py``).

Cobrem o que os contratos por tribunal não alcançam: os GETs das páginas
seguintes na aba de decisões monocráticas, cujos samples reais cabem todos em
uma página, e a primeira página gravada em busca sem resultado.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import responses
from responses.matchers import query_param_matcher

import juscraper as jus
from juscraper.courts._esaj.download import download_cjsg_pages

BASE = "https://esaj.tjac.jus.br/"


def _baixar(tmp_path: Path, *, tipo_decisao: str, n_pags: int) -> Path:
    return Path(
        download_cjsg_pages(
            scraper=jus.scraper("tjac"),
            base_url=BASE,
            download_path=str(tmp_path),
            body={},
            tipo_decisao=tipo_decisao,
            paginas=None,
            get_n_pags_callback=lambda _html: n_pags,
            sleep_time=0,
        )
    )


def _add(metodo: str, caminho: str, **kwargs) -> None:
    responses.add(metodo, f"{BASE}cjsg/{caminho}", body=b"<html></html>", status=200, **kwargs)


@responses.activate
@pytest.mark.parametrize(("tipo_decisao", "aba"), [("acordao", "A"), ("monocratica", "D")])
def test_paginas_seguintes_pedem_a_aba_do_tipo_de_decisao(tmp_path, tipo_decisao, aba):
    _add(responses.POST, "resultadoCompleta.do")
    for pagina in ("1", "2"):
        _add(
            responses.GET,
            "trocaDePagina.do",
            match=[query_param_matcher({"tipoDeDecisao": aba, "pagina": pagina})],
        )

    pasta = _baixar(tmp_path, tipo_decisao=tipo_decisao, n_pags=2)

    gets = [chamada.request.params for chamada in responses.calls if chamada.request.method == "GET"]
    assert [(params["tipoDeDecisao"], params["pagina"]) for params in gets] == [(aba, "1"), (aba, "2")]
    assert len(list(pasta.iterdir())) == 2


@responses.activate
def test_busca_sem_resultado_guarda_a_primeira_pagina(tmp_path):
    _add(responses.POST, "resultadoCompleta.do")
    _add(responses.GET, "trocaDePagina.do")

    pasta = _baixar(tmp_path, tipo_decisao="acordao", n_pags=0)

    assert [arquivo.read_bytes() for arquivo in pasta.iterdir()] == [b"<html></html>"]
