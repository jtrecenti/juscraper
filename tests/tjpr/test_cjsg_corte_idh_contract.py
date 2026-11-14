"""Contratos de ``incluir_corte_idh`` no cjsg do TJPR.

O portal mistura à tabela de jurisprudência até 10 precedentes da Corte IDH
por página (linhas com ``input[name=idsSelecionadosCidh]``). Por padrão o
parser os descarta; com ``incluir_corte_idh=True`` eles voltam com
``fonte="Corte IDH"`` e o nome do caso em ``caso``. O parâmetro não altera a
requisição de busca: os POSTs abaixo usam o mesmo matcher de corpo do modo
padrão.
"""
from datetime import date
from urllib.parse import parse_qs, urlsplit

import pandas as pd
import pytest
import responses
from pydantic import ValidationError
from responses.matchers import urlencoded_params_matcher

import juscraper as jus
from juscraper.courts.tjpr.download import VISUALIZAR_URL, build_cjsg_form_body
from tests._helpers import load_sample, query_param_subset_matcher
from tests.tjpr._helpers import SEARCH_URL, add_home

COLUNAS_TJ = ["processo", "orgao_julgador", "relator", "data_julgamento", "ementa"]
COLUNAS_COM_CORTE_IDH = [*COLUNAS_TJ, "fonte", "caso"]
# Linhas da Corte IDH truncadas em "Leia mais.." nas páginas 1 e 2 de
# "dano moral"; as de id 114, 25, 18, 103 e 9 já trazem a ementa inteira.
IDS_CORTE_IDH_TRUNCADOS = {
    "106", "117", "120", "119", "118", "116", "115", "104", "107",
    "105", "23", "15", "17", "19", "16",
}


def _add_search_page(pesquisa: str, pagina: int, sample_path: str) -> None:
    responses.add(
        responses.POST,
        SEARCH_URL,
        body=load_sample("tjpr", sample_path),
        status=200,
        content_type="text/html; charset=UTF-8",
        match=[
            query_param_subset_matcher({"actionType": "pesquisar"}),
            urlencoded_params_matcher(build_cjsg_form_body(pesquisa, page=pagina), allow_blank=True),
        ],
    )


def _add_ementas_completas() -> None:
    responses.add(
        responses.GET,
        SEARCH_URL,
        body=load_sample("tjpr", "cjsg/ementa_completa.html"),
        status=200,
        content_type="text/html; charset=UTF-8",
        match=[query_param_subset_matcher({"actionType": "exibirTextoCompleto"})],
    )
    # Resposta real do caso 120 (Comunidades Quilombolas de Alcântara),
    # reaproveitada para todos os ids.
    responses.add(
        responses.GET,
        VISUALIZAR_URL,
        body=load_sample("tjpr", "cjsg/ementa_completa_cidh.html"),
        status=200,
        content_type="text/html; charset=UTF-8",
        match=[query_param_subset_matcher({"actionType": "exibirTextoCompletoCidh"})],
    )


def _ids_corte_idh_buscados() -> list[str]:
    return [
        parse_qs(urlsplit(call.request.url).query)["idProcesso"][0]
        for call in responses.calls
        if "exibirTextoCompletoCidh" in call.request.url
    ]


@responses.activate
def test_cjsg_incluir_corte_idh_mantem_as_linhas_marcadas(mocker):
    mocker.patch("time.sleep")
    add_home()
    _add_search_page("dano moral", 1, "cjsg/results_normal_page_01.html")
    _add_search_page("dano moral", 2, "cjsg/results_normal_page_02.html")
    _add_ementas_completas()

    df = jus.scraper("tjpr").cjsg("dano moral", paginas=range(1, 3), incluir_corte_idh=True)

    assert df.columns.tolist() == COLUNAS_COM_CORTE_IDH
    # 50 linhas por página: 40 do TJ e 10 da Corte IDH.
    assert len(df) == 100
    assert df["fonte"].value_counts().to_dict() == {"TJPR": 80, "Corte IDH": 20}

    tj = df[df["fonte"] == "TJPR"]
    assert (tj["processo"].str.len() > 0).all()
    assert tj["caso"].isna().all()

    corte_idh = df[df["fonte"] == "Corte IDH"]
    assert corte_idh[["processo", "orgao_julgador", "relator"]].isna().all().all()
    assert (corte_idh["caso"].str.len() > 0).all()
    assert corte_idh["data_julgamento"].notna().all()
    assert not corte_idh["ementa"].str.contains("Leia mais").any()
    assert not corte_idh["ementa"].str.contains("A expressão foi encontrada").any()

    assert sorted(_ids_corte_idh_buscados()) == sorted(IDS_CORTE_IDH_TRUNCADOS)
    alcantara = corte_idh[corte_idh["caso"] == "Comunidades Quilombolas de Alcântara vs. Brasil"]
    ementa = alcantara["ementa"].iloc[0]
    # O destaque "<span class='high'>quilombola</span>s" não parte a palavra.
    assert "171 comunidades quilombolas de Alcântara" in ementa
    assert ementa.endswith("num contexto de discriminação estrutural.")


@responses.activate
def test_cjsg_sem_incluir_corte_idh_mantem_o_contrato_anterior(mocker):
    mocker.patch("time.sleep")
    add_home()
    _add_search_page("quilombola", 1, "cjsg/single_page.html")
    _add_ementas_completas()

    df = jus.scraper("tjpr").cjsg("quilombola", paginas=1)

    assert df.columns.tolist() == COLUNAS_TJ
    assert len(df) == 5
    assert _ids_corte_idh_buscados() == []


def test_cjsg_parse_incluir_corte_idh_extrai_os_campos_da_linha():
    """Sem ``criterio``, a ementa fica truncada como nas linhas do TJ."""
    df = jus.scraper("tjpr").cjsg_parse(
        [load_sample("tjpr", "cjsg/single_page.html")], incluir_corte_idh=True
    )

    assert df.columns.tolist() == COLUNAS_COM_CORTE_IDH
    assert df["fonte"].tolist() == ["TJPR"] * 4 + ["Corte IDH"] + ["TJPR"]
    linha = df.iloc[4]
    assert linha["caso"] == "Comunidades Quilombolas de Alcântara vs. Brasil"
    assert linha["data_julgamento"] == date(2024, 11, 20)
    assert linha[["processo", "orgao_julgador", "relator"]].isna().all()
    assert linha["ementa"].startswith("O caso Comunidades Quilombolas de Alcântara vs. Brasil trata")
    assert linha["ementa"].endswith("Leia mais..")
    assert "Ementa disponibilizada" not in linha["ementa"]


def test_cjsg_parse_incluir_corte_idh_sem_resultados_tem_as_colunas():
    df = jus.scraper("tjpr").cjsg_parse(
        [load_sample("tjpr", "cjsg/no_results.html")], incluir_corte_idh=True
    )

    assert df.empty
    assert df.columns.tolist() == COLUNAS_COM_CORTE_IDH


@responses.activate
@pytest.mark.parametrize("valor", ["sim", "false", 1])
def test_cjsg_incluir_corte_idh_nao_bool_levanta_antes_da_rede(valor):
    with pytest.raises(ValidationError, match="incluir_corte_idh"):
        jus.scraper("tjpr").cjsg("dano moral", paginas=1, incluir_corte_idh=valor)

    assert len(responses.calls) == 0
