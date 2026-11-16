"""Offline contract tests for TJRS cjsg."""
import json
from urllib.parse import urlencode

import pandas as pd
import pytest
import requests
import responses
from responses.matchers import urlencoded_params_matcher
from responses.registries import OrderedRegistry

import juscraper as jus
from juscraper.core.exceptions import ColetaParcialError, HTTPSemanticError, InvalidJSONResponseError
from juscraper.courts.tjrs.download import TJRSBuscaError
from tests._helpers import load_sample

BASE = "https://www.tjrs.jus.br/buscas/jurisprudencia/ajax.php"
CJSG_MIN_COLUMNS = {"processo", "ementa", "url", "relator", "orgao_julgador", "data_julgamento"}


def _inner_params(
    pesquisa: str,
    pagina: int,
    *,
    classe: str = "-1",
    assunto: str = "-1",
    orgao_julgador: str = "-1",
    relator: str = "-1",
    data_julgamento_inicio: str = "",
    data_julgamento_fim: str = "",
    data_publicacao_inicio: str = "",
    data_publicacao_fim: str = "",
    tipo_processo: str = "-1",
    secao: str | None = None,
) -> dict:
    payload = {
        "aba": "jurisprudencia",
        "realizando_pesquisa": "1",
        "pagina_atual": str(pagina),
        "start": "0",
        "q_palavra_chave": pesquisa,
        "conteudo_busca": "ementa_completa",
        "filtroComAExpressao": "",
        "filtroComQualquerPalavra": "",
        "filtroSemAsPalavras": "",
        "filtroTribunal": "-1",
        "filtroRelator": relator,
        "filtroOrgaoJulgador": orgao_julgador,
        "filtroTipoProcesso": tipo_processo,
        "filtroClasseCnj": classe,
        "assuntoCnj": assunto,
        "data_julgamento_de": data_julgamento_inicio,
        "data_julgamento_ate": data_julgamento_fim,
        "filtroNumeroProcesso": "",
        "data_publicacao_de": data_publicacao_inicio,
        "data_publicacao_ate": data_publicacao_fim,
        "facet": "on",
        "facet.sort": "index",
        "facet.limit": "index",
        "wt": "json",
        "ordem": "desc",
        "facet_orgao_julgador": "",
        "facet_origem": "",
        "facet_relator_redator": "",
        "facet_ano_julgamento": "",
        "facet_nome_classe_cnj": "",
        "facet_nome_assunto_cnj": "",
        "facet_nome_tribunal": "",
        "facet_tipo_processo": "",
        "facet_mes_ano_publicacao": "",
    }
    if secao:
        # Nomes das caixas de seção do formulário de busca do TJRS.
        campo = {"civel": "filtroSecaoCivel", "crime": "filtroSecaoCrime"}[secao]
        payload[campo] = secao
    return payload


def _form_payload(pesquisa: str, pagina: int, **kwargs) -> dict:
    return {
        "action": "consultas_solr_ajax",
        "metodo": "buscar_resultados",
        "parametros": urlencode(_inner_params(pesquisa, pagina, **kwargs), doseq=True),
    }


def _add_page(pesquisa: str, pagina: int, sample_path: str, **kwargs) -> None:
    responses.add(
        responses.POST,
        BASE,
        body=load_sample("tjrs", sample_path),
        status=200,
        content_type="application/json",
        match=[urlencoded_params_matcher(_form_payload(pesquisa, pagina, **kwargs), allow_blank=True)],
    )


@responses.activate
def test_cjsg_typical_com_paginacao(mocker):
    """Typical multi-page query returns a DataFrame with the minimum schema."""
    mocker.patch("time.sleep")
    _add_page("dano moral", 1, "cjsg/results_normal_page_01.json")
    _add_page("dano moral", 2, "cjsg/results_normal_page_02.json")

    df = jus.scraper("tjrs").cjsg("dano moral", paginas=range(1, 3))

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_MIN_COLUMNS
    assert len(df) > 0


@responses.activate
def test_cjsg_single_page(mocker):
    """Single requested page returns parsed records."""
    mocker.patch("time.sleep")
    _add_page("mandado de seguranca", 1, "cjsg/single_page.json")

    df = jus.scraper("tjrs").cjsg("mandado de seguranca", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_MIN_COLUMNS
    assert len(df) > 0


@responses.activate
def test_cjsg_no_results(mocker):
    """Zero-result query returns an empty DataFrame instead of raising."""
    mocker.patch("time.sleep")
    _add_page("juscraper_probe_zero_hits_xyzqwe", 1, "cjsg/no_results.json")

    df = jus.scraper("tjrs").cjsg("juscraper_probe_zero_hits_xyzqwe", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert df.empty


@pytest.mark.parametrize(
    "falha",
    [requests.ReadTimeout("lento"), requests.ConnectionError("fora do ar")],
    ids=["timeout", "conexao"],
)
@responses.activate(registry=OrderedRegistry)
def test_cjsg_retenta_timeout_e_erro_de_conexao(mocker, falha):
    """Timeout e erro de conexão transitórios ganham nova tentativa, como no TRF3."""
    mocker.patch("time.sleep")
    responses.add(responses.POST, BASE, body=falha)
    _add_page("mandado de seguranca", 1, "cjsg/single_page.json")

    df = jus.scraper("tjrs").cjsg("mandado de seguranca", paginas=1)

    assert len(df) > 0
    assert len(responses.calls) == 2


@pytest.mark.parametrize(
    "corpo",
    ["", "<html><body>Manutenção</body></html>"],
    ids=["vazio", "html"],
)
@responses.activate(registry=OrderedRegistry)
def test_cjsg_retenta_corpo_nao_json(mocker, corpo):
    """Um 200 com corpo vazio ou HTML é transitório e ganha nova tentativa, como no TJES."""
    mocker.patch("time.sleep")
    responses.add(responses.POST, BASE, body=corpo, status=200, content_type="text/html")
    _add_page("mandado de seguranca", 1, "cjsg/single_page.json")

    df = jus.scraper("tjrs").cjsg("mandado de seguranca", paginas=1)

    assert len(df) > 0
    assert len(responses.calls) == 2


@responses.activate
def test_cjsg_corpo_nao_json_persistente_levanta_invalid_json(mocker):
    """Persistindo, sai ``InvalidJSONResponseError`` com o status, não ``JSONDecodeError`` opaco."""
    mocker.patch("time.sleep")
    responses.add(responses.POST, BASE, body="", status=200)

    with pytest.raises(InvalidJSONResponseError):
        jus.scraper("tjrs").cjsg("mandado de seguranca", paginas=1)

    assert len(responses.calls) == 3


@pytest.mark.parametrize(
    ("politica", "timeout_esperado"),
    [(None, (10, 30)), ({"cjsg": {"timeout": 7}}, 7)],
    ids=["default", "politica"],
)
@responses.activate
def test_cjsg_timeout_vem_do_perfil_http(mocker, politica, timeout_esperado):
    """O timeout sai do perfil ``cjsg``, ajustável com ``politica=`` no construtor."""
    mocker.patch("time.sleep")
    _add_page("mandado de seguranca", 1, "cjsg/single_page.json")

    jus.scraper("tjrs", politica=politica).cjsg("mandado de seguranca", paginas=1)

    assert responses.calls[0].request.req_kwargs["timeout"] == timeout_esperado


@pytest.mark.parametrize("paginas", [1, None], ids=["pagina_pedida", "todas_as_paginas"])
@responses.activate
def test_cjsg_erro_do_solr_levanta_em_vez_de_busca_vazia(mocker, paginas):
    """Aspas sem fechar: HTTP 200 com ``{"error": ...}`` no lugar de ``response``."""
    mocker.patch("time.sleep")
    _add_page('"dano moral', 1, "cjsg/erro_solr.json")

    with pytest.raises(TJRSBuscaError, match="Cannot parse") as excinfo:
        jus.scraper("tjrs").cjsg('"dano moral', paginas=paginas)  # tjrs: guarda-paginas: 1 resposta registrada

    assert excinfo.value.codigo == 400
    assert isinstance(excinfo.value, HTTPSemanticError)
    assert len(responses.calls) == 1


@pytest.mark.parametrize("metodo", ["cjsg", "cjsg_download"])
@pytest.mark.parametrize("paginas", [range(1, 4), [1, 2, 3]], ids=["range", "lista"])
@responses.activate
def test_cjsg_erro_do_solr_no_meio_da_paginacao_guarda_as_paginas_anteriores(mocker, metodo, paginas):
    """Erro do Solr na página 2: a página 1 vem lida em ``.resultado``, e a busca para."""
    mocker.patch("time.sleep")
    _add_page("dano moral", 1, "cjsg/results_normal_page_01.json")
    _add_page("dano moral", 2, "cjsg/erro_solr.json")

    with pytest.raises(ColetaParcialError, match=r"página 2 falhou.*faltam as páginas \[2, 3\],") as excinfo:
        getattr(jus.scraper("tjrs"), metodo)("dano moral", paginas=paginas)

    tjrs = jus.scraper("tjrs")
    esperado = tjrs.cjsg_parse([json.loads(load_sample("tjrs", "cjsg/results_normal_page_01.json"))])
    pd.testing.assert_frame_equal(excinfo.value.resultado, esperado)
    assert isinstance(excinfo.value.__cause__, TJRSBuscaError)
    assert [type(falha[2]) for falha in excinfo.value.falhas] == [TJRSBuscaError]
    # A página 3 não é pedida.
    assert len(responses.calls) == 2


@responses.activate
def test_cjsg_erro_do_solr_no_meio_de_todas_as_paginas_resume_as_que_faltam(mocker):
    """``paginas=None``: o total vem da página 1, e as páginas que faltam saem como ``range``."""
    mocker.patch("time.sleep")
    primeira = json.loads(load_sample("tjrs", "cjsg/results_normal_page_01.json"))
    primeira["response"]["numFound"] = 45
    responses.add(responses.POST, BASE, json=primeira)
    _add_page("dano moral", 2, "cjsg/erro_solr.json")
    todas = None  # a página 2 responde erro, e nenhuma outra é pedida

    with pytest.raises(ColetaParcialError, match=r"faltam as páginas range\(2, 6\),") as excinfo:
        jus.scraper("tjrs").cjsg("dano moral", paginas=todas)

    assert len(excinfo.value.resultado) == 10
    assert len(responses.calls) == 2


@pytest.mark.parametrize("brutos", [["erro"], ["pagina", "erro"]], ids=["so_o_erro", "depois_de_uma_pagina"])
def test_cjsg_parse_de_envelope_de_erro_levanta_em_vez_de_vazio(brutos):
    """Arquivo salvo de uma busca recusada pelo Solr: o parse direto não o lê como busca vazia."""
    amostras = {"erro": "cjsg/erro_solr.json", "pagina": "cjsg/results_normal_page_01.json"}

    with pytest.raises(TJRSBuscaError, match="Cannot parse") as excinfo:
        jus.scraper("tjrs").cjsg_parse([json.loads(load_sample("tjrs", amostras[nome])) for nome in brutos])

    assert excinfo.value.codigo == 400


def test_cjsg_parse_de_busca_sem_resultado_segue_vazio():
    df = jus.scraper("tjrs").cjsg_parse([json.loads(load_sample("tjrs", "cjsg/no_results.json"))])

    assert df.empty


def test_cjsg_parse_relator_quando_o_redator_e_outro():
    """``relator_redator`` com dois nomes traz o redator primeiro; ``relator`` é o relator."""
    brutos = [json.loads(load_sample("tjrs", "cjsg/relator_redator_multi.json"))]
    assert brutos[0]["response"]["docs"][0]["relator_redator"] == [
        "Regis de Oliveira Montenegro Barbosa",
        "José Conrado Kurtz de Souza",
    ]

    df = jus.scraper("tjrs").cjsg_parse(brutos)

    linha = df[df["processo"] == "80009491520268210001"].iloc[0]
    assert linha["relator"] == "José Conrado Kurtz de Souza"
    assert linha["nome_redator"] == "Regis de Oliveira Montenegro Barbosa"
    assert (df["relator"] == df["nome_relator"]).all()
    # Sem redator distinto, o portal não manda ``nome_redator``.
    sem_redator = df[df["processo"] == "50043305220258210087"].iloc[0]
    assert sem_redator["relator"] == "Altair de Lemos Junior"
    assert sem_redator["nome_redator"] is None
