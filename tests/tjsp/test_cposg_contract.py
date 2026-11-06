"""Offline contract tests for TJSP cposg (``method='html'`` and ``'api'``).

HTML flow: GET ``cposg/open.do`` → GET ``cposg/search.do`` → Caso 3
(resposta simples) or Caso 1/2 (listagem/modal). The CNJ used here lands
in Caso 3 — the search response itself contains the process details and
the scraper saves it under the ``cdProcesso`` value.

API flow: a single GET ``processo/cposg/search/numproc/{id}``; parsed values
are asserted against the real response sample.
"""
import pandas as pd
import responses
from responses.matchers import query_param_matcher

import juscraper as jus
from tests._helpers import load_sample, load_sample_bytes

ESAJ = "https://esaj.tjsp.jus.br"
API = "https://api.tjsp.jus.br"

CNJ = "1000149-71.2024.8.26.0346"
CNJ_DIGITS = "10001497120248260346"

CPOSG_BASICOS_MIN = {"id_original", "classe", "status"}

# Ordem pública das colunas do cposg HTML. A lista é literal de propósito: se o
# teste importasse a constante do módulo testado, uma reordenação dela passaria.
CPOSG_COLUNAS_ORDENADAS = [
    "id_original", "processo", "status", "classe", "assunto", "secao",
    "orgao_julgador", "area", "relator", "valor_da_acao", "origem",
    "volume_apenso", "movimentacoes", "partes", "historico", "decisoes",
    "composicao", "primeira_inst",
]


# ---------- method='html' -----------------------------------------------

@responses.activate
def test_cposg_html_simple_response(tmp_path, mocker):
    """HTML flow — Caso 3 (resposta simples): search.do has the process details."""
    mocker.patch("time.sleep")

    responses.add(
        responses.GET,
        f"{ESAJ}/cposg/open.do",
        body=load_sample_bytes("tjsp", "cposg/open.html"),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher({"gateway": "true"})],
    )
    search_params = {
        "conversationId": "",
        "paginaConsulta": "1",
        "localPesquisa.cdLocal": "-1",
        "cbPesquisa": "NUMPROC",
        "tipoNuProcesso": "UNIFICADO",
        "numeroDigitoAnoUnificado": "1000149-71.2024",
        "foroNumeroUnificado": "0346",
        "dePesquisaNuUnificado": CNJ,
        "dePesquisa": "",
        "uuidCaptcha": "",
        "pbEnviar": "Pesquisar",
    }
    responses.add(
        responses.GET,
        f"{ESAJ}/cposg/search.do",
        body=load_sample_bytes("tjsp", "cposg/search_listagem.html"),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher(search_params)],
    )

    df = jus.scraper("tjsp", download_path=str(tmp_path)).cposg(CNJ, method="html")

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    assert set(df.columns) >= CPOSG_BASICOS_MIN
    assert list(df.columns) == CPOSG_COLUNAS_ORDENADAS


# ---------- method='api' ------------------------------------------------

@responses.activate
def test_cposg_api_parses_real_sample(tmp_path, mocker):
    """A API retorna os dados observados no sample real da resposta."""
    mocker.patch("time.sleep")
    responses.add(
        responses.GET,
        f"{API}/processo/cposg/search/numproc/{CNJ_DIGITS}",
        body=load_sample("tjsp", "cposg/api_search.json"),
        status=200,
        content_type="application/json",
    )

    df = jus.scraper("tjsp", download_path=str(tmp_path)).cposg(CNJ, method="api")

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["id_original"] == "1000149-71.2024.8.26.0346"
    assert row["processo"] == "1000149-71.2024.8.26.0346"
    assert row["classe"] == "Apelação Cível"
    assert row["assunto"] == "DIREITO DO CONSUMIDOR - Contratos de Consumo - Bancários"


@responses.activate
def test_cposg_download_html_usa_diretorio_sem_alterar_download_path(tmp_path, mocker):
    """O destino alternativo do HTML não deve alterar o destino configurado."""
    mocker.patch("time.sleep")
    responses.add(
        responses.GET,
        f"{ESAJ}/cposg/open.do",
        body=load_sample_bytes("tjsp", "cposg/open.html"),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher({"gateway": "true"})],
    )
    search_params = {
        "conversationId": "",
        "paginaConsulta": "1",
        "localPesquisa.cdLocal": "-1",
        "cbPesquisa": "NUMPROC",
        "tipoNuProcesso": "UNIFICADO",
        "numeroDigitoAnoUnificado": "1000149-71.2024",
        "foroNumeroUnificado": "0346",
        "dePesquisaNuUnificado": CNJ,
        "dePesquisa": "",
        "uuidCaptcha": "",
        "pbEnviar": "Pesquisar",
    }
    responses.add(
        responses.GET,
        f"{ESAJ}/cposg/search.do",
        body=load_sample_bytes("tjsp", "cposg/search_listagem.html"),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher(search_params)],
    )
    caminho = tmp_path / "padrao"
    alternativo = tmp_path / "alternativo"
    scraper = jus.scraper("tjsp", download_path=str(caminho))

    scraper.cposg_download(CNJ, method="html", diretorio=str(alternativo))

    assert (alternativo / "cposg").is_dir()
    assert not (caminho / "cposg").exists()
    assert scraper.download_path == str(caminho)


@responses.activate
def test_cposg_download_api_usa_download_path_sem_diretorio(tmp_path, mocker):
    """Sem destino alternativo, o CPOSG API usa ``self.download_path``."""
    mocker.patch("time.sleep")
    responses.add(
        responses.GET,
        f"{API}/processo/cposg/search/numproc/{CNJ_DIGITS}",
        body=load_sample("tjsp", "cposg/api_search.json"),
        status=200,
        content_type="application/json",
    )
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))

    scraper.cposg_download(CNJ, method="api")

    assert (tmp_path / "cposg").is_dir()
    assert scraper.download_path == str(tmp_path)


def test_cposg_download_api_usa_diretorio_sem_alterar_download_path(tmp_path, mocker):
    """O destino alternativo do API deve ser encaminhado ao downloader."""
    caminho = tmp_path / "padrao"
    alternativo = tmp_path / "alternativo"
    scraper = jus.scraper("tjsp", download_path=str(caminho))
    download = mocker.patch("juscraper.courts.tjsp.client.cposg_download_api")

    scraper.cposg_download(CNJ, method="api", diretorio=str(alternativo))

    assert download.call_args.kwargs["download_path"] == str(alternativo)
    assert scraper.download_path == str(caminho)
