"""Downloads raw results from the TJRR jurisprudence search (JSF/PrimeFaces)."""
import logging
import re
import time

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

logger = logging.getLogger(__name__)

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


def _collect_form_defaults(soup: BeautifulSoup) -> dict:
    """Collect every default field on the ``menuinicial`` form.

    A browser submit includes every form input (with its default value),
    including hidden panel-collapsed flags like
    ``menuinicial:j_idt44_collapsed=true`` and ``menuinicial:tipoClasseList=0``.
    Dropping them makes the backend return zero results when searching
    with an empty ``pesquisa`` — the empty-term path only works when the
    full form context is preserved.
    """
    defaults: dict[str, list] = {}
    form = soup.find("form", {"id": "menuinicial"}) or soup
    for tag in form.find_all(["input", "select", "textarea"]):
        name = tag.get("name")
        if not name or not name.startswith("menuinicial"):
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


def _get_form_fields(session: requests.Session) -> dict:
    """Fetch the initial page and discover JSF field names and defaults.

    JSF auto-generates component IDs like ``menuinicial:j_idt28`` that
    shift whenever components are added or reordered server-side. We
    look dynamic fields up by their stable attributes
    (``id=consultaAtual`` for the search input) and snapshot every form
    default so the POST matches what a browser would send.
    """
    resp = session.get(BASE_URL, timeout=30)
    resp.raise_for_status()
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
    }


def _search(
    session: requests.Session,
    form_fields: dict,
    pesquisa: str,
    relator: str = "",  # noqa: ARG001 - accepted for API compat; no longer a text input in TJRR
    data_inicio: str = "",
    data_fim: str = "",
    orgao_julgador: list | None = None,
    especie: list | None = None,
    max_retries: int = 3,
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

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://jurisprudencia.tjrr.jus.br",
        "Referer": "https://jurisprudencia.tjrr.jus.br/",
    }
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.post(BASE_URL, data=data, headers=headers, timeout=60)
            resp.raise_for_status()
            resp.encoding = "utf-8"
            return resp.text
        except requests.RequestException as exc:
            if attempt == max_retries:
                raise
            wait = 2 ** attempt
            logger.warning(
                "TJRR request failed (attempt %d/%d): %s. Retrying in %ds...",
                attempt, max_retries, exc, wait,
            )
            time.sleep(wait)
    return ""  # unreachable


def _get_total_pages(html: str) -> int:
    """Extract total pages from the PrimeFaces paginator."""
    match = re.search(r"\((\d+) of (\d+)\)", html)
    if match:
        return int(match.group(2))
    return 1


def _paginate(
    session: requests.Session,
    html: str,
    page: int,
    max_retries: int = 3,
) -> str:
    """Navigate to a specific page using PrimeFaces AJAX pagination."""
    soup = BeautifulSoup(html, "html.parser")
    vs_input = soup.find("input", {"name": "javax.faces.ViewState"})
    if not vs_input:
        raise RuntimeError("Could not find ViewState for pagination.")

    viewstate = vs_input["value"]
    rows = RESULTS_PER_PAGE
    first = (page - 1) * rows

    data = {
        "javax.faces.partial.ajax": "true",
        "javax.faces.source": "formPesquisa:j_idt159:dataTablePesquisa",
        "javax.faces.partial.execute": "formPesquisa:j_idt159:dataTablePesquisa",
        "javax.faces.partial.render": "formPesquisa:j_idt159:dataTablePesquisa",
        "formPesquisa:j_idt159:dataTablePesquisa_pagination": "true",
        "formPesquisa:j_idt159:dataTablePesquisa_first": str(first),
        "formPesquisa:j_idt159:dataTablePesquisa_rows": str(rows),
        "formPesquisa": "formPesquisa",
        "javax.faces.ViewState": viewstate,
    }

    for attempt in range(1, max_retries + 1):
        try:
            resp = session.post(BASE_URL, data=data, timeout=60)
            resp.raise_for_status()
            resp.encoding = "utf-8"
            return _extract_cdata(resp.text)
        except requests.RequestException as exc:
            if attempt == max_retries:
                raise
            wait = 2 ** attempt
            logger.warning(
                "TJRR pagination failed (attempt %d/%d): %s. Retrying in %ds...",
                attempt, max_retries, exc, wait,
            )
            time.sleep(wait)
    return ""  # unreachable


def cjsg_download_manager(
    pesquisa: str,
    paginas=None,
    session: requests.Session | None = None,
    **kwargs,
) -> list:
    """Download raw HTML results from the TJRR jurisprudence search.

    Returns a list of raw HTML strings (one per page).

    Args:
        pesquisa: Search term.
        paginas (list, range, or None): Pages to download (1-based).
        session: Optional requests.Session to reuse.
        **kwargs: Additional filter parameters.
    """
    if session is None:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
        })

    form_fields = _get_form_fields(session)
    first_html = _search(session, form_fields, pesquisa, **kwargs)
    time.sleep(1)

    if paginas is None:
        resultados = [first_html]
        n_pags = _get_total_pages(first_html)
        if n_pags > 1:
            for pagina in tqdm(range(2, n_pags + 1), desc="Baixando CJSG TJRR"):
                html = _paginate(session, first_html, pagina)
                resultados.append(html)
                time.sleep(1)
        return resultados

    paginas_iter = list(paginas)
    resultados = []
    for pagina_1based in tqdm(paginas_iter, desc="Baixando CJSG TJRR"):
        if pagina_1based == 1:
            resultados.append(first_html)
        else:
            html = _paginate(session, first_html, pagina_1based)
            resultados.append(html)
            time.sleep(1)
    return resultados
