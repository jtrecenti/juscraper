"""Offline contract tests for TJRO cjsg.

TJRO paginates via ``from`` offset: ``paginas=1`` sends ``from=0``,
``paginas=2`` sends ``from=10``. The contract confirms both the DataFrame
schema and the offset-based wire payload, page-by-page.
"""
import json

import pandas as pd
import responses
from responses.matchers import json_params_matcher

import juscraper as jus
from juscraper.courts.tjro.download import BASE_URL, RESULTS_PER_PAGE, build_cjsg_payload
from tests._helpers import corpo_json_enviado, load_sample

CJSG_MIN_COLUMNS = {
    "processo", "tipo", "classe", "orgao_julgador", "orgao_julgador_colegiado",
    "relator", "assunto", "data_julgamento", "data_publicacao", "ementa",
}


def _add_page(pesquisa: str, pagina_1based: int, sample_path: str) -> None:
    offset = (pagina_1based - 1) * RESULTS_PER_PAGE
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("tjro", sample_path),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(build_cjsg_payload(pesquisa, offset=offset))],
    )


@responses.activate
def test_cjsg_typical_com_paginacao(mocker):
    """Two-page query exercises offset 0 and offset ``RESULTS_PER_PAGE``."""
    mocker.patch("time.sleep")
    _add_page("dano moral", 1, "cjsg/results_normal_page_01.json")
    _add_page("dano moral", 2, "cjsg/results_normal_page_02.json")

    df = jus.scraper("tjro").cjsg("dano moral", paginas=range(1, 3))

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_MIN_COLUMNS
    assert len(df) > 0


def test_cjsg_parse_traz_a_chave_do_documento_sem_deduplicar():
    """``id_documento`` é o ``_id`` de cada hit, na ordem do portal, na última coluna."""
    brutos = [json.loads(load_sample("tjro", f"cjsg/results_normal_page_0{n}.json")) for n in (1, 2)]
    ids = [hit["_id"] for bruto in brutos for hit in bruto["hits"]["hits"]]

    df = jus.scraper("tjro").cjsg_parse(brutos)

    assert df.columns[-1] == "id_documento"
    assert df["id_documento"].tolist() == ids
    assert df["id_documento"].is_unique
    assert len(df) == len(ids)


@responses.activate
def test_cjsg_single_page(mocker):
    """Single page: the request goes out with ``from=0`` and the default filter in ``tipo.raw``."""
    mocker.patch("time.sleep")
    _add_page("mandado de seguranca", 1, "cjsg/single_page.json")

    df = jus.scraper("tjro").cjsg("mandado de seguranca", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_MIN_COLUMNS
    assert len(df) > 0

    # O matcher deriva o esperado de ``build_cjsg_payload``; a chave do filtro
    # se confere no corpo enviado, para não depender do próprio builder.
    campos = corpo_json_enviado(responses.calls[0].request)["fields"]
    assert campos["tipo.raw"] == ["EMENTA"]
    assert "tipo" not in campos


@responses.activate
def test_cjsg_no_results(mocker):
    """Zero-hit query returns an empty DataFrame."""
    mocker.patch("time.sleep")
    _add_page("juscraper_probe_zero_hits_xyzqwe", 1, "cjsg/no_results.json")

    df = jus.scraper("tjro").cjsg("juscraper_probe_zero_hits_xyzqwe", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert df.empty
