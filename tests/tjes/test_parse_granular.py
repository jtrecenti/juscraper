"""Caracterização do parser de resultados TJES, compartilhado por CJSG e CJPG."""

import copy
import datetime
import json

import pandas as pd
import pytest

from juscraper.courts.tjes.parse import cjsg_parse
from tests._helpers import load_sample


def test_parse_preserva_valores_colunas_ordem_e_entrada():
    paginas = json.loads(load_sample("tjes", "cjsg/mixed_pages.json"))
    original = copy.deepcopy(paginas)

    resultado = cjsg_parse(paginas)

    primeira_linha = {
        "processo": "0000001-00.2026.8.08.0000",
        "ementa": "<p>Texto preservado</p>",
        "relator": "Relatora A; Relator B",
        "orgao_julgador": "Câmara Cível",
        "classe": "Apelação",
        "classe_judicial_sigla": "AC",
        "assunto": "Dano moral",
        "jurisdicao": None,
        "competencia": None,
        "dt_juntada": datetime.date(2026, 4, 17),
        "id": "doc-1",
        "acordao": False,
        "lista_assunto": "Consumidor; 42; None",
        "localizacao": "Gabinete",
        "cargo_julgador": "Desembargador",
        "cd_assunto_principal": 0.0,
        "cd_classe_judicial": 198.0,
        "id_assunto_principal": "1; 2",
        "id_classe_judicial": 198.0,
        "id_jurisdicao": None,
        "id_localizacao": None,
        "id_cargo_julgador": 3.0,
        "id_bin": 4.0,
    }
    assert resultado.columns.tolist() == list(primeira_linha)
    assert resultado.iloc[0].to_dict() == primeira_linha
    assert resultado.index.tolist() == [0, 1, 2, 3]
    assert resultado["processo"].tolist() == [
        "0000001-00.2026.8.08.0000", "0000002-00.2026.8.08.0000", None, "0000001-00.2026.8.08.0000",
    ]
    assert resultado.loc[1, "localizacao"] == {"codigo": 7}
    assert resultado.loc[1, "competencia"] == ""
    assert resultado.loc[1, "lista_assunto"] is None
    assert resultado.loc[1:, "dt_juntada"].isna().all()
    assert resultado.loc[2].isna().all()
    assert resultado["dt_juntada"].dtype == object
    assert paginas == original


@pytest.mark.parametrize("paginas", [[], [{}], [{"docs": []}], [{}, {"docs": []}]])
def test_parse_sem_documentos_retorna_dataframe_sem_colunas(paginas):
    pd.testing.assert_frame_equal(cjsg_parse(paginas), pd.DataFrame())


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [(None, None), ([], None), ([""], ""), ([False, 0], "False; 0"), ([[1, 2]], "[1, 2]"), (False, False)],
)
def test_parse_normaliza_listas_sem_descartar_escalares(valor, esperado):
    resultado = cjsg_parse([{"docs": [{"ementa": valor}]}])
    assert resultado.loc[0, "ementa"] == esperado
