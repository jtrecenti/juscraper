"""Contratos offline do ``cjpg`` e de ``baixar_sentencas`` do TJMS (#487).

O TJMS herda o cjpg do TJSP (:class:`~juscraper.courts._esaj.cjpg.EsajCjpgScraper`).
O ``esaj.tjms.jus.br`` não responde a IP de datacenter, então as respostas
são as capturas reais do cjpg e da pasta digital do TJSP, servidas no host
do TJMS. A prova contra o portal está em ``tests/tjms/test_cjpg_integration.py``.
"""

import json
from urllib.parse import parse_qsl, urlsplit

import pandas as pd
import responses
from responses.matchers import query_param_matcher
from responses.registries import OrderedRegistry

import juscraper as jus
from juscraper.courts._esaj.pasta import parse_parametros_pasta
from tests._helpers import PDF_FALSO, load_sample, load_sample_bytes
from tests.fixtures.capture._util import make_tjsp_cjpg_params

ESAJ = "https://esaj.tjms.jus.br"
CD_PROCESSO, CD_FORO, CD_DOCUMENTO = "3I0006RUY0000", "126", "167379827"
_PASTA = json.loads(load_sample("tjsp", "documentos/redirecionamentos.json"))[f"sentenca_{CD_DOCUMENTO}"].replace(
    "https://esaj.tjsp.jus.br", ESAJ
)


def _add_pesquisar(pesquisa: str, sample: str) -> None:
    esperado = {k: v for k, v in make_tjsp_cjpg_params(pesquisa).items() if v is not None}
    responses.add(
        responses.GET,
        f"{ESAJ}/cjpg/pesquisar.do",
        body=load_sample_bytes("tjsp", sample),
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher(esperado)],
    )


def _add_trocar_de_pagina(pagina: int, sample: str) -> None:
    responses.add(
        responses.GET,
        f"{ESAJ}/cjpg/trocarDePagina.do",
        body=load_sample_bytes("tjsp", sample),
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher({"pagina": str(pagina), "conversationId": ""})],
    )


def _registrar_sentenca() -> None:
    responses.add(
        responses.GET,
        f"{ESAJ}/cjpg/obterArquivo.do",
        status=302,
        headers={"Location": _PASTA},
        match=[query_param_matcher({"cdDocumento": CD_DOCUMENTO}, strict_match=False)],
    )
    responses.add(
        responses.GET,
        _PASTA.split("?")[0],
        body=load_sample_bytes("tjsp", f"documentos/pasta_{CD_DOCUMENTO}.html"),
        content_type="text/html;charset=UTF-8",
    )
    parametros = parse_parametros_pasta(load_sample("tjsp", f"documentos/pasta_{CD_DOCUMENTO}.html"))
    responses.add(
        responses.GET,
        f"{ESAJ}/pastadigital/getPDF.do",
        body=PDF_FALSO,
        match=[query_param_matcher(dict(parse_qsl(parametros, keep_blank_values=True)))],
    )


@responses.activate(registry=OrderedRegistry)
def test_cjpg_pagina_no_host_do_tjms_e_traz_os_codigos_da_sentenca(tmp_path, mocker):
    mocker.patch("time.sleep")
    _add_pesquisar("dano moral", "cjpg/results_normal_page_01.html")
    _add_trocar_de_pagina(2, "cjpg/results_normal_page_02.html")

    df = jus.scraper("tjms", download_path=str(tmp_path)).cjpg("dano moral", paginas=range(1, 3))

    assert len(df) == 20
    assert set(df.columns) >= {"id_processo", "cd_processo", "cd_foro", "nm_alias", "cd_documento", "decisao"}
    linha = df.iloc[0]
    assert (linha.cd_processo, linha.cd_foro, linha.nm_alias, linha.cd_documento) == (
        CD_PROCESSO,
        CD_FORO,
        None,
        CD_DOCUMENTO,
    )
    assert all(c.request.url.startswith(f"{ESAJ}/cjpg/") for c in responses.calls)


@responses.activate
def test_cjpg_count_only_no_host_do_tjms(tmp_path, mocker):
    mocker.patch("time.sleep")
    _add_pesquisar("dano moral", "cjpg/results_normal_page_01.html")

    n = jus.scraper("tjms", download_path=str(tmp_path)).cjpg("dano moral", count_only=True)

    assert isinstance(n, int)
    assert n > 20
    assert len(responses.calls) == 1


@responses.activate
def test_cjpg_filtros_chegam_a_consulta_do_tjms(tmp_path, mocker):
    mocker.patch("time.sleep")
    esperado = make_tjsp_cjpg_params(
        "dano moral",
        id_processo="08001234520238120001",
        classes=["7"],
        assuntos=["10433", "7779"],
        varas=["1-2-3"],
        data_inicio="01/01/2024",
        data_fim="31/03/2024",
    )
    responses.add(
        responses.GET,
        f"{ESAJ}/cjpg/pesquisar.do",
        body=load_sample_bytes("tjsp", "cjpg/no_results.html"),
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher(esperado)],
    )

    df = jus.scraper("tjms", download_path=str(tmp_path)).cjpg(
        "dano moral",
        paginas=1,
        classe=7,
        assunto=[10433, 7779],
        vara="1-2-3",
        id_processo="0800123-45.2023.8.12.0001",
        data_julgamento_inicio="01/01/2024",
        data_julgamento_fim="31/03/2024",
    )

    assert df.empty
    assert len(responses.calls) == 1


@responses.activate
def test_cjpg_nao_aplica_ao_tjms_o_limite_de_120_caracteres_do_tjsp(tmp_path, mocker):
    """O limite foi medido no TJSP; no TJMS a busca longa segue para o portal."""
    mocker.patch("time.sleep")
    pesquisa = "a" * 121
    _add_pesquisar(pesquisa, "cjpg/no_results.html")

    df = jus.scraper("tjms", download_path=str(tmp_path)).cjpg(pesquisa, paginas=1)

    assert df.empty
    assert len(responses.calls) == 1


@responses.activate
def test_baixar_sentencas_do_cjpg_pede_ao_tjms(tmp_path, mocker):
    mocker.patch("time.sleep")
    _add_pesquisar("dano moral", "cjpg/results_normal_page_01.html")
    _registrar_sentenca()
    scraper = jus.scraper("tjms", download_path=str(tmp_path))
    cjpg = scraper.cjpg("dano moral", paginas=1).head(1)

    resultado = scraper.baixar_sentencas(cjpg)

    assert resultado["motivo_falha"].tolist() == [None]
    caminho = tmp_path / "sentencas" / f"{CD_PROCESSO}_{CD_DOCUMENTO}.pdf"
    assert resultado["caminho_sentenca"].tolist() == [str(caminho)]
    assert caminho.read_bytes() == PDF_FALSO
    (pedido,) = [c.request for c in responses.calls if "obterArquivo.do" in c.request.url]
    assert pedido.url.startswith(f"{ESAJ}/cjpg/obterArquivo.do?")
    assert dict(parse_qsl(urlsplit(pedido.url).query, keep_blank_values=True)) == {
        "cdProcesso": CD_PROCESSO,
        "cdForo": CD_FORO,
        "nmAlias": "",
        "cdDocumento": CD_DOCUMENTO,
    }
    pd.testing.assert_frame_equal(resultado[cjpg.columns], cjpg)
