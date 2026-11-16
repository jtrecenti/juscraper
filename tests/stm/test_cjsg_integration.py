"""Testes ao vivo do cjsg do STM (precisam de rede).

O WAF do portal recusa pedidos conforme o IP de origem; com o marker
``anti_bot``, esse bloqueio vira ``xfail`` e qualquer outra falha continua
reprovando.
"""
import datetime
from pathlib import Path

import pytest

import juscraper as jus
from juscraper.courts.stm.download import RESULTS_PER_PAGE, cjsg_n_resultados

pytestmark = [pytest.mark.integration, pytest.mark.anti_bot]


@pytest.fixture(scope="module")
def stm():
    return jus.scraper("stm")


def _total_da_pagina(html: str) -> int:
    """Total de documentos que o portal anuncia na página."""
    total = cjsg_n_resultados(html)
    assert total is not None
    return total


def _total(stm, pesquisa, **filtros) -> int:
    """Total de documentos que o portal anuncia para a busca."""
    return _total_da_pagina(stm.cjsg_download(pesquisa, paginas=1, **filtros)[0])


def test_cjsg_duas_paginas_ao_vivo(stm):
    df = stm.cjsg("deserção", paginas=2)

    assert len(df) == 2 * RESULTS_PER_PAGE
    assert df["id_documento"].is_unique
    assert df[["processo", "classe", "relator", "data_julgamento"]].notna().all().all()
    # O portal ordena do julgamento mais recente para o mais antigo.
    assert df["data_julgamento"].is_monotonic_decreasing


def test_cjsg_filtros_ao_vivo(stm):
    df = stm.cjsg("deserção", paginas=1, classe="APELAÇÃO", campo="inteiro_teor")

    assert len(df) > 0
    assert set(df["classe"]) == {"APELAÇÃO"}


def test_cjsg_por_numero_ao_vivo(stm):
    df = stm.cjsg("7000612-54.2022.7.00.0000", campo="numero")

    assert "7000612-54.2022.7.00.0000" in set(df["processo"])


def test_cjsg_sem_resultados_ao_vivo(stm):
    df = stm.cjsg("juscraper_probe_zero_hits_xyzqwe")

    assert df.empty


def test_cjsg_intervalo_de_julgamento_ao_vivo(stm):
    """Termo e intervalo juntos: a combinação que só a pesquisa avançada faz."""
    inicio, fim = datetime.date(2024, 1, 1), datetime.date(2024, 12, 31)

    com_data = stm.cjsg("deserção", paginas=range(1, 3), data_julgamento_inicio=inicio, data_julgamento_fim=fim)

    assert len(com_data) > 0
    assert com_data["id_documento"].is_unique
    assert com_data["data_julgamento"].between(inicio, fim).all()
    assert com_data["ementa"].str.contains("deser", case=False).all()


def test_cjsg_intervalo_de_publicacao_ao_vivo(stm):
    inicio, fim = datetime.date(2024, 3, 1), datetime.date(2024, 3, 31)

    df = stm.cjsg("", paginas=1, data_publicacao_inicio=inicio, data_publicacao_fim=fim)

    assert len(df) > 0
    assert df["data_publicacao"].between(inicio, fim).all()


def test_cjsg_intervalo_sem_resultados_ao_vivo(stm):
    df = stm.cjsg("", data_julgamento_inicio="01/01/1800", data_julgamento_fim="31/12/1800")

    assert df.empty


def test_cjsg_campo_tudo_ao_vivo(stm):
    """Todos os campos incluem a ementa: a mesma expressão não pode achar menos."""
    html = stm.cjsg_download('"corrupção ativa"', paginas=1, campo="tudo")[0]
    df = stm.cjsg_parse([html])

    assert len(df) == RESULTS_PER_PAGE
    assert df[["processo", "classe", "relator", "data_julgamento"]].notna().all().all()
    assert _total_da_pagina(html) > _total(stm, '"corrupção ativa"')


def test_cjsg_campo_referencia_legislativa_ao_vivo(stm):
    """Na busca simples e, com data, na pesquisa avançada, que tem o mesmo campo."""
    inicio, fim = datetime.date(2024, 1, 1), datetime.date(2024, 12, 31)
    busca = {"paginas": 1, "campo": "referencia_legislativa"}

    html = stm.cjsg_download("290", **busca)[0]
    html_com_data = stm.cjsg_download("290", **busca, data_julgamento_inicio=inicio, data_julgamento_fim=fim)[0]
    df, df_com_data = stm.cjsg_parse([html]), stm.cjsg_parse([html_com_data])

    assert len(df) == RESULTS_PER_PAGE
    assert df[["processo", "classe", "relator", "data_julgamento"]].notna().all().all()
    assert len(df_com_data) > 0
    assert df_com_data["data_julgamento"].between(inicio, fim).all()
    assert _total_da_pagina(html) > _total_da_pagina(html_com_data)


PERIODO = {"data_julgamento_inicio": "01/01/2020", "data_julgamento_fim": "31/12/2024"}


def test_cjsg_operadores_com_data_ao_vivo(stm):
    """Com data, E, OU e NÃO valem como na busca simples.

    Em 16/11/2026, nesse período: expressão exata 48, E 53, OU 275.
    """
    frase = _total(stm, '"corrupção ativa"', **PERIODO)
    sem_operador = _total(stm, "corrupção ativa", **PERIODO)
    com_ou = _total(stm, "corrupção OU ativa", **PERIODO)
    so_corrupcao = _total(stm, "corrupção", **PERIODO)

    assert 0 < frase <= sem_operador < so_corrupcao < com_ou
    assert _total(stm, "corrupção NÃO ativa", **PERIODO) == so_corrupcao - sem_operador


def test_cjsg_curinga_e_parenteses_com_data_ao_vivo(stm):
    inteira = _total(stm, "deserção", **PERIODO)
    com_curinga = _total(stm, "deser*", **PERIODO)
    df = stm.cjsg("deser* E (furto OU peculato)", paginas=1, **PERIODO)

    assert 0 < inteira <= com_curinga
    assert 0 < len(df) < com_curinga
    assert df["ementa"].str.contains("deser", case=False).all()


@pytest.mark.parametrize(
    "url",
    [
        # Acórdão recente, no visualizador do eproc (do sample ``results_normal_page_01.html``).
        "https://eproc2g.stm.jus.br/eproc_2g_prod/externo_controlador.php?acao=visualizar_acordao"
        "&uuid=cbb3c68a2a6c472eef9576d05988cef88459cc90295cd7a818e1b04802c93d21",
        # Acórdão antigo, em PDF (do sample ``single_page.html``).
        "https://www2.stm.jus.br/pesquisa/acordao/2015/50/10022722/10022722.pdf",
    ],
)
def test_baixar_inteiro_teor_ao_vivo(stm, tmp_path, url):
    caminho = Path(stm.baixar_inteiro_teor(url, diretorio=str(tmp_path)))

    assert caminho.parent == tmp_path / "inteiro_teor"
    assert caminho.read_bytes().startswith(b"%PDF")
