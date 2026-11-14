"""Contratos de ``incluir_corte_idh`` no cjsg do TJPR.

O portal mistura à tabela de jurisprudência até 10 precedentes da Corte IDH
por página (linhas com ``input[name=idsSelecionadosCidh]``). Por padrão o
parser os descarta; com ``incluir_corte_idh=True`` eles voltam com
``fonte="Corte IDH"`` e o nome do caso em ``caso``. O parâmetro não altera a
requisição de busca: os POSTs abaixo usam o mesmo matcher de corpo do modo
padrão.
"""
from datetime import date
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
import responses
from bs4 import BeautifulSoup
from responses.matchers import urlencoded_params_matcher

import juscraper as jus
from juscraper.courts.tjpr.download import VISUALIZAR_URL, get_ementa_completa
from juscraper.courts.tjpr.parse import cjsg_parse
from tests._helpers import load_sample, query_param_subset_matcher
from tests.tjpr._helpers import add_ementa_completa, add_home, add_search_page

COLUNAS_TJ = ["processo", "orgao_julgador", "relator", "data_julgamento", "ementa"]
COLUNAS_COM_CORTE_IDH = [*COLUNAS_TJ, "fonte", "caso"]
# Linhas da Corte IDH truncadas em "Leia mais.." nas páginas 1 e 2 de
# "dano moral"; as de id 114, 25, 18, 103 e 9 já trazem a ementa inteira.
IDS_CORTE_IDH_TRUNCADOS = {
    "106", "117", "120", "119", "118", "116", "115", "104", "107",
    "105", "23", "15", "17", "19", "16",
}


def _add_ementas_completas() -> None:
    add_ementa_completa()
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


def _buscas_completas() -> list[tuple[str, str, str]]:
    """``(actionType, idProcesso, criterio)`` de cada GET a ``visualizarDecisao.do``."""
    buscas = []
    for call in responses.calls:
        if call.request.url.startswith(VISUALIZAR_URL):
            q = parse_qs(urlsplit(call.request.url).query, keep_blank_values=True)
            buscas.append((q["actionType"][0], q["idProcesso"][0], q["criterio"][0]))
    return buscas


def _ids_corte_idh_buscados() -> list[str]:
    return [id_ for acao, id_, _ in _buscas_completas() if acao == "exibirTextoCompletoCidh"]


@responses.activate
def test_cjsg_incluir_corte_idh_mantem_as_linhas_marcadas(mocker):
    mocker.patch("time.sleep")
    add_home()
    add_search_page("dano moral", 1, "cjsg/results_normal_page_01.html")
    add_search_page("dano moral", 2, "cjsg/results_normal_page_02.html")
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
    add_search_page("quilombola", 1, "cjsg/single_page.html")
    _add_ementas_completas()

    df = jus.scraper("tjpr").cjsg("quilombola", paginas=1)

    assert df.columns.tolist() == COLUNAS_TJ
    assert len(df) == 5
    assert _ids_corte_idh_buscados() == []


def test_cjsg_parse_incluir_corte_idh_extrai_os_campos_da_linha():
    """Sem ``request_fn``, a ementa fica truncada como nas linhas do TJ."""
    df = cjsg_parse([load_sample("tjpr", "cjsg/single_page.html")], incluir_corte_idh=True)

    assert df.columns.tolist() == COLUNAS_COM_CORTE_IDH
    assert df["fonte"].tolist() == ["TJPR"] * 4 + ["Corte IDH"] + ["TJPR"]
    linha = df.iloc[4]
    assert linha["caso"] == "Comunidades Quilombolas de Alcântara vs. Brasil"
    assert linha["data_julgamento"] == date(2024, 11, 20)
    assert linha[["processo", "orgao_julgador", "relator"]].isna().all()
    assert linha["ementa"].startswith("O caso Comunidades Quilombolas de Alcântara vs. Brasil trata")
    # Truncada como a do TJ: termina nas reticências do portal, sem o link.
    assert linha["ementa"].endswith("Embora o Brasil...")
    assert "Leia mais" not in linha["ementa"]
    assert "Ementa disponibilizada" not in linha["ementa"]


@responses.activate
def test_cjsg_sem_termo_completa_as_ementas_do_tj_e_da_corte_idh(mocker):
    """Busca sem termo (``pesquisa=""``) também completa as ementas truncadas.

    Sample real da busca vazia: 3 linhas do TJ e 9 da Corte IDH em "Leia
    mais..". O portal manda ``criterio`` vazio, e o texto vem inteiro.
    """
    mocker.patch("time.sleep")
    add_home()
    add_search_page("", 1, "cjsg/results_sem_termo.html")
    _add_ementas_completas()

    df = jus.scraper("tjpr").cjsg("", paginas=1, incluir_corte_idh=True)

    assert len(df) == 50
    assert not df["ementa"].str.contains("Leia mais|Erro ao buscar").any()
    assert sorted(_buscas_completas()) == sorted(
        [("exibirTextoCompleto", i, "") for i in ("2100000040060902", "2100000039933592", "2100000039781812")]
        + [("exibirTextoCompletoCidh", i, "") for i in ("122", "121", "106", "117", "120", "119", "118", "116", "115")]
    )


@responses.activate
def test_cjsg_parse_sem_criterio_completa_a_ementa_da_corte_idh(mocker):
    """``cjsg_parse`` do scraper busca a ementa completa mesmo sem ``criterio``."""
    mocker.patch("time.sleep")
    _add_ementas_completas()

    df = jus.scraper("tjpr").cjsg_parse(
        [load_sample("tjpr", "cjsg/single_page.html")], incluir_corte_idh=True
    )

    assert _ids_corte_idh_buscados() == ["120"]
    assert df.iloc[4]["ementa"].endswith("num contexto de discriminação estrutural.")


def test_cjsg_parse_ordem_das_colunas_nao_depende_da_primeira_linha():
    """Página que começa por uma linha da Corte IDH mantém a ordem das colunas."""
    html = load_sample("tjpr", "cjsg/single_page.html")
    soup = BeautifulSoup(html, "html.parser")
    tabela = soup.select_one("table.resultTable.jurisprudencia")
    linha_corte_idh = tabela.select_one("tr.cidh").extract()
    tabela.find_all("tr")[0].insert_after(linha_corte_idh)

    df = cjsg_parse([str(soup)], incluir_corte_idh=True)

    assert df.columns.tolist() == COLUNAS_COM_CORTE_IDH
    assert df["fonte"].tolist() == ["Corte IDH"] + ["TJPR"] * 5


def test_get_ementa_completa_codifica_o_criterio(mocker):
    request_fn = mocker.Mock(return_value=SimpleNamespace(text="Texto <span class='high'>a</span>b."))

    texto = get_ementa_completa(request_fn, "exibirTextoCompletoCidh", "120", "dano & moral")

    assert texto == "Texto ab."
    assert request_fn.call_args.args == ("GET", VISUALIZAR_URL)
    assert request_fn.call_args.kwargs["params"] == {
        "actionType": "exibirTextoCompletoCidh",
        "idProcesso": "120",
        "criterio": "dano & moral",
    }


@responses.activate
@pytest.mark.parametrize("valor", ["sim", "false", 1])
def test_cjsg_incluir_corte_idh_nao_bool_levanta_antes_da_rede(valor):
    with pytest.raises(TypeError, match="incluir_corte_idh deve ser bool"):
        jus.scraper("tjpr").cjsg("dano moral", paginas=1, incluir_corte_idh=valor)

    assert len(responses.calls) == 0


def test_cjsg_parse_incluir_corte_idh_nao_bool_levanta():
    with pytest.raises(TypeError, match="incluir_corte_idh deve ser bool"):
        jus.scraper("tjpr").cjsg_parse([], incluir_corte_idh="false")


@responses.activate
def test_cjsg_download_recusa_incluir_corte_idh():
    """O download não muda com a opção; aceitá-la e ignorá-la perderia as linhas no parse."""
    with pytest.raises(TypeError, match="Passe incluir_corte_idh a cjsg_parse"):
        jus.scraper("tjpr").cjsg_download("dano moral", paginas=1, incluir_corte_idh=True)

    assert len(responses.calls) == 0
