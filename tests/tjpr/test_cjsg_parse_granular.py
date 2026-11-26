"""Granular characterization tests for the TJPR CJSG parser."""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest
import requests
from bs4 import BeautifulSoup

from juscraper.core.base import _texto_ausente_como_none
from juscraper.courts.tjpr.download import VISUALIZAR_URL
from juscraper.courts.tjpr.parse import cjsg_parse
from tests._helpers import load_sample

EXPECTED_COLUMNS = ["processo", "orgao_julgador", "relator", "data_julgamento", "ementa"]
TRUNCATED_WITH_ID = "Resumo truncado. Leia mais..."
TRUNCATED_WITHOUT_INPUT = "Resumo sem id documental. Leia mais..."
TRUNCATED_WITHOUT_VALUE = "Resumo com id sem valor. Leia mais..."


def test_cjsg_parse_preserves_row_variants_and_exact_dtypes():
    # O parser devolve o que o pandas da vez produzir; o metodo publico passa a
    # saida por ``_texto_ausente_como_none``, que mantem texto ausente como
    # None tambem no pandas 3. O teste confere o valor que o usuario recebe.
    result = _texto_ausente_como_none(
        cjsg_parse(
            [load_sample("tjpr", "cjsg/parser_edge_cases.html")],
            criterio=None,
        )
    )

    assert result.columns.tolist() == EXPECTED_COLUMNS
    assert result.dtypes.astype(str).to_dict() == dict.fromkeys(EXPECTED_COLUMNS, "object")
    assert result.shape == (5, 5)
    assert result.loc[0].to_dict() == {
        "processo": "0000001-11.2024.8.16.0001",
        "orgao_julgador": "Câmara Inline",
        "relator": "Relator Inline",
        "data_julgamento": date(2024, 2, 1),
        "ementa": "Ementa curta sem expansão.",
    }
    assert result.loc[1].to_dict() == {
        "processo": "0000002-22.2024.8.16.0002",
        "orgao_julgador": "Câmara Irmã",
        "relator": "Relator Irmão",
        "data_julgamento": date(2024, 4, 3),
        "ementa": TRUNCATED_WITH_ID,
    }
    assert result.loc[2, ["processo", "orgao_julgador", "relator"]].tolist() == ["", "", ""]
    assert pd.isna(result.loc[2, "data_julgamento"])
    assert result.loc[2, "ementa"] == "Ementa sem metadados."
    assert result.loc[3].to_dict() == {
        "processo": "0000003-33.2024.8.16.0003",
        "orgao_julgador": "Câmara Sem Id",
        "relator": "Relator Sem Id",
        "data_julgamento": date(2024, 6, 5),
        "ementa": TRUNCATED_WITHOUT_INPUT,
    }
    assert result.loc[4].to_dict() == {
        "processo": "0000004-44.2024.8.16.0004",
        "orgao_julgador": "Câmara Id Vazio",
        "relator": "Relator Id Vazio",
        "data_julgamento": date(2024, 8, 7),
        "ementa": TRUNCATED_WITHOUT_VALUE,
    }


def test_cjsg_parse_ignores_corte_idh_row_and_keeps_judicial_results():
    result = cjsg_parse(
        [load_sample("tjpr", "cjsg/results_normal_page_02.html")],
        criterio=None,
    )

    # A página traz 50 linhas: 40 do TJPR e 10 da Corte IDH.
    assert len(result) == 40
    assert result["processo"].eq("0037484-81.2017.8.16.0018").any()
    assert not result["ementa"].str.contains("Mota Abarullo", case=False).any(), (
        "a linha da Corte IDH 'Caso: Mota Abarullo e Outros Vs. Venezuela' "
        "foi incluída como resultado judicial"
    )


@pytest.mark.parametrize(("criterio", "criterio_enviado"), [("dano moral", "dano moral"), (None, ""), ("", "")])
def test_cjsg_parse_fetches_full_ementa_with_injected_request(mocker, criterio, criterio_enviado):
    # Texto puro, com quebra de linha própria e o destaque no meio da palavra.
    request_fn = mocker.Mock(
        return_value=SimpleNamespace(text="Ementa <span class='high'>DANO</span>S MORAIS\nSegunda linha\n")
    )

    result = cjsg_parse(
        [load_sample("tjpr", "cjsg/parser_edge_cases.html")],
        criterio=criterio,
        request_fn=request_fn,
    )

    assert result.loc[0, "ementa"] == "Ementa curta sem expansão."
    assert result.loc[1, "ementa"] == "Ementa DANOS MORAIS\nSegunda linha"
    # Linhas com "Leia mais..." sem id documental utilizável ficam truncadas, sem requisição.
    assert result.loc[3, "ementa"] == TRUNCATED_WITHOUT_INPUT
    assert result.loc[4, "ementa"] == TRUNCATED_WITHOUT_VALUE
    request_fn.assert_called_once()
    method, url = request_fn.call_args.args
    assert method == "GET"
    assert url == VISUALIZAR_URL
    assert request_fn.call_args.kwargs["params"] == {
        "actionType": "exibirTextoCompleto",
        "idProcesso": "div-id",
        "criterio": criterio_enviado,
    }


@pytest.mark.parametrize(
    "corpo",
    [
        pytest.param(load_sample("tjpr", "cjsg/pagina_intranet.html"), id="pagina-do-portal"),
        pytest.param("", id="vazia"),
        pytest.param("<div>javax.servlet.ServletException</div>", id="fragmento-html"),
    ],
)
def test_cjsg_parse_recusa_resposta_que_nao_e_a_ementa(mocker, corpo):
    """A página do portal (menu da intranet) ou a resposta vazia não viram ementa.

    ``pagina_intranet.html`` é o que ``pesquisa.do?actionType=exibirTextoCompleto``
    devolvia no lugar da ementa; ``visualizarDecisao.do`` responde vazio a id
    desconhecido. O texto da ementa só traz o ``<span>`` do destaque; outra
    marcação também é recusada. A linha fica truncada e ganha o aviso de erro.
    """
    request_fn = mocker.Mock(return_value=SimpleNamespace(text=corpo))

    result = cjsg_parse(
        [load_sample("tjpr", "cjsg/parser_edge_cases.html")],
        criterio="dano moral",
        request_fn=request_fn,
    )

    assert result.loc[1, "ementa"].startswith(f"{TRUNCATED_WITH_ID}\n[Erro ao buscar ementa completa: ")
    assert "não trouxe o texto da ementa" in result.loc[1, "ementa"]
    assert "Intranet" not in result.loc[1, "ementa"]
    assert "ServletException" not in result.loc[1, "ementa"]


def test_cjsg_parse_keeps_truncated_ementa_after_row_request_error(mocker):
    request_fn = mocker.Mock(side_effect=requests.RequestException("indisponível"))

    result = cjsg_parse(
        [load_sample("tjpr", "cjsg/parser_edge_cases.html")],
        criterio="dano moral",
        request_fn=request_fn,
    )

    assert result.loc[1, "ementa"] == (
        f"{TRUNCATED_WITH_ID}\n"
        "[Erro ao buscar ementa completa: indisponível]"
    )
    assert result.loc[2, "ementa"] == "Ementa sem metadados."
    assert result.loc[3, "ementa"] == TRUNCATED_WITHOUT_INPUT
    assert result.loc[4, "ementa"] == TRUNCATED_WITHOUT_VALUE
    request_fn.assert_called_once()


def test_cjsg_parse_propagates_programming_errors_from_full_ementa_fetch(mocker):
    request_fn = mocker.Mock(side_effect=AttributeError("contrato inválido"))

    with pytest.raises(AttributeError, match="contrato inválido"):
        cjsg_parse(
            [load_sample("tjpr", "cjsg/parser_edge_cases.html")],
            criterio="dano moral",
            request_fn=request_fn,
        )


def test_decisao_sem_ementa_sai_ausente():
    """Monocrática com o ``div#ementa<id>`` vazio sai com ementa ausente, não ``""``.

    Sample real da busca sem termo: 33 das 40 linhas do TJ vêm sem ementa.
    """
    html = load_sample("tjpr", "cjsg/results_sem_termo.html")
    tabela = BeautifulSoup(html, "html.parser").select_one("table.resultTable.jurisprudencia")
    linhas = [
        linha for linha in tabela.find_all("tr")[1:]
        if not linha.find("input", {"name": "idsSelecionadosCidh"}) and len(linha.find_all("td")) >= 2
    ]

    df = cjsg_parse([html])

    assert len(df) == len(linhas)
    for ementa, linha in zip(df["ementa"], linhas, strict=True):
        if linha.find_all("td")[1].get_text(strip=True):
            assert isinstance(ementa, str)
            assert ementa
        else:
            assert pd.isna(ementa)
            assert "Decisão monocrática" in linha.find_all("td")[0].get_text()
    assert df["ementa"].isna().sum() == 33
