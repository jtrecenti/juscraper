"""Offline contract tests for TJGO cjsg.

The Projudi search endpoint requires a GET on the form URL first to prime
session cookies; subsequent POSTs return ``iso-8859-1`` HTML. The contract
mocks both calls and asserts the form body sent on each page, including
the ``cf-turnstile-response=""`` literal. Since 12/11/2026 (Projudi 3.194.1)
the backend validates the Cloudflare Turnstile token and answers every search
without it with the empty form, so an empty search emits ``UserWarning``.
"""
from datetime import date

import pandas as pd
import pytest
import responses
from responses.matchers import urlencoded_params_matcher

import juscraper as jus
from juscraper.courts.tjgo.download import SEARCH_URL, _extract_total, build_cjsg_payload
from juscraper.courts.tjgo.parse import _split_blocks, cjsg_parse
from juscraper.courts.tjgo.schemas import OutputCJSGTJGO
from juscraper.schemas import OutputCJSGBase
from tests._helpers import corpo_enviado, load_sample_bytes

CJSG_FIELDS = {
    "processo", "id_arquivo", "serventia", "relator",
    "tipo_ato", "data_publicacao", "texto",
}


def _add_get_prime() -> None:
    responses.add(responses.GET, SEARCH_URL, body=b"", status=200)


def _add_post(pesquisa: str, page: int, sample_path: str, body: bytes | None = None) -> None:
    responses.add(
        responses.POST,
        SEARCH_URL,
        body=body if body is not None else load_sample_bytes("tjgo", sample_path),
        status=200,
        content_type="text/html; charset=iso-8859-1",
        match=[urlencoded_params_matcher(
            build_cjsg_payload(pesquisa=pesquisa, page=page), allow_blank=True,
        )],
    )


@responses.activate
def test_cjsg_typical_com_paginacao(mocker):
    """Two pages: GET primes cookies, then two POSTs with matching bodies."""
    mocker.patch("time.sleep")
    _add_get_prime()
    _add_post("dano moral", page=1, sample_path="cjsg/results_normal_page_01.html")
    _add_post("dano moral", page=2, sample_path="cjsg/results_normal_page_02.html")

    df = jus.scraper("tjgo").cjsg("dano moral", paginas=range(1, 3))

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_FIELDS
    assert len(df) > 0


@responses.activate
def test_cjsg_single_page(mocker):
    """Single-hit query: GET + a single POST."""
    mocker.patch("time.sleep")
    _add_get_prime()
    _add_post("usucapiao extraordinario predio rural familia",
              page=1, sample_path="cjsg/single_page.html")

    df = jus.scraper("tjgo").cjsg(
        "usucapiao extraordinario predio rural familia", paginas=1
    )

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_FIELDS
    assert len(df) == 1


@responses.activate
@pytest.mark.parametrize(
    ("pesquisa", "sample_path"),
    [
        ("juscraper_probe_zero_hits_xyzqwe", "cjsg/no_results.html"),
        # Resposta real a "dano moral" sem o token (Projudi 3.194.1).
        ("dano moral", "cjsg/blocked_turnstile.html"),
    ],
    ids=["sem_resultados", "bloqueada_pelo_turnstile"],
)
def test_cjsg_busca_vazia_avisa_do_turnstile(mocker, pesquisa, sample_path):
    """Empty search returns an empty DataFrame and warns about Turnstile.

    The portal answers a blocked search (no Turnstile token) the same way as
    a genuine zero-hit search, so every empty search warns.
    """
    mocker.patch("time.sleep")
    _add_get_prime()
    _add_post(pesquisa, page=1, sample_path=sample_path)

    with pytest.warns(UserWarning, match="Turnstile"):
        df = jus.scraper("tjgo").cjsg(pesquisa, paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert df.empty
    assert set(df.columns) == CJSG_FIELDS


def test_cjsg_parse_sem_paginas_traz_as_colunas():
    """Sem paginas, o DataFrame vazio tambem traz as colunas."""
    assert set(cjsg_parse([]).columns) == CJSG_FIELDS


def test_cjsg_colunas_sao_as_do_output():
    """As colunas sao ``processo`` e os campos proprios de ``OutputCJSGTJGO``."""
    proprios = set(OutputCJSGTJGO.model_fields) - set(OutputCJSGBase.model_fields)
    assert {"processo"} | proprios == CJSG_FIELDS


@responses.activate
@pytest.mark.parametrize("paginas", [None, 1])
def test_cjsg_com_resultados_sem_contagem_levanta_sem_avisar(mocker, paginas):
    """Results without the count ``legend`` are new markup: ValueError, no Turnstile warning, no page 2.

    HTML derived from the real ``results_normal_page_01.html``.
    """
    mocker.patch("time.sleep")
    html = load_sample_bytes("tjgo", "cjsg/results_normal_page_01.html")
    sem_legend = html.replace(b'class="formLocalizarLegenda"', b'class="outra-classe"')
    assert sem_legend != html
    _add_get_prime()
    _add_post("dano moral", page=1, sample_path="", body=sem_legend)

    with pytest.raises(ValueError, match="TJGO: a página lida não traz a contagem"):  # filterwarnings=error
        jus.scraper("tjgo").cjsg("dano moral", paginas=paginas)


@responses.activate
def test_cjsg_resultado_formato_atual(mocker):
    """Pagina real de 15/11/2026, capturada com o token Turnstile (issue #436).

    Para regravar: ``TJGO_JSESSIONID=... python -m tests.fixtures.capture.tjgo atual``.

    No HTML atual a ``<div class="search-result">`` traz atributos depois da
    classe (``data-realizador``, ``data-id-arquivo``...), com ``->`` dentro de
    ``data-classe-acao``; a data vem como "Julgado em ..." e nao ha mais o
    paragrafo do tipo de ato.
    """
    mocker.patch("time.sleep")
    _add_get_prime()
    _add_post("dano moral", page=1, sample_path="cjsg/results_julgado_em_page_01.html")

    df = jus.scraper("tjgo").cjsg("dano moral", paginas=1)  # filterwarnings=error

    assert len(df) == 10
    assert set(df.columns) == CJSG_FIELDS
    for col in ("processo", "id_arquivo", "serventia", "relator", "texto", "data_publicacao"):
        assert df[col].notna().all(), col
    assert df["tipo_ato"].isna().all()
    primeira = df.iloc[0]
    assert primeira["processo"] == "5323172-88.2023.8.09.0029"
    # id do inteiro teor (abrirArquivo), nao o data-id-arquivo da div (580585407)
    assert primeira["id_arquivo"] == "580585406"
    assert primeira["relator"] == "RICARDO PRATA - (DESEMBARGADOR)"
    assert primeira["data_publicacao"] == date(2026, 11, 15)
    assert primeira["texto"].startswith("EMENTA:DIREITO CIVIL")


def test_cjsg_formato_atual_bloco_comeca_depois_da_tag():
    """O ``>`` dentro de ``data-classe-acao`` nao encerra a tag de abertura."""
    html = load_sample_bytes("tjgo", "cjsg/results_julgado_em_page_01.html").decode("iso-8859-1")
    blocos = _split_blocks(html)
    assert len(blocos) == 10
    assert all("data-numero" not in b.split("<h4>")[0] for b in blocos)


@pytest.mark.parametrize(
    "sample_path",
    [
        "cjsg/results_julgado_em_page_01.html",
        "cjsg/results_normal_page_01.html",
        "cjsg/results_normal_page_02.html",
        "cjsg/single_page.html",
    ],
)
def test_cjsg_ultimo_bloco_termina_no_fim_dos_resultados(sample_path):
    """O ultimo bloco para no ``</fieldset>`` dos resultados, sem o rodape da pagina."""
    html = load_sample_bytes("tjgo", sample_path).decode("iso-8859-1")
    ultimo = _split_blocks(html)[-1]
    assert "</fieldset>" not in ultimo
    assert "modalBusca" not in ultimo
    assert "conteudoTexto" in ultimo


def test_cjsg_formato_atual_ignora_trechos_do_inteiro_teor():
    """Os trechos do INTEIRO TEOR depois do texto nao viram ``tipo_ato``."""
    html = load_sample_bytes("tjgo", "cjsg/results_julgado_em_page_01.html").decode("iso-8859-1")
    trechos = (
        '<p style="text-align:justify"><b>1</b><i> resultado(s) encontrado(s) '
        "no INTEIRO TEOR.</i></p>"
    )
    fim_do_texto = html.index("</p>", html.index('class="conteudoTexto')) + len("</p>")
    df = cjsg_parse([html[:fim_do_texto] + trechos + html[fim_do_texto:]])
    assert df["tipo_ato"].isna().all()


def test_cjsg_formato_atual_contagem():
    """A contagem do HTML atual continua na ``legend.formLocalizarLegenda``."""
    html = load_sample_bytes("tjgo", "cjsg/results_julgado_em_page_01.html").decode("iso-8859-1")
    assert _extract_total(html) == 20255


@responses.activate
def test_cjsg_payload_carries_empty_turnstile_token(mocker):
    """The body carries ``cf-turnstile-response`` empty (the scraper has no token)."""
    mocker.patch("time.sleep")
    _add_get_prime()
    _add_post("dano moral", page=1, sample_path="cjsg/results_normal_page_01.html")

    jus.scraper("tjgo").cjsg("dano moral", paginas=1)

    post_calls = [c for c in responses.calls if c.request.method == "POST"]
    assert len(post_calls) == 1
    body = corpo_enviado(post_calls[0].request)
    assert "cf-turnstile-response=" in body
