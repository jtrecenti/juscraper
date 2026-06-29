"""Downloads raw results from the TJRR jurisprudence search (JSF/PrimeFaces)."""
import re
import time
import unicodedata

from bs4 import BeautifulSoup
from tqdm import tqdm

from juscraper.core.http import RequestFn
from juscraper.utils.pagination import extract_count_with_cascade

BASE_URL = "https://jurisprudencia.tjrr.jus.br/index.xhtml"
RESULTS_PER_PAGE = 10


def _extract_cdata(xml_text: str) -> str:
    """Extract HTML content from a PrimeFaces AJAX XML response."""
    if not xml_text.startswith("<?xml"):
        return xml_text
    cdata_matches: list[str] = re.findall(r"<!\[CDATA\[(.*?)\]\]>", xml_text, re.DOTALL)
    for cdata in cdata_matches:
        if "resultados" in cdata:
            return cdata
    # If no match with 'resultados', return the largest CDATA block
    if cdata_matches:
        return max(cdata_matches, key=len)
    return xml_text


def _collect_form_defaults(soup: BeautifulSoup, form_id: str = "menuinicial") -> dict:
    """Collect every default field on a JSF form (selected by ``form_id``).

    A browser submit includes every form input (with its default value),
    including hidden panel-collapsed flags like
    ``menuinicial:j_idt44_collapsed=true`` and ``menuinicial:tipoClasseList=0``.
    Dropping them makes the backend return zero results when searching
    with an empty ``pesquisa`` — the empty-term path only works when the
    full form context is preserved.

    Used for two forms: ``menuinicial`` (the initial search POST) and
    ``formPesquisa`` (the results page, whose full context the AJAX
    pagination POST must echo back — see :func:`_paginate`). Fields are
    matched by name prefix, which equals ``form_id`` for both forms.
    """
    defaults: dict[str, list] = {}
    form = soup.find("form", {"id": form_id}) or soup
    for tag in form.find_all(["input", "select", "textarea"]):
        name = tag.get("name")
        if not name or not name.startswith(form_id):
            continue
        ttype = (tag.get("type") or "").lower()
        if ttype in ("submit", "button", "image", "reset"):
            continue
        if ttype in ("checkbox", "radio"):
            if not tag.has_attr("checked"):
                continue
            value = tag.get("value", "on")
        elif tag.name == "select":
            opt = tag.find("option", selected=True) or tag.find("option")
            value = opt.get("value", "") if opt else ""
        else:
            value = tag.get("value", "")
        defaults.setdefault(name, []).append(value)
    # Collapse single-value lists to scalars so urlencode emits one
    # entry per field (matches what a browser POST produces).
    return {k: (v[0] if len(v) == 1 else v) for k, v in defaults.items()}


_RELATOR_NOME_RE = re.compile(r"nomeRegimental:(.+?)\)\s*$")


def _collect_relator_map(soup: BeautifulSoup) -> dict[str, str]:
    """Map each magistrado's ``nomeRegimental`` to its opaque form value.

    O backend TJRR expoe o filtro de relator como um PrimeFaces
    ``SelectManyCheckbox`` (``menuinicial:relatorList``). Cada option
    tem como ``value`` um entity bean Java serializado, por exemplo::

        br.jus.tjrr.bpu.domain.model.MagistradoBPU(matricula:3010559, nomeRegimental:ALMIRO PADILHA)

    Para a API publica aceitar o nome regimental ("ALMIRO PADILHA") em
    vez do bean opaco, parseamos o GET inicial (ja baixado para
    descoberta de ViewState) e entregamos o mapa para ``_search`` via
    ``form_fields["relator_map"]``.
    """
    mapping: dict[str, str] = {}
    for tag in soup.find_all("input", {"name": "menuinicial:relatorList"}):
        value = tag.get("value") or ""
        match = _RELATOR_NOME_RE.search(value)
        if match:
            mapping[match.group(1).strip()] = value
    return mapping


def _get_form_fields(request_fn: RequestFn) -> dict:
    """Fetch the initial page and discover JSF field names and defaults.

    JSF auto-generates component IDs like ``menuinicial:j_idt28`` that
    shift whenever components are added or reordered server-side. We
    look dynamic fields up by their stable attributes
    (``id=consultaAtual`` for the search input) and snapshot every form
    default so the POST matches what a browser would send.
    """
    resp = request_fn("GET", BASE_URL, timeout=30)
    soup = BeautifulSoup(resp.text, "html.parser")
    vs_input = soup.find("input", {"name": "javax.faces.ViewState"})
    if not vs_input:
        raise RuntimeError("Could not find ViewState on TJRR page.")
    pesq = soup.find(id="consultaAtual")
    if not pesq or not pesq.get("name"):
        raise RuntimeError("Could not find TJRR pesquisa input (id=consultaAtual).")
    submit_name = None
    for btn in soup.find_all("button"):
        name = btn.get("name", "") or ""
        if name.startswith("menuinicial:j_idt") and not name.startswith("menuinicial:btn_"):
            submit_name = name
            break
    return {
        "viewstate": str(vs_input["value"]),
        "pesquisa_name": pesq["name"],
        "submit_name": submit_name,
        "defaults": _collect_form_defaults(soup),
        "relator_map": _collect_relator_map(soup),
    }


def _norm_relator_key(s: str) -> str:
    """Normaliza nome regimental para lookup: tira diacriticos e baixa caixa.

    NFD separa cada caractere acentuado em base + combining mark
    (``"Á"`` -> ``"A" + U+0301``); o filtro descarta os marks. Depois
    ``casefold()`` baixa a caixa de forma agressiva (mais correta que
    ``lower()`` em casos como ``"ß"``). Continua sendo igualdade exata —
    nao habilita substring ou fuzzy.
    """
    nfd = unicodedata.normalize("NFD", s)
    no_diacritics = "".join(c for c in nfd if not unicodedata.combining(c))
    return no_diacritics.casefold()


def _resolve_relator_values(
    relator: list[str], relator_map: dict[str, str]
) -> list[str]:
    """Resolve regimental names to the opaque bean values expected by the form.

    Match e exato apos normalizacao ``_norm_relator_key`` — o usuario pode
    digitar ``"cristovao suter"``, ``"Cristóvão Suter"`` ou
    ``"CRISTÓVÃO SUTER"`` e bate com o mesmo magistrado. Continua sendo
    igualdade (nao fuzzy/substring), entao nao ha risco de bater dois
    nomes pelo primeiro componente. ``ValueError`` lista os nomes
    **canonicos** (UPPERCASE com acento) para o usuario corrigir.
    """
    normalized_lookup = {
        _norm_relator_key(name): value for name, value in relator_map.items()
    }
    resolved: list[str] = []
    unknown: list[str] = []
    for name in relator:
        opaque = normalized_lookup.get(_norm_relator_key(name))
        if opaque is None:
            unknown.append(name)
        else:
            resolved.append(opaque)
    if unknown:
        available = ", ".join(sorted(relator_map)) or "(nenhum encontrado no form)"
        raise ValueError(
            f"Relator(es) desconhecido(s) no TJRR: {unknown}. "
            f"Nomes disponiveis (nomeRegimental): {available}."
        )
    return resolved


def _search(
    request_fn: RequestFn,
    form_fields: dict,
    pesquisa: str,
    relator: list[str] | None = None,
    data_inicio: str = "",
    data_fim: str = "",
    orgao_julgador: list | None = None,
    especie: list | None = None,
) -> str:
    """Submit the search form and return the HTML response."""
    data: dict = dict(form_fields.get("defaults", {}))
    data["menuinicial"] = "menuinicial"
    data[form_fields["pesquisa_name"]] = pesquisa
    data["menuinicial:numProcesso"] = ""
    data["menuinicial:datainicial_input"] = data_inicio
    data["menuinicial:datafinal_input"] = data_fim
    data["javax.faces.ViewState"] = form_fields["viewstate"]
    if form_fields.get("submit_name"):
        data[form_fields["submit_name"]] = ""
    if orgao_julgador:
        data["menuinicial:tipoOrgaoList"] = list(orgao_julgador)
    if especie:
        data["menuinicial:tipoEspecieList"] = list(especie)
    if relator:
        data["menuinicial:relatorList"] = _resolve_relator_values(
            list(relator), form_fields.get("relator_map", {})
        )

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://jurisprudencia.tjrr.jus.br",
        "Referer": "https://jurisprudencia.tjrr.jus.br/",
    }
    resp = request_fn("POST", BASE_URL, data=data, headers=headers, timeout=60)
    resp.encoding = "utf-8"
    return resp.text


_PAGINATION_CSS_SELECTORS: tuple[str, ...] = ("span.ui-paginator-current",)
_PAGINATION_REGEXES: tuple[re.Pattern[str], ...] = (
    re.compile(r"of\s+(\d+)\)", re.IGNORECASE),
    re.compile(r"de\s+(\d+)\)", re.IGNORECASE),
)


def _get_total_pages(html: str) -> int:
    """Extract total pages from the PrimeFaces paginator."""
    n = extract_count_with_cascade(
        html,
        css_selectors=_PAGINATION_CSS_SELECTORS,
        regex_patterns=_PAGINATION_REGEXES,
        fallback_max_int=False,
    )
    return n if n is not None else 1


# JSF auto-generates the numeric segment of the results datatable id
# (``formPesquisa:j_idtNNN:dataTablePesquisa``) and it shifts whenever the
# page's component tree changes server-side (observed drift j_idt159 -> j_idt158
# in 2026-06). Hardcoding it silently breaks pagination: the AJAX POST targets a
# component that no longer exists and the backend replies with an opaque,
# unparseable partial-response, so every page past the first yields zero rows.
# Discover it from the rendered results page instead. Tried in cascade per the
# project rule for tribunal-page extraction (see CLAUDE.md). The ``(?!\w)``
# lookahead stops the match before ``dataTablePesquisa2`` (the second, distinct
# results table) and ``dataTablePesquisa_data`` (the tbody), pinning the base id.
_DATATABLE_ID_SELECTORS: tuple[re.Pattern[str], ...] = (
    re.compile(r'id="(formPesquisa:j_idt\d+:dataTablePesquisa)(?!\w)'),
    re.compile(r"(formPesquisa:j_idt\d+:dataTablePesquisa)(?!\w)"),
    re.compile(r"(formPesquisa:[\w-]+:dataTablePesquisa)(?!\w)"),
)


def _extract_datatable_id(html: str) -> str:
    """Discover the JSF id of the results datatable from the rendered page.

    Cascade of selectors (most specific first) so a change in how the id is
    surfaced does not silently fall back to a stale hardcoded value.
    """
    for pattern in _DATATABLE_ID_SELECTORS:
        match = pattern.search(html)
        if match:
            return match.group(1)
    raise RuntimeError(
        "Could not find the results datatable id "
        "(formPesquisa:j_idtNNN:dataTablePesquisa) on the TJRR results page."
    )


def _paginate(
    request_fn: RequestFn,
    html: str,
    page: int,
) -> str:
    """Navigate to a specific page via PrimeFaces AJAX pagination.

    Replicates a browser's "next page" POST faithfully. A minimal payload
    (datatable params + ViewState only) is silently ignored by the TJRR
    backend, which keeps returning page 1 — verified live (issue #287,
    layer 2). The backend honours the ``_first`` offset only when the POST
    carries the *full* ``formPesquisa`` form context (notably
    ``consultaAtual``, the search term), the PrimeFaces ``page`` behavior
    event, the datatable feature flags (``_skipChildren``/``_encodeFeature``)
    and the ``Faces-Request: partial/ajax`` header — exactly what the
    browser sends.

    ``_first`` is an absolute offset and the TJRR ViewState is reusable, so
    each page is fetched independently from the page-1 ``html`` — no need to
    thread the ViewState returned by each partial-response.

    Only ``dataTablePesquisa`` (acórdãos) is paginated. The results page
    also renders ``dataTablePesquisa2`` (decisões monocráticas) with its own
    paginator; those rows are captured from page 1 only. Paginating the
    second table is tracked as a follow-up to issue #287.
    """
    soup = BeautifulSoup(html, "html.parser")
    vs_input = soup.find("input", {"name": "javax.faces.ViewState"})
    if not vs_input:
        raise RuntimeError("Could not find ViewState for pagination.")

    viewstate = vs_input["value"]
    datatable_id = _extract_datatable_id(html)
    rows = RESULTS_PER_PAGE
    first = (page - 1) * rows

    # Echo the whole results form, then overlay the AJAX pagination params.
    data = _collect_form_defaults(soup, form_id="formPesquisa")
    data.update({
        "javax.faces.partial.ajax": "true",
        "javax.faces.source": datatable_id,
        "javax.faces.partial.execute": datatable_id,
        "javax.faces.partial.render": datatable_id,
        "javax.faces.behavior.event": "page",
        "javax.faces.partial.event": "page",
        f"{datatable_id}_pagination": "true",
        f"{datatable_id}_first": str(first),
        f"{datatable_id}_rows": str(rows),
        f"{datatable_id}_skipChildren": "true",
        f"{datatable_id}_encodeFeature": "true",
        "formPesquisa": "formPesquisa",
        "javax.faces.ViewState": viewstate,
    })

    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Faces-Request": "partial/ajax",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/xml, text/xml, */*; q=0.01",
        "Origin": "https://jurisprudencia.tjrr.jus.br",
        "Referer": "https://jurisprudencia.tjrr.jus.br/",
    }
    resp = request_fn("POST", BASE_URL, data=data, headers=headers, timeout=60)
    resp.encoding = "utf-8"
    return _extract_cdata(resp.text)


def cjsg_download_manager(
    pesquisa: str,
    paginas=None,
    *,
    request_fn: RequestFn,
    sleep_time: float = 1.0,
    **kwargs,
) -> list:
    """Download raw HTML results from the TJRR jurisprudence search.

    Returns a list of raw HTML strings (one per page).

    Args:
        pesquisa: Search term.
        paginas (list, range, or None): Pages to download (1-based).
        request_fn: HTTP callable que faz retry + raise_for_status — em uso
            normal e ``TJRRScraper._request_with_retry`` (via
            ``core.http.HTTPScraper``), centralizando backoff para 429/5xx.
        sleep_time: Delay (em segundos) entre páginas. Default 1.0; o client
            normalmente passa ``self.sleep_time`` herdado de ``HTTPScraper``.
        **kwargs: Additional filter parameters.
    """
    form_fields = _get_form_fields(request_fn)
    first_html = _search(request_fn, form_fields, pesquisa, **kwargs)

    if paginas is None:
        resultados = [first_html]
        n_pags = _get_total_pages(first_html)
        if n_pags > 1:
            for pagina in tqdm(range(2, n_pags + 1), desc="Baixando CJSG TJRR"):
                time.sleep(sleep_time)
                html = _paginate(request_fn, first_html, pagina)
                resultados.append(html)
        return resultados

    paginas_iter = list(paginas)
    resultados = []
    for pagina_1based in tqdm(paginas_iter, desc="Baixando CJSG TJRR"):
        if pagina_1based == 1:
            resultados.append(first_html)
        else:
            time.sleep(sleep_time)
            html = _paginate(request_fn, first_html, pagina_1based)
            resultados.append(html)
    return resultados
