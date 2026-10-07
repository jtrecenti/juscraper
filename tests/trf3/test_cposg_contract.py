"""Contratos offline do ``TRF3Scraper.cposg`` (consulta pública de 2º grau).

Mesma API do 1º grau, em ``pje2g-consultapublica.trf3.jus.br``. Os samples
vêm de ``tests/fixtures/capture/trf3.py``.
"""
from __future__ import annotations

import pandas as pd
import pytest
import responses

import juscraper as jus
from juscraper.courts.trf3.download import BASE_URL_1G, BASE_URL_2G
from juscraper.courts.trf3.schemas import OutputCposgTRF3
from tests.trf3._api import carregar, registrar_busca, registrar_processo

CNJ_APELACAO = "50211226520184036100"
CNJ_AGRAVO = "50262427520264030000"
CNJ_SO_NO_1G = "50035362120254036342"


@pytest.fixture(autouse=True)
def _sem_espera(mocker):
    mocker.patch("time.sleep")


@responses.activate
def test_cposg_traz_recurso_de_2o_grau_com_turma() -> None:
    """Apelação com movimentações em 3 páginas; ``orgao_julgador_colegiado`` traz a turma."""
    paginas = registrar_processo(BASE_URL_2G, "cposg", "normal")
    df = jus.scraper("trf3", sleep_time=0).cposg("5021122-65.2018.4.03.6100")

    assert len(df) == 1
    row = df.iloc[0]
    assert row["id_cnj"] == CNJ_APELACAO
    assert row["processo"] == "5021122-65.2018.4.03.6100"
    assert row["classe"] == "APELAÇÃO CÍVEL (198)"
    assert row["orgao_julgador_colegiado"] == "4ª Turma"
    assert row["orgao_julgador"] == "Gab. 13 - DES. FED. MONICA NOBRE"
    assert row["data_distribuicao"] == "01/12/2020"
    assert row["polo_ativo"][0]["tipo"] == "APELANTE"
    total = carregar("cposg", "normal_movimentacoes_page_0.json")["pageInfo"]["count"]
    assert len(row["movimentacoes"]) == total > 15
    OutputCposgTRF3.model_validate(row.to_dict())
    assert len(responses.calls) == 2 + paginas
    assert all(c.request.url.startswith(BASE_URL_2G) for c in responses.calls)


@responses.activate
def test_cposg_pagina_unica_com_polo_passivo_em_erro() -> None:
    """Agravo com tudo numa página; o ``poloPassivo`` que a API responde 500 sai ``None``."""
    paginas = registrar_processo(BASE_URL_2G, "cposg", "pagina_unica")
    df = jus.scraper("trf3", sleep_time=0).cposg(CNJ_AGRAVO)

    row = df.iloc[0]
    assert row["classe"] == "AGRAVO DE INSTRUMENTO (202)"
    assert row["polo_passivo"] is None
    assert len(row["movimentacoes"]) == 10
    assert len(row["documentos"]) == 1
    # Uma página por recurso com sample + as 4 tentativas no poloPassivo.
    assert len(responses.calls) == 2 + paginas + 4


@responses.activate
def test_cposg_sem_resultado_no_2o_grau() -> None:
    """Processo que só existe no 1º grau vira linha só com ``id_cnj`` no ``cposg``."""
    registrar_busca(BASE_URL_2G, "cposg", "sem_resultado", "5003536-21.2025.4.03.6342")
    df = jus.scraper("trf3", sleep_time=0).cposg(CNJ_SO_NO_1G)

    assert list(df.columns) == ["id_cnj"]
    assert df.iloc[0]["id_cnj"] == CNJ_SO_NO_1G
    assert not any(c.request.url.startswith(BASE_URL_1G) for c in responses.calls)


@responses.activate
def test_cposg_download_e_parse_separados() -> None:
    """``cposg_download`` consulta o host de 2º grau; ``cposg_parse`` monta o DataFrame."""
    registrar_processo(BASE_URL_2G, "cposg", "normal")
    scraper = jus.scraper("trf3", sleep_time=0)
    brutos = scraper.cposg_download(CNJ_APELACAO)
    df = scraper.cposg_parse(brutos, [CNJ_APELACAO])

    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["orgao_julgador_colegiado"] == "4ª Turma"


def test_cposg_rejeita_kwarg_desconhecido() -> None:
    """Kwarg desconhecido vira ``TypeError`` com o nome do método."""
    scraper = jus.scraper("trf3", sleep_time=0)
    with pytest.raises(TypeError, match=r"cposg got unexpected keyword"):
        scraper.cposg(CNJ_APELACAO, grau=2)
