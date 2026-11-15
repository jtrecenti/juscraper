"""TJSC cjsg: datas em DD/MM/YYYY e falha em redirecionamento (#495)."""
import datetime

import pytest
import responses
from responses.matchers import urlencoded_params_matcher

import juscraper as jus
from juscraper.courts.tjsc.download import SEARCH_URL, build_cjsg_form_body, cjsg_url_for_page
from tests._helpers import load_sample_bytes


@responses.activate
def test_cjsg_data_julgamento_chega_em_formato_brasileiro_e_filtra(mocker):
    """O caso da issue: julgamento entre 10 e 13/03/2025 vai em DD/MM/YYYY.

    As datas do resultado (sample real, consulta de 15/11/2026) ficam dentro
    do intervalo.
    """
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        SEARCH_URL,
        body=load_sample_bytes("tjsc", "cjsg/filtro_data_julgamento.html"),
        status=200,
        content_type="text/html; charset=iso-8859-1",
        match=[urlencoded_params_matcher(
            build_cjsg_form_body(
                "direito",
                page=1,
                dt_decisao_inicio="10/03/2025",
                dt_decisao_fim="13/03/2025",
            ),
            allow_blank=True,
        )],
    )

    df = jus.scraper("tjsc").cjsg(
        "direito",
        paginas=1,
        data_julgamento_inicio="2025-03-10",
        data_julgamento_fim="2025-03-13",
    )

    assert len(df) == 10
    assert df["processo"].notna().all()
    assert df["data_julgamento"].between(
        datetime.date(2025, 3, 10), datetime.date(2025, 3, 13)
    ).all()


@pytest.mark.parametrize("pagina", [1, 2])
@responses.activate
def test_cjsg_redirecionamento_da_busca_falha_alto(mocker, pagina):
    """Redirecionamento da busca levanta erro, na primeira página e na AJAX."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        cjsg_url_for_page(pagina),
        status=302,
        headers={"Location": "https://outro.tjsc.jus.br/listar_resultados"},
    )

    with pytest.raises(RuntimeError, match="redirecionada"):
        jus.scraper("tjsc").cjsg_download("direito", paginas=[pagina])

    assert len(responses.calls) == 1
