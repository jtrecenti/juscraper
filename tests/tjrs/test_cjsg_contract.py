"""Offline contract tests for TJRS cjsg."""
from urllib.parse import urlencode

import pandas as pd
import responses
from responses.matchers import urlencoded_params_matcher

import juscraper as jus
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
        payload["filtroSecao"] = {"civel": "C", "crime": "P"}[secao]
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
    assert CJSG_MIN_COLUMNS <= set(df.columns)
    assert len(df) > 0


@responses.activate
def test_cjsg_single_page(mocker):
    """Single requested page returns parsed records."""
    mocker.patch("time.sleep")
    _add_page("mandado de seguranca", 1, "cjsg/single_page.json")

    df = jus.scraper("tjrs").cjsg("mandado de seguranca", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert CJSG_MIN_COLUMNS <= set(df.columns)
    assert len(df) > 0


@responses.activate
def test_cjsg_no_results(mocker):
    """Zero-result query returns an empty DataFrame instead of raising."""
    mocker.patch("time.sleep")
    _add_page("juscraper_probe_zero_hits_xyzqwe", 1, "cjsg/no_results.json")

    df = jus.scraper("tjrs").cjsg("juscraper_probe_zero_hits_xyzqwe", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert df.empty
