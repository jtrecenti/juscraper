"""HTTP-level helpers for the TJRJ jurisprudence search."""
from __future__ import annotations

import math
import re
import time
from urllib.parse import parse_qs, urlparse

from juscraper.core.http import RequestFn
from juscraper.utils.pagination import paginas_no_intervalo

FORM_URL = "https://www3.tjrj.jus.br/ejuris/ConsultarJurisprudencia.aspx"
RESULT_URL = (
    "https://www3.tjrj.jus.br/EJURIS/ProcessarConsJurisES.aspx"
    "/ExecutarConsultarJurisprudencia"
)
RESULTS_PER_PAGE = 10

_FIELD_PREFIX = "ctl00$ContentPlaceHolder1$"
_BLOCKED_WORDS_FIELD = f"{_FIELD_PREFIX}hfListaPalavrasBloqueadas"

_HIDDEN_RE = re.compile(
    r'<input[^>]*name="(?P<name>__VIEWSTATE|__VIEWSTATEGENERATOR|__EVENTVALIDATION'
    r'|ctl00\$ContentPlaceHolder1\$hfListaPalavrasBloqueadas)"[^>]*value="(?P<value>[^"]*)"',
    re.IGNORECASE,
)

_OPTION_RE = re.compile(r'<option[^>]*value="(?P<value>[^"]*)"', re.IGNORECASE)
_SELECTED_OPTION_RE = re.compile(
    r'<option[^>]*selected="selected"[^>]*value="(?P<value>[^"]*)"', re.IGNORECASE
)


def _select_block(html: str, campo: str) -> str | None:
    """Bloco ``<select name="...<campo>">...</select>`` do form, ou ``None``."""
    match = re.search(
        rf'<select[^>]*name="{re.escape(_FIELD_PREFIX + campo)}".*?</select>',
        html,
        re.IGNORECASE | re.DOTALL,
    )
    return match.group(0) if match else None


def extract_select_options(html: str, campo: str) -> list[str]:
    """Valores nao vazios das ``<option>`` do ``<select>`` ``campo``, na ordem da pagina.

    Devolve ``[]`` quando o ``<select>`` nao aparece, e o chamador nao valida
    contra uma lista que nao conseguiu ler.
    """
    block = _select_block(html, campo)
    if block is None:
        return []
    return [valor for valor in _OPTION_RE.findall(block) if valor.strip()]


def _selected_option(html: str, campo: str) -> str | None:
    """Valor da ``<option selected>`` do ``<select>`` ``campo``, ou ``None``."""
    block = _select_block(html, campo)
    match = _SELECTED_OPTION_RE.search(block) if block else None
    return match.group("value") if match else None


def extract_viewstate_fields(html: str) -> dict:
    """Extrai os quatro hidden fields exigidos pelo POST ASP.NET do TJRJ.

    Retorna ``__VIEWSTATE``, ``__VIEWSTATEGENERATOR``, ``__EVENTVALIDATION`` e
    ``ctl00$ContentPlaceHolder1$hfListaPalavrasBloqueadas``. Campos ausentes
    sao omitidos do dict — o caller substitui defaults explicitamente.

    O hidden de palavras bloqueadas carrega a stopword list do backend
    (``"A;ACIMA;COM;..."``); o servidor le esse valor de volta para validar o
    termo de busca, e um POST que omite o campo pode disparar 500 Runtime
    Error em janelas onde o backend espera o roundtrip (refs #143, exposto
    em 2026-04-30).
    """
    fields: dict = {}
    for match in _HIDDEN_RE.finditer(html):
        fields[match.group("name")] = match.group("value")
    return fields


def extract_default_year(html: str) -> str:
    r"""Devolve o ano-padrao do form — a primeira ``<option>`` de ``cmbAnoInicio``.

    O backend do TJRJ passou a exigir ``cmbAnoInicio``/``cmbAnoFim`` nao-vazios:
    um POST com ano em branco dispara ``HTTP 500`` ja na submissao do form
    (refs #278). Nenhuma ``<option>`` do dropdown vem marcada com ``selected``,
    entao o ``<select>`` do navegador submete a primeira opcao (a mais nova) —
    o ano corrente. Replicamos esse default em vez de usar ``date.today().year``
    porque o valor parseado e garantidamente uma opcao que o backend aceita
    (``date.today()`` poderia enviar um ano ainda ausente do dropdown na virada
    do ano e cair em erro de validacao).

    Fallback: se o ``<select>`` nao parsear (formato mudou), devolve o maior
    ``\\d{4}`` encontrado no bloco; em ultimo caso, o maior do HTML inteiro.
    Nunca devolve ``""`` — string vazia e exatamente o que provoca o 500.
    """
    values = extract_select_options(html, "cmbAnoInicio")
    if values:
        return values[0]
    block = _select_block(html, "cmbAnoInicio") or html
    anos = re.findall(r"\b(\d{4})\b", block) or re.findall(r"\b(\d{4})\b", html)
    return str(max(anos)) if anos else ""


def build_cjsg_payload(
    hidden: dict,
    pesquisa: str,
    *,
    ano_inicio: str = "",
    ano_fim: str = "",
    competencia: str = "1",
    origem: str = "1",
    tipo_acordao: bool = True,
    tipo_monocratica: bool = True,
    magistrado_codigo: str | None = None,
    orgao_codigo: str | None = None,
) -> dict:
    """Monta o body URL-encoded para o POST ASPX do TJRJ.

    ``hidden`` carrega os quatro hidden fields devolvidos por
    :func:`extract_viewstate_fields`. ``g-recaptcha-response`` fica vazio
    propositalmente — o widget e decorativo, o backend nao valida o token.
    """
    data = {
        "__EVENTTARGET": f"{_FIELD_PREFIX}btnPesquisar",
        "__EVENTARGUMENT": "",
        "__LASTFOCUS": "",
        "__VIEWSTATE": hidden.get("__VIEWSTATE", ""),
        "__VIEWSTATEGENERATOR": hidden.get("__VIEWSTATEGENERATOR", ""),
        "__EVENTVALIDATION": hidden.get("__EVENTVALIDATION", ""),
        _BLOCKED_WORDS_FIELD: hidden.get(_BLOCKED_WORDS_FIELD, ""),
        f"{_FIELD_PREFIX}hfCodRamos": "",
        f"{_FIELD_PREFIX}hfCodMags": magistrado_codigo or "",
        f"{_FIELD_PREFIX}hfCodOrgs": orgao_codigo or "",
        f"{_FIELD_PREFIX}txtTextoPesq": pesquisa,
        f"{_FIELD_PREFIX}cmbOrigem": origem,
        f"{_FIELD_PREFIX}cmbAnoInicio": ano_inicio,
        f"{_FIELD_PREFIX}cmbAnoFim": ano_fim,
        f"{_FIELD_PREFIX}cmbCompetencia": competencia,
        f"{_FIELD_PREFIX}cmbRamo": "",
        f"{_FIELD_PREFIX}cmbMagistrado": "",
        f"{_FIELD_PREFIX}chkAtivo": "on",
        f"{_FIELD_PREFIX}chkInativo": "on",
        f"{_FIELD_PREFIX}cmbOrgaoJulgador": "",
        f"{_FIELD_PREFIX}cmbTipNumeracao": "1",
        f"{_FIELD_PREFIX}txtNumeracao": "",
        # chkEmentario fica de fora. Marcado junto com os outros, o servidor
        # ignorava chkAcordao/chkDecMon desmarcados (tipo_acordao=False e
        # tipo_monocratica=False sem efeito); depois do postback de origem,
        # trocava a busca para o ementario e desmarcava acordao e monocratica.
        f"{_FIELD_PREFIX}chkIntTeor": "on",
        "g-recaptcha-response": "",
    }
    if tipo_acordao:
        data[f"{_FIELD_PREFIX}chkAcordao"] = "on"
    if tipo_monocratica:
        data[f"{_FIELD_PREFIX}chkDecMon"] = "on"
    return data


def _valor_do_form(html: str, campo: str, nome: str, valor: str | None, origem: str, fallback: str) -> str:
    """Devolve o valor de ``campo`` para a busca, conferido contra o ``<select>`` do form.

    Vazio vira o padrao do navegador: a opcao marcada ou, sem ela, a primeira
    (``fallback`` se o ``<select>`` nao parsear). O servidor responde HTTP 500
    a um valor que o combo da origem nao oferece; o erro sai aqui, antes da
    busca, com as opcoes da origem.
    """
    opcoes = extract_select_options(html, campo)
    if not valor:
        return _selected_option(html, campo) or (opcoes[0] if opcoes else fallback)
    if opcoes and valor not in opcoes:
        raise ValueError(
            f"TJRJ: {nome}={valor!r} nao existe no formulario da origem {origem!r}; "
            f"opcoes: {', '.join(opcoes)}."
        )
    return valor


def _init_session(
    request_fn: RequestFn,
    pesquisa: str,
    ano_inicio: str | None,
    ano_fim: str | None,
    competencia: str | None,
    origem: str,
    tipo_acordao: bool,
    tipo_monocratica: bool,
    magistrado_codigo: str | None,
    orgao_codigo: str | None,
) -> str:
    """Submete o form de busca e devolve o ``PageSeq`` que o servidor deu a ela.

    O servidor numera as buscas de uma mesma sessao ASP.NET (0, 1, 2...) e
    guarda os parametros de cada uma em separado; o XHR de resultados escolhe
    a busca pelo ``pageSeq``. O numero vem na URL do redirect do POST.

    ``ano_inicio``, ``ano_fim`` e ``competencia`` vazios ficam com o padrao do
    form da origem, como no navegador: a opcao marcada do combo ou, sem ela, a
    primeira. A excecao e ``ano_inicio`` vazio com ``ano_fim`` preenchido, que
    vira o ano mais antigo da origem. Valor que o combo da origem nao oferece
    levanta ``ValueError``.
    """
    resp = request_fn("GET", FORM_URL, perfil="formulario")
    html = resp.text
    # Anos e competencia aqui sao os padroes do form inicial e so alimentam o
    # postback de origem; os da busca saem do form da origem, mais abaixo. O
    # backend exige anos nao-vazios (refs #278).
    default_year = extract_default_year(html)
    data = build_cjsg_payload(
        hidden=extract_viewstate_fields(html),
        pesquisa=pesquisa,
        ano_inicio=default_year,
        ano_fim=default_year,
        origem=origem,
        tipo_acordao=tipo_acordao,
        tipo_monocratica=tipo_monocratica,
        magistrado_codigo=magistrado_codigo,
        orgao_codigo=orgao_codigo,
    )
    if _selected_option(html, "cmbOrigem") != origem:
        # Trocar a origem no mesmo POST da busca dispara o evento de troca de
        # cmbOrigem no servidor, que recarrega os combos de ano no padrao (ano
        # corrente) depois de ler os anos enviados: o filtro de ano se perdia
        # sem erro. O navegador faz este postback ao mudar o combo; a busca
        # vai em seguida com o estado devolvido por ele. O postback leva os
        # anos e a competencia padrao do form inicial: a ``"3"`` (Fazendaria),
        # por exemplo, so existe depois que a Turma Recursal carrega.
        postback = dict(data, __EVENTTARGET=f"{_FIELD_PREFIX}cmbOrigem")
        html = request_fn("POST", FORM_URL, data=postback, perfil="formulario").text
        data.update(extract_viewstate_fields(html))
    # Cada origem tem seus combos: os Tribunais de Alcada vao de 1975 a 1998,
    # o de Alcada Criminal so tem a competencia "2" e o Conselho da
    # Magistratura so a "0" (15/11/2026). Fora deles, o servidor responde 500.
    default_year = extract_default_year(html)
    if ano_fim and not ano_inicio:
        # So o fim: o inicio vira o ano mais antigo da origem. O padrao do
        # combo (o mais recente) invertia o intervalo, e o portal devolvia 0
        # documentos.
        ano_inicio = min(extract_select_options(html, "cmbAnoInicio"), default=None)
    for campo, nome, valor, fallback in (
        ("cmbAnoInicio", "ano_inicio", ano_inicio, default_year),
        ("cmbAnoFim", "ano_fim", ano_fim, default_year),
        ("cmbCompetencia", "competencia", competencia, "1"),
    ):
        data[_FIELD_PREFIX + campo] = _valor_do_form(html, campo, nome, valor, origem, fallback)
    resp = request_fn("POST", FORM_URL, data=data, allow_redirects=True, perfil="formulario")
    page_seq = parse_qs(urlparse(resp.url).query).get("PageSeq")
    if not page_seq:
        raise RuntimeError(
            "TJRJ: o form de busca nao redirecionou para os resultados "
            f"(URL final: {resp.url}); a busca nao foi registrada no servidor."
        )
    return page_seq[0]


def _fetch_page(request_fn: RequestFn, num_pagina_0: int, page_seq: str) -> dict:
    payload = {"numPagina": num_pagina_0, "pageSeq": page_seq}
    resp = request_fn(
        "POST",
        RESULT_URL,
        json=payload,
        headers={
            "Content-Type": "application/json; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        },
        perfil="cjsg",
    )
    resp.encoding = "utf-8"
    data: dict = resp.json().get("d", {})
    return data


def cjsg_download(
    pesquisa: str,
    paginas,
    *,
    request_fn: RequestFn,
    ano_inicio: str | None,
    ano_fim: str | None,
    competencia: str | None,
    origem: str,
    tipo_acordao: bool,
    tipo_monocratica: bool,
    magistrado_codigo: str | None,
    orgao_codigo: str | None,
    sleep_time: float,
) -> list:
    """Run a TJRJ search and return the raw JSON page payloads.

    Args:
        request_fn: HTTP callable que aplica retry + ``raise_for_status``.
            Em uso normal e ``TJRJScraper._request_with_retry`` (via
            ``core.http.HTTPScraper``).
    """
    page_seq = _init_session(
        request_fn=request_fn,
        pesquisa=pesquisa,
        ano_inicio=ano_inicio,
        ano_fim=ano_fim,
        competencia=competencia,
        origem=origem,
        tipo_acordao=tipo_acordao,
        tipo_monocratica=tipo_monocratica,
        magistrado_codigo=magistrado_codigo,
        orgao_codigo=orgao_codigo,
    )
    first = _fetch_page(request_fn, 0, page_seq)
    total = int(first.get("TotalDocs") or 0)
    n_pags = max(1, math.ceil(total / RESULTS_PER_PAGE)) if total else 1

    results: list = []
    for pagina in paginas_no_intervalo(paginas, n_pags, tribunal="TJRJ"):
        if pagina == 1:
            results.append(first)
            continue
        time.sleep(sleep_time)
        data = _fetch_page(request_fn, pagina - 1, page_seq)
        results.append(data)
    return results
