"""
Functions for parsing specific to TJPR
"""
import pandas as pd
from bs4 import BeautifulSoup
from bs4.element import Tag

from juscraper.core.failures import FALHAS_DE_TRANSPORTE
from juscraper.core.http import RequestFn
from juscraper.core.parse_utils import coerce_date_columns

from .download import TJPREmentaIndisponivelError, get_ementa_completa

_FALHAS_DA_EMENTA: tuple[type[Exception], ...] = (*FALHAS_DE_TRANSPORTE, TJPREmentaIndisponivelError)


def _extract_processo(dados_td: Tag) -> str:
    processo_a = dados_td.find("a", class_="decisao negrito")
    if processo_a:
        return str(processo_a.get_text(strip=True))

    processo = ""
    for div in dados_td.find_all("div"):
        if "Processo:" not in div.get_text():
            continue
        processo_div = div.find_all("div")
        if processo_div:
            processo = str(processo_div[0].get_text(strip=True))
    return processo


def _extract_labeled_value(
    dados_td: Tag,
    label: str,
    *,
    use_text_sibling: bool = False,
) -> str:
    label_text = dados_td.find(string=lambda text: text and label in text)
    if not label_text:
        return ""

    value = str(label_text).split(label)[-1].strip()
    if value or not use_text_sibling or label_text.parent is None:
        return value

    sibling = label_text.parent.find_next_sibling(string=True)
    return str(sibling).strip() if sibling else ""


def _extract_ementa(
    ementa_td: Tag,
    id_registro: str,
    criterio: str | None,
    request_fn: RequestFn | None,
    action_type: str = "exibirTextoCompleto",
) -> str:
    """Ementa da linha, completa quando o portal a trunca em "Leia mais..".

    O texto sai do ``div#ementa<id>``, sem o link "Leia mais..", sem a nota "A
    expressão foi encontrada..." do TJ e sem a autoria das ementas da Corte
    IDH, e sem separador entre os nós: o destaque do termo buscado pode cair no
    meio da palavra ("<span>DANO</span>S MORAIS"). Sem ``request_fn`` a ementa
    fica truncada; o ``criterio`` vazio não impede a busca da completa.
    """
    truncada = "leia mais" in ementa_td.get_text().lower()
    ementa_el = ementa_td.find("div", id=f"ementa{id_registro}") or ementa_td
    # Na Corte IDH o link fica dentro do ``div#ementa<id>``; no TJ, fora.
    for link in ementa_el.find_all("a"):
        link.decompose()
    ementa = str(ementa_el.get_text()).strip()
    if not truncada or not id_registro or request_fn is None:
        return ementa

    try:
        return get_ementa_completa(request_fn, action_type, id_registro, criterio or "")
    except _FALHAS_DA_EMENTA as error:
        # A falha de uma ementa completa não invalida os demais resultados da página.
        return f"{ementa}\n[Erro ao buscar ementa completa: {error}]"


def _input_value(td: Tag, name: str) -> str:
    field = td.find("input", {"name": name})
    return str(field["value"]) if field and "value" in field.attrs else ""


def _parse_row_corte_idh(
    id_caso: str,
    dados_td: Tag,
    ementa_td: Tag,
    criterio: str | None,
    request_fn: RequestFn | None,
) -> dict[str, str | None]:
    """Linha da Corte IDH: sem processo, órgão nem relator, que o portal não tem.

    Chaves na ordem da linha do TJ.
    """
    caso_a = dados_td.find("a", class_="cidh-text")
    caso = caso_a.get_text(strip=True).removeprefix("Caso:").strip() if caso_a else ""
    return {
        "processo": None,
        "orgao_julgador": None,
        "relator": None,
        "data_julgamento": _extract_labeled_value(dados_td, "Data Julgamento:"),
        "ementa": _extract_ementa(ementa_td, id_caso, criterio, request_fn, "exibirTextoCompletoCidh"),
        "fonte": "Corte IDH",
        "caso": caso,
    }


def _parse_row(
    row: Tag,
    criterio: str | None,
    request_fn: RequestFn | None,
    *,
    incluir_corte_idh: bool = False,
) -> dict[str, str | None] | None:
    # O portal mistura precedentes da Corte IDH na tabela de jurisprudência
    # (ver a divisão das 50 linhas em ``download.py``).
    corte_idh = row.find("input", {"name": "idsSelecionadosCidh"})
    if corte_idh and not incluir_corte_idh:
        return None

    cols = row.find_all("td")
    if len(cols) < 2:
        return None

    dados_td, ementa_td = cols[:2]
    if corte_idh:
        id_caso = str(corte_idh.get("value", ""))
        return _parse_row_corte_idh(id_caso, dados_td, ementa_td, criterio, request_fn)

    resultado: dict[str, str | None] = {
        "processo": _extract_processo(dados_td),
        "orgao_julgador": _extract_labeled_value(dados_td, "Órgão Julgador:"),
        "relator": _extract_labeled_value(dados_td, "Relator:", use_text_sibling=True),
        "data_julgamento": _extract_labeled_value(dados_td, "Data Julgamento:", use_text_sibling=True),
        "ementa": _extract_ementa(
            ementa_td, _input_value(dados_td, "idsSelecionados"), criterio, request_fn
        ),
    }
    if incluir_corte_idh:
        resultado["fonte"] = "TJPR"
        resultado["caso"] = None
    return resultado


def cjsg_parse(
    htmls,
    criterio=None,
    *,
    request_fn: RequestFn | None = None,
    incluir_corte_idh: bool = False,
):
    """
    Extracts relevant data from the HTMLs returned by TJPR.
    Returns a DataFrame with the decisions.

    ``request_fn`` busca a ementa completa das linhas truncadas em "Leia
    mais..", com ou sem ``criterio``. Sem ele a ementa fica truncada, o que
    serve ao parse offline de páginas já baixadas.

    ``incluir_corte_idh``: ver :meth:`TJPRScraper.cjsg`.
    """
    resultados = []
    for html in htmls:
        soup = BeautifulSoup(html, "html.parser")
        tabela = soup.select_one("table.resultTable.jurisprudencia")
        if not tabela:
            continue
        for row in tabela.find_all("tr")[1:]:  # pula o cabeçalho
            result = _parse_row(row, criterio, request_fn, incluir_corte_idh=incluir_corte_idh)
            if result is not None:
                resultados.append(result)
    df = pd.DataFrame(resultados)
    coerce_date_columns(df, ["data_julgamento"], date_format="%d/%m/%Y")
    return df
