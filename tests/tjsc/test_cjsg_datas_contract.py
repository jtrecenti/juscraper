"""TJSC cjsg: datas em DD/MM/YYYY, falha em redirecionamento (#495) e conexão derrubada."""
import datetime

import pytest
import requests
import responses
from responses.matchers import urlencoded_params_matcher
from responses.registries import OrderedRegistry

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


@responses.activate(registry=OrderedRegistry)
def test_cjsg_retenta_conexao_derrubada_pelo_portal(mocker):
    """Conexão derrubada pelo portal ganha nova tentativa.

    O portal reseta às vezes a conexão keep-alive reaproveitada (15/11/2026: 5
    de 18 pedidos em sequência rápida na mesma sessão). Sem nova tentativa, a
    terceira busca seguida de uma instância caía com ``ConnectionError``.
    """
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        SEARCH_URL,
        body=requests.ConnectionError(ConnectionResetError(54, "Connection reset by peer")),
    )
    responses.add(
        responses.POST,
        SEARCH_URL,
        body=load_sample_bytes("tjsc", "cjsg/single_page.html"),
        status=200,
        content_type="text/html; charset=iso-8859-1",
    )

    df = jus.scraper("tjsc").cjsg("plano saude paciente doenca rara", paginas=1)

    assert len(df) > 0
    assert len(responses.calls) == 2
