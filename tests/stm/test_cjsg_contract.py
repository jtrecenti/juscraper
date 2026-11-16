"""Contratos offline do cjsg do STM.

A busca é um GET em ``consulta.php``. Os samples saem de
``tests/fixtures/capture/stm.py`` (ver ``samples/cjsg/README.md``), menos
``waf_rejected.html``, que é a resposta direta do portal a um IP de datacenter.
"""
import datetime
from pathlib import Path

import pytest
import responses
from responses.matchers import query_param_matcher

import juscraper as jus
from juscraper.core.exceptions import BotChallengeBlockedError
from juscraper.courts.stm.download import BASE_URL, build_cjsg_params
from juscraper.courts.stm.parse import COLUNAS
from tests._helpers import load_sample

INDEX_URL = "https://jurisprudencia.stm.jus.br/index.php"
SAMPLES_CJSG = Path(__file__).parent / "samples" / "cjsg"


def _add_page(pesquisa: str, pagina: int, sample: str, campo: str = "ementa", **filtros) -> None:
    responses.add(
        responses.GET,
        BASE_URL,
        body=load_sample("stm", f"cjsg/{sample}"),
        content_type="text/html; charset=UTF-8",
        match=[query_param_matcher(build_cjsg_params(pesquisa, pagina, campo, **filtros))],
    )


@responses.activate
def test_cjsg_paginas_none_baixa_todas(mocker):
    """O contador "1 - 100 de 205" dá três páginas, com ``start`` 0, 100 e 200."""
    sleep = mocker.patch("time.sleep")
    _add_page('"corrupção ativa"', 1, "results_normal_page_01.html")
    _add_page('"corrupção ativa"', 2, "results_normal_page_02.html")
    _add_page('"corrupção ativa"', 3, "results_normal_page_03.html")

    df = jus.scraper("stm", sleep_time=3).cjsg('"corrupção ativa"')

    assert [call.request.params["start"] for call in responses.calls] == ["0", "100", "200"]
    assert sleep.call_args_list == [mocker.call(3), mocker.call(3)]
    assert list(df.columns) == COLUNAS
    assert len(df) == 205
    assert df["id_documento"].is_unique
    # Só estes campos vêm em todo documento; os demais faltam nos mais antigos.
    assert df[["processo", "classe", "relator", "data_julgamento", "ementa", "id_documento"]].notna().all().all()
    assert df["url_inteiro_teor"].dropna().str.startswith("https://").all()


@responses.activate
def test_cjsg_primeiro_documento(mocker):
    """Os valores saem como o portal os publica, com as datas em ``date``."""
    mocker.patch("time.sleep")
    _add_page("0000088-44.2014.7.07.0007", 1, "single_page.html", campo="numero")

    df = jus.scraper("stm").cjsg("0000088-44.2014.7.07.0007", campo="numero")

    assert len(responses.calls) == 1
    assert len(df) == 1
    linha = df.iloc[0]
    assert linha["processo"] == "0000088-44.2014.7.07.0007"
    assert linha["classe"] == "APELAÇÃO"
    assert linha["relator"] == "MARIA ELIZABETH GUIMARÃES TEIXEIRA ROCHA"
    assert linha["relator_acordao"] is None
    assert linha["revisor"] == "LUIS CARLOS GOMES MATTOS"
    assert linha["assunto"] == "1) DIREITO PENAL MILITAR,CRIMES CONTRA O PATRIMÔNIO,FURTO,FURTO ."
    assert linha["data_autuacao"] == datetime.date(2015, 3, 23)
    assert linha["data_julgamento"] == datetime.date(2015, 11, 10)
    assert linha["data_publicacao"] == datetime.date(2015, 12, 10)
    assert linha["ementa"].startswith("RECURSO DEFENSIVO. APELAÇÃO. FURTO SIMPLES.")
    assert linha["url_inteiro_teor"] == "https://www2.stm.jus.br/pesquisa/acordao/2015/50/10022722/10022722.pdf"
    assert linha["id_documento"] == "fde435a51e657229ddd7f670b2a704e3"


# Os dois samples saem do script de captura, de um IP que o portal aceite.
# O ``skipif`` é provisório: sai no commit que gravar os samples.
@pytest.mark.skipif(
    not (SAMPLES_CJSG / "campo_tudo.html").exists(),
    reason="samples de campo='tudo' e 'referencia_legislativa' ainda não capturados (prova residencial)",
)
@pytest.mark.parametrize(
    ("pesquisa", "campo", "sample"),
    [
        ('"corrupção ativa"', "tudo", "campo_tudo.html"),
        ("290", "referencia_legislativa", "campo_referencia_legislativa.html"),
    ],
)
@responses.activate
def test_cjsg_demais_campos_de_busca(mocker, pesquisa, campo, sample):
    """``tudo`` e ``referencia_legislativa`` respondem no template das demais buscas."""
    mocker.patch("time.sleep")
    relator = "CARLOS VUYK DE AQUINO"
    _add_page(pesquisa, 1, sample, campo=campo, relator=relator)

    df = jus.scraper("stm").cjsg(pesquisa, paginas=1, campo=campo, relator=relator)

    assert list(df.columns) == COLUNAS
    assert len(df) > 0
    assert df["id_documento"].is_unique
    assert set(df["relator"]) == {relator}
    assert df[["processo", "classe", "data_julgamento", "ementa"]].notna().all().all()


@responses.activate
def test_cjsg_relator_do_acordao(mocker):
    """``relator_acordao`` só vem nos documentos em que o relator ficou vencido."""
    mocker.patch("time.sleep")
    _add_page('"corrupção ativa"', 1, "results_normal_page_01.html")

    df = jus.scraper("stm").cjsg('"corrupção ativa"', paginas=1)

    assert df["relator_acordao"].notna().sum() == 10
    assert (df["relator_acordao"].dropna() != df.loc[df["relator_acordao"].notna(), "relator"]).all()


@responses.activate
def test_cjsg_pagina_seguinte_sem_documentos_levanta(mocker):
    """Página dentro do total que volta sem contador não vira coleta menor em silêncio."""
    mocker.patch("time.sleep")
    _add_page('"corrupção ativa"', 1, "results_normal_page_01.html")
    _add_page('"corrupção ativa"', 2, "no_results.html")

    with pytest.raises(ValueError, match="página 2 da busca veio sem o contador"):
        jus.scraper("stm").cjsg('"corrupção ativa"')


@responses.activate
def test_cjsg_paginas_pedidas(mocker):
    """``paginas=[2]`` pede só a segunda página."""
    mocker.patch("time.sleep")
    _add_page('"corrupção ativa"', 2, "results_normal_page_02.html")

    df = jus.scraper("stm").cjsg('"corrupção ativa"', paginas=[2])

    assert len(responses.calls) == 1
    assert len(df) == 100


@responses.activate
def test_cjsg_sem_resultados(mocker):
    """Busca vazia: o portal redireciona para ``index.php``, que mostra o aviso."""
    mocker.patch("time.sleep")
    responses.add(
        responses.GET,
        BASE_URL,
        status=302,
        headers={"Location": f"{INDEX_URL}?search_filter_option=jurisprudencia&search_filter=numero"},
    )
    responses.add(
        responses.GET,
        INDEX_URL,
        body=load_sample("stm", "cjsg/no_results.html"),
        content_type="text/html; charset=UTF-8",
    )

    df = jus.scraper("stm").cjsg("0000000-00.0000.0.00.0000", campo="numero")

    assert df.empty
    assert list(df.columns) == COLUNAS


@responses.activate
def test_cjsg_bloqueio_do_waf_levanta():
    """A página "Request Rejected" vem com HTTP 200 e não pode virar busca vazia."""
    responses.add(
        responses.GET,
        BASE_URL,
        body=load_sample("stm", "cjsg/waf_rejected.html"),
        content_type="text/html; charset=utf-8",
    )

    with pytest.raises(BotChallengeBlockedError, match="Request Rejected") as erro:
        jus.scraper("stm").cjsg("deserção")

    assert erro.value.reference == "14748640621862346384"


@responses.activate
def test_cjsg_pagina_sem_contador_levanta():
    """Página do portal sem contador nem aviso de busca vazia não vira DataFrame vazio."""
    sem_aviso = load_sample("stm", "cjsg/no_results.html").replace("Nenhum documento encontrado", "")
    responses.add(responses.GET, BASE_URL, body=sem_aviso, content_type="text/html; charset=UTF-8")

    with pytest.raises(ValueError, match="não traz a contagem"):
        jus.scraper("stm").cjsg("deserção")
