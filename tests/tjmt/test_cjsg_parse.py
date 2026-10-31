"""Testes do parser e do DataFrame público do TJMT."""
from datetime import date

import pandas as pd
import pytest

from juscraper.courts.tjmt.client import TJMTScraper
from juscraper.courts.tjmt.parse import CJSG_COLUMNS, cjsg_parse


def _resultado(tipo: str, *, nulo: bool = False) -> dict:
    return {
        "idDocumento": 123 if tipo == "Acordao" else 456,
        "id": "uuid-que-nao-deve-ser-usado",
        "tipo": tipo,
        "conteudo": "<p>Ementa <strong>com destaque</strong>.</p>",
        "observacao": None if nulo else "Observação",
        "numeroUnicoFormatado": "0000000-00.2024.8.11.0001",
        "nomeClasse": "APELAÇÃO CÍVEL",
        "assunto": None if nulo else "Dano moral",
        "tipoAcao": "DIREITO CIVIL",
        "tipoProcesso": "Cível",
        "nomeRelator": None if nulo else "RELATOR TESTE",
        "nomeRedatorDesignado": None,
        "nomeCamara": "PRIMEIRA CÂMARA",
        "nomeClasseEsferaProcessual": "APEL",
        "dataJulgamento": "2024-01-02T03:04:05.123",
        "dataPublicacao": None if nulo else "2024-01-03T00:00:00",
        "instancia": "Segunda",
        "origem": "PJe",
        "descricaoJulgamento": "UNÂNIME",
    }


def _pagina(*resultados: dict) -> dict:
    return {
        "success": True,
        "errorMessage": None,
        "value": {"resultados": list(resultados)},
    }


def test_parser_mapeia_acordao_e_decisao_para_as_18_colunas():
    registros = cjsg_parse(
        [_pagina(_resultado("Acordao"), _resultado("DecisaoMonocratica"))],
        tipo_consulta="Acordao",
    )

    assert list(registros[0]) == list(CJSG_COLUMNS)
    assert registros[0]["id"] == 123
    assert registros[0]["classe"] == "APELAÇÃO CÍVEL"
    assert registros[0]["sigla_classe_feito"] == "APEL"
    assert registros[0]["julgamento"] == "UNÂNIME"
    assert registros[0]["ementa"] == "Ementa com destaque."
    assert registros[1]["id"] == 456
    assert registros[1]["tipo"] == "DecisaoMonocratica"


def test_cjsg_preserva_colunas_converte_datas_e_nulos(mocker):
    scraper = TJMTScraper()
    mocker.patch.object(
        scraper,
        "cjsg_download",
        return_value=[_pagina(_resultado("Acordao", nulo=True))],
    )

    dataframe = scraper.cjsg("termo", paginas=1)

    assert isinstance(dataframe, pd.DataFrame)
    assert list(dataframe.columns) == list(CJSG_COLUMNS)
    assert dataframe.loc[0, "id"] == 123
    assert pd.api.types.is_integer_dtype(dataframe["id"])
    assert dataframe.loc[0, "data_julgamento"] == date(2024, 1, 2)
    assert pd.isna(dataframe.loc[0, "data_publicacao"])
    assert pd.isna(dataframe.loc[0, "observacao"])


def test_cjsg_converte_datas_com_fusos_mistos_sem_alterar_o_dia_civil(mocker):
    primeiro = _resultado("Acordao")
    primeiro["dataJulgamento"] = "2024-01-02T23:30:00-03:00"
    primeiro["dataPublicacao"] = "2024-01-03T00:30:00+02:00"
    segundo = _resultado("DecisaoMonocratica")
    segundo["dataJulgamento"] = "2024-01-04T12:00:00"
    segundo["dataPublicacao"] = "2024-01-05T00:00:00Z"
    terceiro = _resultado("Acordao")
    terceiro["dataJulgamento"] = "data inválida"
    terceiro["dataPublicacao"] = None
    scraper = TJMTScraper()
    mocker.patch.object(
        scraper,
        "cjsg_download",
        return_value=[_pagina(primeiro, segundo, terceiro)],
    )

    dataframe = scraper.cjsg("termo", paginas=1)

    assert dataframe["data_julgamento"].tolist()[:2] == [date(2024, 1, 2), date(2024, 1, 4)]
    assert dataframe["data_publicacao"].tolist()[:2] == [date(2024, 1, 3), date(2024, 1, 5)]
    assert pd.isna(dataframe.loc[2, "data_julgamento"])
    assert pd.isna(dataframe.loc[2, "data_publicacao"])


def test_cjsg_publico_processa_decisao_monocratica(mocker):
    scraper = TJMTScraper()
    mocker.patch.object(
        scraper,
        "cjsg_download",
        return_value=[_pagina(_resultado("DecisaoMonocratica"))],
    )

    dataframe = scraper.cjsg(
        "termo",
        paginas=1,
        tipo_consulta="DecisaoMonocratica",
    )

    assert list(dataframe.columns) == list(CJSG_COLUMNS)
    assert dataframe.loc[0, "tipo"] == "DecisaoMonocratica"
    assert dataframe.loc[0, "id"] == 456


def test_cjsg_vazio_preserva_as_18_colunas(mocker):
    scraper = TJMTScraper()
    mocker.patch.object(scraper, "cjsg_download", return_value=[_pagina()])

    dataframe = scraper.cjsg("termo", paginas=1)

    assert dataframe.empty
    assert list(dataframe.columns) == list(CJSG_COLUMNS)


@pytest.mark.parametrize(
    "resposta",
    [
        {"success": False, "errorMessage": "falha", "value": {"resultados": []}},
        {"success": True, "errorMessage": "falha", "value": {"resultados": []}},
    ],
)
def test_parser_rejeita_resposta_de_erro_em_vez_de_busca_vazia(resposta):
    with pytest.raises(ValueError, match=r"(falha|erro)"):
        cjsg_parse([resposta])


@pytest.mark.parametrize(
    "resposta",
    [{}, {"value": {}}, {"value": {"resultados": None}}],
)
def test_parser_rejeita_resposta_malformada(resposta):
    with pytest.raises(
        (TypeError, ValueError), match=r"indica falha|value.resultados|value como"
    ):
        cjsg_parse([resposta])
