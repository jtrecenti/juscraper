"""Offline contract tests for TJDFT cjsg."""
import json
from datetime import date

import pandas as pd
import pytest
import responses
from responses.matchers import json_params_matcher

import juscraper as jus
from juscraper.courts.tjdft.schemas import OutputCJSGTJDFT
from tests._helpers import corpo_json_enviado, load_sample
from tests.fixtures.capture.tjdft import DATA_PUBLICACAO_COM_MONOCRATICAS

BASE = "https://jurisdf.tjdft.jus.br/api/v1/pesquisa"
CJSG_MIN_COLUMNS = {"processo", "ementa", "relator", "orgao_julgador", "data_julgamento", "data_publicacao"}
# Nomes crus da API que o parser renomeia para os canônicos (refs #12).
COLUNAS_CRUAS_RENOMEADAS = {"nomeRelator", "descricaoOrgaoJulgador", "dataJulgamento", "dataPublicacao"}


def _payload(
    pesquisa: str,
    pagina: int,
    *,
    sinonimos: bool = True,
    espelho: bool = True,
    inteiro_teor: bool = False,
    tamanho_pagina: int = 10,
    termos_acessorios: list | None = None,
) -> dict:
    return {
        "query": pesquisa,
        "termosAcessorios": list(termos_acessorios) if termos_acessorios else [],
        # ``pagina`` é a página 1-based de ``cjsg``; a API conta a partir de 0.
        "pagina": pagina - 1,
        "tamanho": tamanho_pagina,
        "sinonimos": sinonimos,
        "espelho": espelho,
        "inteiroTeor": inteiro_teor,
        "retornaInteiroTeor": False,
        "retornaTotalizacao": True,
    }


def _add_page(pesquisa: str, pagina: int, sample_path: str, **kwargs) -> None:
    responses.add(
        responses.POST,
        BASE,
        body=load_sample("tjdft", sample_path),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(_payload(pesquisa, pagina, **kwargs))],
    )


@responses.activate
def test_cjsg_typical_com_paginacao(mocker):
    """Typical multi-page query returns a DataFrame with the minimum schema."""
    mocker.patch("time.sleep")
    _add_page("dano moral", 1, "cjsg/results_normal_page_01.json")
    _add_page("dano moral", 2, "cjsg/results_normal_page_02.json")

    df = jus.scraper("tjdft").cjsg("dano moral", paginas=range(1, 3))

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_MIN_COLUMNS
    assert len(df) > 0


@pytest.mark.parametrize(
    "sample",
    [
        "results_normal_page_01.json",
        "results_normal_page_02.json",
        "single_page.json",
        "todas_paginas_page_01.json",
        "todas_paginas_page_02.json",
        "com_decisoes_monocraticas.json",
    ],
)
def test_cjsg_parse_renomeia_colunas_para_os_nomes_canonicos(sample):
    """Relator, órgão julgador e datas saem com os nomes dos demais tribunais.

    Decisões monocráticas (``base="decisoes"``) não trazem ``dataJulgamento``.
    """
    registros = json.loads(load_sample("tjdft", f"cjsg/{sample}"))["registros"]
    linhas = jus.scraper("tjdft").cjsg_parse(registros)

    assert len(linhas) == len(registros) > 0
    for bruto, linha in zip(registros, linhas, strict=True):
        assert not COLUNAS_CRUAS_RENOMEADAS & linha.keys()
        assert linha["relator"] == bruto["nomeRelator"]
        assert linha["orgao_julgador"] == bruto["descricaoOrgaoJulgador"]
        assert linha.get("data_julgamento") == bruto.get("dataJulgamento")
        assert linha["data_publicacao"] == bruto["dataPublicacao"]
        assert all(linha[col] for col in ("relator", "orgao_julgador", "data_publicacao")), linha["processo"]
        assert ("data_julgamento" in linha) == (bruto["base"] == "acordaos")
        OutputCJSGTJDFT.model_validate(linha)


@responses.activate
def test_cjsg_decisoes_monocraticas_saem_sem_data_de_julgamento(mocker):
    """Na página mista, a monocrática sai com relator e órgão, e ``data_julgamento`` vazia."""
    mocker.patch("time.sleep")
    _add_page(
        "direito penal",
        1,
        "cjsg/com_decisoes_monocraticas.json",
        termos_acessorios=[DATA_PUBLICACAO_COM_MONOCRATICAS],
    )

    df = jus.scraper("tjdft").cjsg(
        "direito penal",
        paginas=1,
        data_publicacao_inicio="2026-11-20",
        data_publicacao_fim="2026-11-20",
    )

    monocraticas = df["base"] == "decisoes"
    assert monocraticas.sum() == 2
    assert df.loc[monocraticas, "data_julgamento"].isna().all()
    assert df.loc[~monocraticas, "data_julgamento"].notna().all()
    assert df[["relator", "orgao_julgador", "data_publicacao"]].notna().all().all()


@responses.activate
def test_cjsg_single_page(mocker):
    """Single requested page returns parsed records without hitting the network again."""
    mocker.patch("time.sleep")
    _add_page("mandado de seguranca", 1, "cjsg/single_page.json")

    df = jus.scraper("tjdft").cjsg("mandado de seguranca", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_MIN_COLUMNS
    assert len(df) > 0


@responses.activate
def test_cjsg_datas_saem_como_date(mocker):
    """``data_julgamento``/``data_publicacao`` saem como ``date``, e não como texto ISO.

    A data é a do instante em UTC, a mesma do filtro da API: com
    ``data_publicacao`` em 14/11/2026, a API devolve a publicação de
    ``2026-11-14T00:56:36.000Z`` (conferido em 16/11/2026).
    """
    mocker.patch("time.sleep")
    _add_page("dano moral", 1, "cjsg/results_normal_page_01.json")
    _add_page("enfiteuse", 1, "cjsg/todas_paginas_page_01.json")

    scraper = jus.scraper("tjdft")
    df = pd.concat([scraper.cjsg("dano moral", paginas=1), scraper.cjsg("enfiteuse", paginas=1)])

    for col in ("data_julgamento", "data_publicacao"):
        assert df[col].map(type).eq(date).all(), col
    datas = df.set_index("processo")[["data_julgamento", "data_publicacao"]]
    assert tuple(datas.loc["0773607-82.2023.8.07.0016"]) == (date(2026, 11, 4), date(2026, 11, 14))
    assert tuple(datas.loc["20120111466064APC"]) == (date(2016, 10, 19), date(2016, 10, 27))


@responses.activate
def test_cjsg_no_results(mocker):
    """Zero-result query returns an empty DataFrame instead of raising."""
    mocker.patch("time.sleep")
    _add_page("juscraper_probe_zero_hits_xyzqwe", 1, "cjsg/no_results.json")

    df = jus.scraper("tjdft").cjsg("juscraper_probe_zero_hits_xyzqwe", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert df.empty


@responses.activate
def test_cjsg_paginas_none_busca_todas_as_paginas(mocker):
    """``paginas=None`` lê o total em ``hits.value`` e pede as páginas 0 e 1 da API."""
    mocker.patch("time.sleep")
    _add_page("enfiteuse", 1, "cjsg/todas_paginas_page_01.json")
    _add_page("enfiteuse", 2, "cjsg/todas_paginas_page_02.json")

    df = jus.scraper("tjdft").cjsg("enfiteuse", paginas=None)

    assert [corpo_json_enviado(call.request)["pagina"] for call in responses.calls] == [0, 1]
    assert len(df) == 13
    assert df["processo"].is_unique
    assert set(df.columns) >= CJSG_MIN_COLUMNS


@responses.activate
def test_cjsg_paginas_none_sem_resultados_faz_uma_requisicao(mocker):
    """Com ``hits.value == 0``, ``paginas=None`` para na primeira página."""
    mocker.patch("time.sleep")
    _add_page("juscraper_probe_zero_hits_xyzqwe", 1, "cjsg/no_results.json")

    df = jus.scraper("tjdft").cjsg("juscraper_probe_zero_hits_xyzqwe", paginas=None)

    assert len(responses.calls) == 1
    assert df.empty
