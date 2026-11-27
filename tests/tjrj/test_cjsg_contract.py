"""Offline contract tests for TJRJ cjsg.

The TJRJ flow has three steps: ``GET`` the ASPX form to extract hidden
fields, ``POST`` the form to seed the server-side session, then ``POST``
the JSON XHR per page. The contract mocks all three and pins the body
subset (everything except ``__VIEWSTATE`` / ``__VIEWSTATEGENERATOR`` /
``__EVENTVALIDATION`` — those rotate per request).
"""
import json

import pandas as pd
import pytest
import responses
from pydantic import ValidationError
from responses.matchers import json_params_matcher

import juscraper as jus
from juscraper.courts.tjrj.download import (
    FORM_URL,
    RESULT_URL,
    build_cjsg_payload,
    extract_default_year,
    extract_viewstate_fields,
)
from tests._helpers import corpo_enviado, load_sample, url_enviada, urlencoded_body_subset_matcher

CJSG_FIELDS = {
    "processo", "classe", "orgao_julgador", "relator", "ementa",
    "data_julgamento", "data_publicacao", "cod_documento",
}


RESULTS_PAGE_URL = "https://www3.tjrj.jus.br/EJURIS/ProcessarConsJurisES.aspx"


def _form_html() -> str:
    return load_sample("tjrj", "cjsg/post_initial.html")


def _xhr_payload(filename: str) -> dict:
    payload: dict = json.loads(load_sample("tjrj", f"cjsg/{filename}"))
    return payload


def _expected_body_subset(pesquisa: str, **overrides) -> dict:
    """Body keys we care about (drops the three rotating hidden fields).

    Built off ``build_cjsg_payload`` so the contract drifts with the source.
    """
    hidden = extract_viewstate_fields(_form_html())
    body = build_cjsg_payload(hidden=hidden, pesquisa=pesquisa, **overrides)
    body.pop("__VIEWSTATE", None)
    body.pop("__VIEWSTATEGENERATOR", None)
    body.pop("__EVENTVALIDATION", None)
    return body


def _add_form_get() -> None:
    responses.add(responses.GET, FORM_URL, body=_form_html(), status=200,
                  content_type="text/html; charset=utf-8")


def _add_form_post(pesquisa: str, page_seq: int = 0, **overrides) -> None:
    """Form POST answered like the backend: 302 to the results page with ``PageSeq``."""
    responses.add(
        responses.POST, FORM_URL, status=302,
        headers={"Location": f"/EJURIS/ProcessarConsJurisES.aspx?PageSeq={page_seq}&Version=1.2.2.3"},
        match=[urlencoded_body_subset_matcher(_expected_body_subset(pesquisa, **overrides))],
    )
    responses.add(responses.GET, RESULTS_PAGE_URL, body=b"", status=200)


def _add_xhr(num_pagina_0: int, sample_filename: str, page_seq: int = 0) -> None:
    responses.add(
        responses.POST, RESULT_URL,
        json=_xhr_payload(sample_filename), status=200,
        match=[json_params_matcher({"numPagina": num_pagina_0, "pageSeq": str(page_seq)})],
    )


@responses.activate
def test_cjsg_typical_com_paginacao(mocker):
    """Two-page query: GET, POST, two XHRs (numPagina=0 then 1)."""
    mocker.patch("time.sleep")
    _add_form_get()
    _add_form_post("dano moral", ano_inicio="2024", ano_fim="2024")
    _add_xhr(0, "xhr_page_01.json")
    _add_xhr(1, "xhr_page_02.json")

    df = jus.scraper("tjrj").cjsg(
        "dano moral", ano_inicio=2024, ano_fim=2024, paginas=range(1, 3),
    )

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_FIELDS
    assert len(df) == 20  # 10 docs/page × 2 páginas


@responses.activate
def test_cjsg_pagina_fora_do_total_e_pulada_sem_requisicao(mocker, caplog):
    """Página além do total não vira requisição: só fica o aviso no log."""
    mocker.patch("time.sleep")
    _add_form_get()
    _add_form_post("dano moral", ano_inicio="2024", ano_fim="2024")
    _add_xhr(0, "xhr_page_01.json")
    alem_do_total = 10_000  # a amostra tem 78.523 resultados, ou 7.853 páginas

    with caplog.at_level("WARNING", logger="juscraper.tjrj"):
        df = jus.scraper("tjrj").cjsg(
            "dano moral", ano_inicio=2024, ano_fim=2024, paginas=[1, alem_do_total],
        )

    assert len(df) == 10
    assert len([c for c in responses.calls if c.request.url == RESULT_URL]) == 1
    assert f"TJRJ: página {alem_do_total} fora do intervalo" in caplog.text


@responses.activate
def test_cjsg_single_page(mocker):
    """Narrow query whose hits fit on a single XHR call."""
    mocker.patch("time.sleep")
    _add_form_get()
    _add_form_post(
        "usucapiao extraordinario predio rural familia",
        ano_inicio="2024", ano_fim="2024",
    )
    _add_xhr(0, "xhr_single_page.json")

    df = jus.scraper("tjrj").cjsg(
        "usucapiao extraordinario predio rural familia",
        ano_inicio=2024, ano_fim=2024, paginas=1,
    )

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_FIELDS
    assert len(df) == 2


@responses.activate
def test_cjsg_no_results(mocker):
    """Zero-hit query returns an empty DataFrame, not an error."""
    mocker.patch("time.sleep")
    _add_form_get()
    _add_form_post(
        "juscraper_probe_zero_hits_xyzqwe",
        ano_inicio="2024", ano_fim="2024",
    )
    _add_xhr(0, "xhr_no_results.json")

    df = jus.scraper("tjrj").cjsg(
        "juscraper_probe_zero_hits_xyzqwe",
        ano_inicio=2024, ano_fim=2024, paginas=1,
    )

    assert isinstance(df, pd.DataFrame)
    assert df.empty


@responses.activate
def test_cjsg_payload_carries_blocked_words_hidden(mocker):
    """The form POST must carry ``hfListaPalavrasBloqueadas`` (refs #143).

    The hidden field's absence triggered a transient 500 in 2026-04-30 — the
    contract pins it so a future regression that drops the field surfaces in
    CI rather than as a backend 500 in the wild.
    """
    mocker.patch("time.sleep")
    _add_form_get()
    _add_form_post("dano moral", ano_inicio="2024", ano_fim="2024")
    _add_xhr(0, "xhr_page_01.json")

    jus.scraper("tjrj").cjsg(
        "dano moral", ano_inicio=2024, ano_fim=2024, paginas=1,
    )

    post_calls = [c for c in responses.calls if c.request.method == "POST"
                  and url_enviada(c.request).startswith(FORM_URL)]
    assert len(post_calls) == 1
    body = post_calls[0].request.body or ""
    if isinstance(body, bytes):
        body = body.decode("utf-8")
    assert "ctl00%24ContentPlaceHolder1%24hfListaPalavrasBloqueadas=" in body
    # Value comes from the GET sample — non-empty stopword list.
    assert "ACIMA" in body  # one of the words in the canonical TJRJ stopword list


def test_extract_default_year_uses_newest_dropdown_option():
    """``extract_default_year`` devolve a opcao mais nova de ``cmbAnoInicio``."""
    assert extract_default_year(_form_html()) == "2026"


def test_extract_default_year_fallback_sem_select():
    r"""Sem o ``<select>`` de ``cmbAnoInicio``, cai no maior ``\d{4}`` do HTML."""
    html = "<html><body><p>rodape 2019</p><p>atualizado em 2030</p></body></html>"
    assert extract_default_year(html) == "2030"


def test_extract_default_year_fallback_select_sem_option_valida():
    r"""``<select>`` presente mas sem ``<option value>`` cai no maior ``\d{4}``."""
    html = (
        '<select name="ctl00$ContentPlaceHolder1$cmbAnoInicio">'
        "<option>2021</option><option>2027</option>"
        "</select>"
    )
    assert extract_default_year(html) == "2027"


@responses.activate
def test_cjsg_sem_ano_usa_ano_corrente(mocker):
    """Sem ``ano_inicio``/``ano_fim``, o POST carrega o ano corrente (refs #278).

    O backend do TJRJ passou a exigir ``cmbAnoInicio``/``cmbAnoFim`` nao-vazios:
    enviar vazio retornava ``HTTP 500`` no POST do form. O contrato fixa o
    default (ano mais novo do dropdown, igual ao padrao do site) para que uma
    regressao que volte a mandar ano vazio quebre no CI, e nao como 500 no ar.
    """
    mocker.patch("time.sleep")
    _add_form_get()
    _add_form_post("dano moral", ano_inicio="2026", ano_fim="2026")
    _add_xhr(0, "xhr_page_01.json")

    jus.scraper("tjrj").cjsg("dano moral", paginas=1)

    post_calls = [c for c in responses.calls if c.request.method == "POST"
                  and url_enviada(c.request).startswith(FORM_URL)]
    assert len(post_calls) == 1
    body = post_calls[0].request.body or ""
    if isinstance(body, bytes):
        body = body.decode("utf-8")
    assert "ctl00%24ContentPlaceHolder1%24cmbAnoInicio=2026" in body
    assert "ctl00%24ContentPlaceHolder1%24cmbAnoFim=2026" in body
    # Nunca vazio — vazio e exatamente o que disparava o 500.
    assert "ctl00%24ContentPlaceHolder1%24cmbAnoInicio=&" not in body


@responses.activate
def test_cjsg_so_ano_inicio_completa_o_fim_com_ano_corrente(mocker):
    """So ``ano_inicio`` => ``ano_fim`` vira o ano corrente (refs #278).

    O ano explicito e respeitado e o omitido recebe o ano mais novo do
    dropdown, resultando num intervalo ``2020..ano-corrente`` em vez do antigo
    ``cmbAnoFim`` vazio (que disparava o 500). O caso inverso (so ``ano_fim``)
    esta em ``test_cjsg_so_ano_fim_comeca_no_ano_mais_antigo_da_origem``.
    """
    mocker.patch("time.sleep")
    _add_form_get()
    _add_form_post("dano moral", ano_inicio="2020", ano_fim="2026")
    _add_xhr(0, "xhr_page_01.json")

    jus.scraper("tjrj").cjsg("dano moral", ano_inicio=2020, paginas=1)

    post_calls = [c for c in responses.calls if c.request.method == "POST"
                  and url_enviada(c.request).startswith(FORM_URL)]
    assert len(post_calls) == 1
    body = post_calls[0].request.body or ""
    if isinstance(body, bytes):
        body = body.decode("utf-8")
    assert "ctl00%24ContentPlaceHolder1%24cmbAnoInicio=2020" in body
    assert "ctl00%24ContentPlaceHolder1%24cmbAnoFim=2026" in body


@responses.activate
def test_cjsg_so_ano_fim_comeca_no_ano_mais_antigo_da_origem(mocker):
    """So ``ano_fim`` => ``ano_inicio`` vira o ano mais antigo do combo (1975).

    Antes, o inicio caia no padrao do combo (o ano mais recente) e a busca ia
    com o intervalo invertido ``2026..2020``, que o JS do portal
    (``ValidarIntervaloData``) nao deixa submeter.
    """
    mocker.patch("time.sleep")
    _add_form_get()
    _add_form_post("dano moral", ano_inicio="1975", ano_fim="2020")
    _add_xhr(0, "xhr_page_01.json")

    df = jus.scraper("tjrj").cjsg("dano moral", ano_fim=2020, paginas=1)

    assert len(df) > 0


@responses.activate
def test_cjsg_intervalo_de_anos_invertido_levanta_antes_da_busca():
    """``ano_inicio > ano_fim`` levanta ``ValidationError``; o portal devolveria 0 documentos."""
    with pytest.raises(ValidationError, match=r"'ano_inicio' \(2024\) é posterior a 'ano_fim' \(2020\)"):
        jus.scraper("tjrj").cjsg("dano moral", ano_inicio=2024, ano_fim="2020", paginas=1)

    assert len(responses.calls) == 0


@responses.activate
def test_cjsg_mesma_instancia_le_a_busca_corrente(mocker):
    """Buscas seguidas na mesma instancia leem cada uma o proprio resultado.

    O servidor numera as buscas da sessao ASP.NET (``PageSeq`` 0, 1, ...) no
    redirect do form e guarda os parametros de cada uma. Pedir sempre
    ``pageSeq=0`` devolvia, sem erro, o resultado da primeira busca para todas
    as seguintes. A segunda busca tem duas paginas para fixar que a pagina 2
    tambem vai com o ``PageSeq`` da busca corrente.
    """
    mocker.patch("time.sleep")
    _add_form_get()
    _add_form_post(
        "usucapiao extraordinario predio rural familia", page_seq=0,
        ano_inicio="2024", ano_fim="2024",
    )
    _add_xhr(0, "xhr_single_page.json", page_seq=0)
    _add_form_get()
    _add_form_post("dano moral", page_seq=1, ano_inicio="2024", ano_fim="2024")
    _add_xhr(0, "xhr_page_01.json", page_seq=1)
    _add_xhr(1, "xhr_page_02.json", page_seq=1)

    tjrj = jus.scraper("tjrj")
    primeira = tjrj.cjsg_download(
        "usucapiao extraordinario predio rural familia",
        ano_inicio=2024, ano_fim=2024, paginas=1,
    )
    segunda = tjrj.cjsg_download("dano moral", ano_inicio=2024, ano_fim=2024, paginas=range(1, 3))

    assert primeira == [_xhr_payload("xhr_single_page.json")["d"]]
    assert segunda == [_xhr_payload("xhr_page_01.json")["d"], _xhr_payload("xhr_page_02.json")["d"]]


def test_cjsg_form_sem_redirect_levanta_erro(mocker):
    """Sem ``PageSeq`` no redirect a busca nao existe no servidor: erro, nao resultado alheio."""
    mocker.patch("time.sleep")
    with responses.RequestsMock() as rsps:
        rsps.add(responses.GET, FORM_URL, body=_form_html(), status=200,
                 content_type="text/html; charset=utf-8")
        rsps.add(responses.POST, FORM_URL, body=_form_html(), status=200)
        with pytest.raises(RuntimeError, match="nao redirecionou"):
            jus.scraper("tjrj").cjsg_download("dano moral", ano_inicio=2024, ano_fim=2024, paginas=1)


@responses.activate
def test_cjsg_turma_recursal_respeita_o_ano(mocker):
    """``origem`` fora do padrao do form passa pelo postback de ``cmbOrigem`` antes da busca.

    Trocar a origem no mesmo POST da busca fazia o servidor recarregar os
    combos de ano no ano corrente, e a Turma Recursal (``origem="4"``)
    devolvia o mesmo total para qualquer ano. A busca tem de ir com o estado
    devolvido pelo postback e sem ``chkEmentario``, que nesse form desmarca
    acordao e monocratica.
    """
    mocker.patch("time.sleep")
    postback_html = load_sample("tjrj", "cjsg/postback_origem_turma_recursal.html")
    postback_hidden = extract_viewstate_fields(postback_html)
    _add_form_get()
    responses.add(
        responses.POST, FORM_URL, body=postback_html, status=200,
        content_type="text/html; charset=utf-8",
        match=[urlencoded_body_subset_matcher({
            "__EVENTTARGET": "ctl00$ContentPlaceHolder1$cmbOrigem",
            "ctl00$ContentPlaceHolder1$cmbOrigem": "4",
        })],
    )
    responses.add(
        responses.POST, FORM_URL, status=302,
        headers={"Location": "/EJURIS/ProcessarConsJurisES.aspx?PageSeq=0&Version=1.2.2.3"},
        match=[urlencoded_body_subset_matcher({
            "__EVENTTARGET": "ctl00$ContentPlaceHolder1$btnPesquisar",
            "__VIEWSTATE": postback_hidden["__VIEWSTATE"],
            "__EVENTVALIDATION": postback_hidden["__EVENTVALIDATION"],
            "ctl00$ContentPlaceHolder1$txtTextoPesq": "cancelamento de voo",
            "ctl00$ContentPlaceHolder1$cmbOrigem": "4",
            "ctl00$ContentPlaceHolder1$cmbAnoInicio": "2025",
            "ctl00$ContentPlaceHolder1$cmbAnoFim": "2025",
            "ctl00$ContentPlaceHolder1$chkAcordao": "on",
            "ctl00$ContentPlaceHolder1$chkDecMon": "on",
        })],
    )
    responses.add(responses.GET, RESULTS_PAGE_URL, body=b"", status=200)
    _add_xhr(0, "xhr_turma_recursal.json")

    df = jus.scraper("tjrj").cjsg(
        "cancelamento de voo", origem="4", ano_inicio=2025, ano_fim=2025, paginas=1,
    )

    assert "chkEmentario" not in corpo_enviado(responses.calls[2].request)
    assert len(df) == 10
    assert {d.year for d in df["data_julgamento"]} == {2025}


@responses.activate
def test_cjsg_turma_recursal_competencia_fazendaria(mocker):
    """``competencia="3"`` so existe no form da Turma Recursal (#207).

    O postback de ``cmbOrigem`` sai do form ainda na origem padrao, que so
    oferece as competencias 1 e 2; com ``"3"`` nele, o servidor respondia
    HTTP 500. O postback leva ``"1"`` e a busca, ja no form da Turma Recursal,
    leva ``"3"``.
    """
    mocker.patch("time.sleep")
    postback_html = load_sample("tjrj", "cjsg/postback_origem_turma_recursal.html")
    _add_form_get()
    responses.add(
        responses.POST, FORM_URL, body=postback_html, status=200,
        content_type="text/html; charset=utf-8",
        match=[urlencoded_body_subset_matcher({
            "__EVENTTARGET": "ctl00$ContentPlaceHolder1$cmbOrigem",
            "ctl00$ContentPlaceHolder1$cmbOrigem": "4",
            "ctl00$ContentPlaceHolder1$cmbCompetencia": "1",
        })],
    )
    responses.add(
        responses.POST, FORM_URL, status=302,
        headers={"Location": "/EJURIS/ProcessarConsJurisES.aspx?PageSeq=0&Version=1.2.2.3"},
        match=[urlencoded_body_subset_matcher({
            "__EVENTTARGET": "ctl00$ContentPlaceHolder1$btnPesquisar",
            "ctl00$ContentPlaceHolder1$cmbOrigem": "4",
            "ctl00$ContentPlaceHolder1$cmbCompetencia": "3",
        })],
    )
    responses.add(responses.GET, RESULTS_PAGE_URL, body=b"", status=200)
    _add_xhr(0, "xhr_turma_recursal.json")

    df = jus.scraper("tjrj").cjsg("dano moral", origem="4", competencia=3, paginas=1)

    assert len(df) == 10


def _add_postback_origem(origem: str, sample: str) -> None:
    responses.add(
        responses.POST, FORM_URL, body=load_sample("tjrj", f"cjsg/{sample}"), status=200,
        content_type="text/html; charset=utf-8",
        match=[urlencoded_body_subset_matcher({
            "__EVENTTARGET": "ctl00$ContentPlaceHolder1$cmbOrigem",
            "ctl00$ContentPlaceHolder1$cmbOrigem": origem,
        })],
    )


def _add_busca(origem: str, ano: str, competencia: str) -> None:
    responses.add(
        responses.POST, FORM_URL, status=302,
        headers={"Location": "/EJURIS/ProcessarConsJurisES.aspx?PageSeq=0&Version=1.2.2.3"},
        match=[urlencoded_body_subset_matcher({
            "__EVENTTARGET": "ctl00$ContentPlaceHolder1$btnPesquisar",
            "ctl00$ContentPlaceHolder1$cmbOrigem": origem,
            "ctl00$ContentPlaceHolder1$cmbAnoInicio": ano,
            "ctl00$ContentPlaceHolder1$cmbAnoFim": ano,
            "ctl00$ContentPlaceHolder1$cmbCompetencia": competencia,
        })],
    )
    responses.add(responses.GET, RESULTS_PAGE_URL, body=b"", status=200)
    _add_xhr(0, "xhr_single_page.json")


@pytest.mark.parametrize(
    ("origem", "sample", "ano", "competencia"),
    [
        ("2", "postback_origem_alcada_civel.html", "1998", "1"),
        ("3", "postback_origem_alcada_criminal.html", "1998", "2"),
        ("5", "postback_origem_conselho_magistratura.html", "2026", "0"),
    ],
    ids=["alcada_civel", "alcada_criminal", "conselho_magistratura"],
)
@responses.activate
def test_cjsg_sem_ano_nem_competencia_usa_o_form_da_origem(mocker, origem, sample, ano, competencia):
    """Sem filtro, ano e competencia saem do form da origem, nao do form inicial.

    Os Tribunais de Alcada vao de 1975 a 1998, o de Alcada Criminal so tem a
    competencia ``"2"`` e o Conselho da Magistratura so a ``"0"``
    ("Selecione..."). Com o ano corrente e a competencia ``"1"`` do form
    inicial, o portal respondia HTTP 500. O XHR de resultados e o da 2a
    instancia: o teste confere o form da busca, nao o conteudo.
    """
    mocker.patch("time.sleep")
    _add_form_get()
    _add_postback_origem(origem, sample)
    _add_busca(origem, ano, competencia)

    df = jus.scraper("tjrj").cjsg("dano", origem=origem, paginas=1)

    assert len(df) > 0


@responses.activate
def test_cjsg_ano_vazio_vale_como_sem_filtro(mocker):
    """``ano_inicio=""`` segue o padrao do form, como antes da conferencia por origem."""
    mocker.patch("time.sleep")
    _add_form_get()
    _add_form_post("dano moral", ano_inicio="2026", ano_fim="2026")
    _add_xhr(0, "xhr_single_page.json")

    df = jus.scraper("tjrj").cjsg("dano moral", ano_inicio="", ano_fim="", paginas=1)

    assert len(df) > 0


@pytest.mark.parametrize(
    ("origem", "sample", "filtro", "mensagem"),
    [
        ("2", "postback_origem_alcada_civel.html", {"ano_inicio": 2020}, "ano_inicio='2020'.*1998"),
        ("2", "postback_origem_alcada_civel.html", {"ano_fim": 2020}, "ano_fim='2020'.*1998"),
        ("5", "postback_origem_conselho_magistratura.html", {"competencia": 1}, "competencia='1'.*opcoes: 0"),
    ],
    ids=["ano_inicio_fora_da_alcada", "ano_fim_fora_da_alcada", "competencia_no_conselho"],
)
@responses.activate
def test_cjsg_filtro_fora_do_form_da_origem_levanta_antes_da_busca(mocker, origem, sample, filtro, mensagem):
    """Ano ou competencia que o form da origem nao oferece: ``ValueError``, sem a busca (HTTP 500)."""
    mocker.patch("time.sleep")
    _add_form_get()
    _add_postback_origem(origem, sample)

    with pytest.raises(ValueError, match=mensagem):
        jus.scraper("tjrj").cjsg("dano", origem=origem, paginas=1, **filtro)

    assert len(responses.calls) == 2
