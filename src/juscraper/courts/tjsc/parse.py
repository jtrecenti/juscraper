"""Parse raw HTML results from the TJSC jurisprudence search (eproc)."""
from collections.abc import Iterator

import pandas as pd
from bs4 import BeautifulSoup
from bs4.element import Tag

from juscraper.core.avisos import avisar
from juscraper.utils.cnj import format_cnj

_FIELD_MAP = {
    "PROCESSO": "processo",
    "UF": "uf",
    "ORGAO JULGADOR": "orgao_julgador",
    "DATA DO JULGAMENTO": "data_julgamento",
    "DATA DA PUBLICACAO": "data_publicacao",
    "RELATOR": "relator",
    "RELATORA": "relator",
    "EMENTA": "ementa",
    "DECISAO": "decisao",
}

_LABEL_REPLACEMENTS = str.maketrans({
    "Ã": "A",
    "Õ": "O",
    "Ó": "O",
    "Ç": "C",
    "É": "E",
    "Á": "A",
})


def _normalize_label(label: str) -> str:
    """Normalize only the accented characters historically accepted by TJSC."""
    return label.translate(_LABEL_REPLACEMENTS)


def _resolve_field(label: str) -> str | None:
    """Resolve exact and partial labels after normalizing accents."""
    normalized_label = _normalize_label(label)
    direct_match = _FIELD_MAP.get(normalized_label)
    if direct_match:
        return direct_match

    for field_label, field_key in _FIELD_MAP.items():
        if field_label in normalized_label:
            return field_key
    return None


def _extract_class(value: Tag) -> str | None:
    """Classe do campo PROCESSO, lida do ``<span>`` da segunda coluna do ``div.row``.

    O ``<span>`` traz ``<código> - <classe>`` (``ApCiv - Apelação``, ``HC TR -
    Habeas Corpus Criminal TR``, ``422070 - Recurso Administrativo``). A classe é
    o texto depois do primeiro `` - ``, como o portal a escreve, ou o texto
    inteiro sem `` - ``. Sem a segunda coluna ou sem o ``<span>``, não há classe.
    """
    linha = value.find("div", class_="row")
    colunas = linha.find_all("div", recursive=False) if linha else []
    span = colunas[1].find("span") if len(colunas) > 1 else None
    if span is None:
        return None
    texto = " ".join(span.get_text(" ").split())
    return texto.partition(" - ")[2] or texto or None


def _raw_process_number(value) -> str | None:
    """Return the process number without the ``/TJSC`` suffix, or ``None``.

    O número costuma vir no link ``a.numero-processo``. Alguns registros (acórdãos
    do Conselho da Magistratura, por exemplo) trazem só o texto ``<número>/TJSC``,
    sem link. Tirar o sufixo antes de formatar vale também para números antigos
    fora do padrão CNJ, que format_cnj devolve crus.
    """
    link = value.find("a", class_="numero-processo")
    if link:
        return str(link.get_text(strip=True)).removesuffix("/TJSC")
    for text in value.stripped_strings:
        if text.endswith("/TJSC"):
            return str(text).removesuffix("/TJSC")
    return None


def _extract_process_fields(value) -> dict[str, str]:
    """Extract the linked process number and the adjacent class description."""
    fields = {}
    raw_process = _raw_process_number(value)
    if raw_process:
        fields["processo"] = format_cnj(raw_process, strict=False) or raw_process
    process_class = _extract_class(value)
    if process_class is not None:
        fields["classe"] = process_class
    return fields


def _parse_result_item(item) -> dict:
    """Parse a single resultadoItem div from the TJSC search page."""
    result = {}
    labels = item.find_all("div", class_="resLabel")
    values = item.find_all("div", class_="resValue")

    for label, value in zip(labels, values, strict=False):
        label_text = label.get_text(strip=True).upper()
        key = _resolve_field(label_text)
        if not key:
            continue

        if key == "processo":
            result.update(_extract_process_fields(value))
            continue
        result[key] = value.get_text(strip=True)

    if "decisao" in result:
        result.setdefault("ementa", result["decisao"])

    return result


def _iter_result_items(resultados_brutos: list) -> Iterator[Tag]:
    """Yield result items from every downloaded page."""
    for html in resultados_brutos:
        soup = BeautifulSoup(html, "html.parser")
        yield from soup.find_all("div", class_="resultadoItem")


def _avisar_campos_vazios(registros: list[dict]) -> None:
    """Avisa os registros sem número de processo e os com processo e sem classe."""
    vazios = {
        ("número de processo", "processo"): sum("processo" not in r for r in registros),
        ("classe", "classe"): sum("processo" in r and "classe" not in r for r in registros),
    }
    for (descricao, coluna), quantos in vazios.items():
        if quantos:
            avisar(
                f"TJSC cjsg: {quantos} registro(s) sem {descricao} reconhecível; "
                f"a coluna '{coluna}' fica vazia nessas linhas."
            )


def cjsg_parse_manager(resultados_brutos: list) -> pd.DataFrame:
    """Extract relevant data from the raw TJSC HTML responses.

    Returns a DataFrame with the decisions.

    Args:
        resultados_brutos: List of raw HTML strings from the TJSC search.
    """
    registros = []
    for item in _iter_result_items(resultados_brutos):
        registro = _parse_result_item(item)
        if registro and ("ementa" in registro or "processo" in registro):
            registros.append(registro)

    _avisar_campos_vazios(registros)

    df = pd.DataFrame(registros)
    if df.empty:
        return df

    for col in ["data_julgamento", "data_publicacao"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], format="%d/%m/%Y", errors="coerce").dt.date

    principais = [
        "processo", "classe", "orgao_julgador", "relator",
        "data_julgamento", "data_publicacao", "ementa",
    ]
    cols_principais = [c for c in principais if c in df.columns]
    cols_restantes = [c for c in df.columns if c not in principais]
    df = df[cols_principais + cols_restantes]
    return df
