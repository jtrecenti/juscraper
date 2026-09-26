"""Offline contract tests for TJMG ``cposg`` (consulta processual 2a instancia).

Samples capturados de ``www4.tjmg.jus.br/juridico/sf`` em 26/09/2026:

* ``resultado_single`` — CNJ com um recurso (apelacao criminal).
* ``resultado_multi`` — CNJ com dois recursos (apelacao + embargos).
* ``resultado_segredo`` — todos os recursos em segredo de justica.
* ``resultado_baixado`` — processo fisico antigo (2010), sem "NUMERO TJMG".
* ``resultado_not_found`` — "Nenhum processo encontrado".
* ``partes_*`` — pagina "Todas as Partes/Advogados" de cada recurso.
"""
from __future__ import annotations

import pandas as pd
import pytest
import responses
from responses import matchers

import juscraper as jus
from juscraper.courts.tjmg.schemas import OutputCPOSGTJMG
from tests._helpers import load_sample_bytes

BASE = "https://www4.tjmg.jus.br/juridico/sf"
RESULTADO_URL = f"{BASE}/proc_resultado2.jsp"
PARTES_URL = f"{BASE}/proc_partes_advogados2.jsp"

EXPECTED_COLUMNS = {
    "id_cnj",
    "processo",
    "processo_interno",
    "segredo_justica",
    "situacao",
    "secretaria",
    "classe",
    "assunto",
    "orgao_julgador",
    "data_cadastramento",
    "data_distribuicao",
    "partes",
}


def _add(url: str, numero: str, sample: str, status: int = 200) -> None:
    responses.add(
        responses.GET,
        url,
        body=load_sample_bytes("tjmg", f"cposg/{sample}.html"),
        status=status,
        content_type="text/html; charset=ISO-8859-1",
        match=[matchers.query_param_matcher({"listaProcessos": numero})],
    )


@pytest.fixture
def scraper():
    return jus.scraper("tjmg", sleep_time=0)


@responses.activate
def test_cposg_single_returns_partes_and_advogados(scraper):
    _add(RESULTADO_URL, "00003597920208130205", "resultado_single")
    _add(PARTES_URL, "10000264083767001", "partes_single")

    df = scraper.cposg("0000359-79.2020.8.13.0205")

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= EXPECTED_COLUMNS
    assert len(df) == 1
    row = df.iloc[0]
    assert row["id_cnj"] == "00003597920208130205"
    assert row["processo"] == "0000359-79.2020.8.13.0205"
    assert row["processo_interno"] == "1.0000.26.408376-7/001"
    assert row["classe"] == "Apelação Criminal"
    assert row["orgao_julgador"] == "3ª CÂMARA CRIMINAL"
    assert row["situacao"] == "ATIVO"
    assert not row["segredo_justica"]
    assert str(row["data_distribuicao"]) == "2026-06-09"
    assert row["partes"][0] == {
        "tipo": "Apelante",
        "nome": "LEANDRO SERGIO DIAS",
        "baixa": None,
        "advogados": [{"oab": "165085N/MG", "nome": "LUIS FERNANDO BATISTA"}],
    }
    assert [p["tipo"] for p in row["partes"]] == ["Apelante", "Apelado", "Vítima"]
    for record in df.to_dict(orient="records"):
        OutputCPOSGTJMG.model_validate(record)


@responses.activate
def test_cposg_multi_recursos_one_row_each(scraper):
    _add(RESULTADO_URL, "50003445720258130461", "resultado_multi")
    _add(PARTES_URL, "10000261492847001", "partes_multi_1")
    _add(PARTES_URL, "10000261492847002", "partes_multi_2")

    df = scraper.cposg(["5000344-57.2025.8.13.0461"])

    assert list(df["processo_interno"]) == ["1.0000.26.149284-7/001", "1.0000.26.149284-7/002"]
    assert list(df["classe"]) == ["Apelação Cível", "Embargos de Declaração-Cv"]
    apelante = df.iloc[0]["partes"][0]
    assert apelante["nome"] == "RAFAELA LUCIA MARCELINO"
    assert [a["oab"] for a in apelante["advogados"]] == ["159502N/MG", "164867N/MG", "182853N/MG"]
    assert df.iloc[1]["partes"][1]["tipo"] == "Embargado"


@responses.activate
def test_cposg_accepts_numero_tjmg(scraper):
    _add(RESULTADO_URL, "10000264083767001", "resultado_single")
    _add(PARTES_URL, "10000264083767001", "partes_single")

    df = scraper.cposg("1.0000.26.408376-7/001")

    assert df.iloc[0]["processo"] == "0000359-79.2020.8.13.0205"


@responses.activate
def test_cposg_baixado_without_numero_tjmg_header(scraper):
    _add(RESULTADO_URL, "00370502120108130439", "resultado_baixado")
    _add(PARTES_URL, "10439100037050001", "partes_baixado")
    _add(PARTES_URL, "10439100037050002", "partes_baixado")

    df = scraper.cposg("0037050-21.2010.8.13.0439")

    assert list(df["processo_interno"]) == ["1.0439.10.003705-0/001", "1.0439.10.003705-0/002"]
    assert list(df["situacao"]) == ["BAIXADO", "BAIXADO"]
    apelado = df.iloc[1]["partes"][1]
    assert apelado["baixa"] == "04/05/2012 - REMETIDOS à COMARCA DE ORIGEM"
    assert apelado["nome"] == "MUNICIPIO DE MURIAE"
    assert len(apelado["advogados"]) == 2


@responses.activate
def test_cposg_segredo_skips_partes_request(scraper):
    _add(RESULTADO_URL, "50055464220238130701", "resultado_segredo")

    df = scraper.cposg("5005546-42.2023.8.13.0701")

    assert len(df) == 4
    assert df["segredo_justica"].all()
    assert df["partes"].isna().all()
    assert len(responses.calls) == 1


@responses.activate
def test_cposg_not_found_keeps_id_cnj_row(scraper):
    _add(RESULTADO_URL, "12345678920208130024", "resultado_not_found")

    df = scraper.cposg("1234567-89.2020.8.13.0024")

    assert len(df) == 1
    assert df.iloc[0]["id_cnj"] == "12345678920208130024"


def test_cposg_rejects_unknown_kwarg(scraper):
    with pytest.raises(TypeError, match="foo"):
        scraper.cposg("0000359-79.2020.8.13.0205", foo=1)


def test_cposg_rejects_invalid_length(scraper):
    with pytest.raises(ValueError, match="17 digitos"):
        scraper.cposg("123")
