"""Offline contract tests for TJES cjsg."""
import datetime

import pandas as pd
import pytest
import responses
from responses.matchers import query_param_matcher

import juscraper as jus
from tests._helpers import load_sample

BASE = "https://sistemas.tjes.jus.br/consulta-jurisprudencia/api/search"
CJSG_MIN_COLUMNS = {"processo", "ementa", "relator", "orgao_julgador", "classe", "assunto", "dt_juntada"}


def _params(
    pesquisa: str,
    pagina: int,
    *,
    core: str = "pje2g",
    tamanho_pagina: int = 20,
    busca_exata: bool = False,
    data_inicio: str | None = None,
    data_fim: str | None = None,
    relator: str | None = None,
    orgao_julgador: str | None = None,
    classe: str | None = None,
    jurisdicao: str | None = None,
    assunto: str | None = None,
    ordenacao: str | None = None,
) -> dict:
    params = {
        "core": core,
        "q": pesquisa,
        "page": str(pagina),
        "per_page": str(tamanho_pagina),
    }
    if busca_exata:
        params["exact_match"] = "true"
    if data_inicio:
        params["dataIni"] = data_inicio
    if data_fim:
        params["dataFim"] = data_fim
    if relator:
        params["magistrado"] = relator
    if orgao_julgador:
        params["orgao_julgador"] = orgao_julgador
    if classe:
        params["classe_judicial"] = classe
    if jurisdicao:
        params["jurisdicao"] = jurisdicao
    if assunto:
        params["lista_assunto"] = assunto
    if ordenacao:
        params["sort"] = ordenacao
    return params


def _add_page(pesquisa: str, pagina: int, sample_path: str, **kwargs) -> None:
    responses.add(
        responses.GET,
        BASE,
        body=load_sample("tjes", sample_path),
        status=200,
        content_type="application/json",
        match=[query_param_matcher(_params(pesquisa, pagina, **kwargs))],
    )


@responses.activate
def test_cjsg_typical_com_paginacao(mocker):
    """Typical multi-page query returns a DataFrame with the minimum schema."""
    mocker.patch("time.sleep")
    _add_page("dano moral", 1, "cjsg/results_normal_page_01.json")
    _add_page("dano moral", 2, "cjsg/results_normal_page_02.json")

    df = jus.scraper("tjes").cjsg("dano moral", paginas=range(1, 3))

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_MIN_COLUMNS
    assert len(df) > 0


@responses.activate
def test_cjsg_single_page(mocker):
    """Single requested page returns parsed records."""
    mocker.patch("time.sleep")
    _add_page("mandado de seguranca", 1, "cjsg/single_page.json")

    df = jus.scraper("tjes").cjsg("mandado de seguranca", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_MIN_COLUMNS
    assert len(df) > 0


@responses.activate
def test_cjsg_no_results(mocker):
    """Zero-result query returns an empty DataFrame instead of raising."""
    mocker.patch("time.sleep")
    _add_page("juscraper_probe_zero_hits_xyzqwe", 1, "cjsg/no_results.json")

    df = jus.scraper("tjes").cjsg("juscraper_probe_zero_hits_xyzqwe", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_cjsg_rejects_pje1g_core():
    """Public cjsg rejects first-instance core; use cjpg instead."""
    with pytest.raises(ValueError, match="cjpg"):
        jus.scraper("tjes").cjsg("direito", core="pje1g", paginas=1)


@responses.activate
def test_cjsg_core_legado_preenche_colunas_canonicas(mocker):
    """No core ``legado``, processo, relator, ementa e datas vêm dos campos próprios do core."""
    mocker.patch("time.sleep")
    _add_page("dano moral", 1, "cjsg/results_legado_page_01.json", core="legado")

    df = jus.scraper("tjes").cjsg("dano moral", paginas=1, core="legado")

    assert len(df) == 20
    for coluna in ("processo", "ementa", "relator", "orgao_julgador", "data_julgamento", "data_publicacao", "acordao"):
        assert df[coluna].notna().all(), coluna
    primeira = df.iloc[0]
    assert primeira["processo"] == "0014394-89.2014.8.08.0012"
    assert primeira["relator"] == "SAMUEL MEIRA BRASIL JUNIOR"
    assert primeira["ementa"].strip().startswith("ACÓRDÃO")
    assert "EMENTA: APELAÇÃO CÍVEL" in primeira["ementa"]
    assert primeira["data_julgamento"] == datetime.date(2017, 4, 18)
    assert primeira["data_publicacao"] == datetime.date(2017, 4, 28)


@responses.activate
def test_cjsg_core_turma_recursal_legado_preenche_colunas_canonicas(mocker):
    """No core ``turma_recursal_legado``, processo, relator, classe, ementa e data vêm dos campos do core."""
    mocker.patch("time.sleep")
    _add_page("dano moral", 1, "cjsg/results_turma_recursal_legado_page_01.json", core="turma_recursal_legado")

    df = jus.scraper("tjes").cjsg("dano moral", paginas=1, core="turma_recursal_legado")

    assert len(df) == 20
    for coluna in ("processo", "ementa", "relator", "orgao_julgador", "classe", "data_julgamento"):
        assert df[coluna].notna().all(), coluna
    primeira = df.iloc[0]
    # O número vem como a fonte o entrega: só dígitos, sem os zeros à esquerda.
    assert primeira["processo"] == "145275020158080545"
    assert primeira["relator"] == "PAULA CHEIM JORGE"
    assert primeira["classe"] == "Recurso Inominado"
    assert "ACÓRDÃO" in primeira["ementa"]
    assert primeira["data_julgamento"] == datetime.date(2017, 2, 16)
