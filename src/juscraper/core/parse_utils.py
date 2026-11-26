"""Helpers compartilhados de parsing — limpeza HTML e normalização de datas.

Consolidam lógica duplicada hoje em vários ``courts/<xx>/parse.py``:

* ``clean_html`` substitui ``_clean_html`` privado de TJAP/TJRN/TJRO. A versão
  default (``decode_entities=True``) decodifica todas as entidades HTML5 via
  ``html.unescape`` (cobre nomeadas — ``&Aacute;``, ``&copy;``, ``&hellip;`` —
  e numéricas — ``&#193;``, ``&#xC1;``). ``decode_entities=False`` cobre o caso
  minimalista (só strip de tags e whitespace) usado por TJRN/TJRO.
* ``coerce_date_columns`` extrai o loop ``pd.to_datetime(..., errors="coerce").dt.date``
  repetido em ~13 tribunais.
* ``clean_document_text`` limpa o texto bruto de documento dos agregadores
  JusBR e PDPJ, que servem a mesma API da PDPJ-CNJ.
* ``normalizar_texto`` e ``normalizar_colunas_texto`` tiram do texto corrido
  (ementa, decisão, inteiro teor) os caracteres que atrapalham a busca, sem
  mexer em quebras de linha nem em espaços.
* ``html_para_texto`` converte HTML de texto longo (ementa, inteiro teor) em
  texto com um parágrafo por linha, para os campos em que ``clean_html``, que
  põe tudo numa linha só, perderia a estrutura.

Uso (a partir das Fases 1-4 do refactor #194)::

    from juscraper.core.parse_utils import clean_html, coerce_date_columns

A migração dos tribunais para esses helpers acontece nas issues #202–#205.
"""
from __future__ import annotations

import html
import re
from collections.abc import Iterable
from typing import overload

import pandas as pd

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")

# Caracteres invisíveis que separam letras de uma mesma palavra: ``"MANDADO\u200c
# \u200cDE"`` no TJES, ``"§\xad 3º"`` no TJPI. Hífen discricionário e os de
# largura zero (espaço, não-agregador e agregador).
_INVISIVEIS = dict.fromkeys(map(ord, "\xad\u200b\u200c\u200d"))

# Trechos que o navegador não mostra: comentários (o Word guarda neles o XML de
# estilos, que vira ``"Normal 0 21 false ..."`` no TJAP), o conteúdo de
# ``<style>``, ``<script>`` e ``<title>`` (``"p{text-align: justify;}"`` no
# TJRN) e a tag cortada no fim do texto (``'<p dir="ltr" s...'``). Sem o
# fechamento, o comentário e esses blocos valem até o fim, como no navegador.
_SEM_TEXTO_RE = re.compile(
    r"<!--.*?(?:-->|\Z)|<(style|script|title)\b[^>]*>.*?(?:</\1\s*>|\Z)|<[a-zA-Z/][^<>\n]*\Z",
    re.DOTALL | re.IGNORECASE,
)
# Tags de bloco e ``<br>``, que abrem uma linha nova; ``<td>``/``<th>`` separam
# células com espaço. As demais (``<b>``, ``<span>``, ``<font>``...) somem sem
# deixar espaço, como no navegador: ``"<b>dano</b>,"`` vira ``"dano,"``.
_BLOCOS = (
    "address|article|aside|blockquote|body|br|caption|center|dd|details|div|dl|"
    "dt|fieldset|figcaption|figure|footer|form|h[1-6]|header|hr|html|li|main|"
    "nav|ol|p|pre|section|summary|table|tbody|tfoot|thead|tr|ul"
)
_TAG_BLOCO_RE = re.compile(rf"</?(?:{_BLOCOS})\b[^>]*>", re.IGNORECASE)
_TAG_CELULA_RE = re.compile(r"</?t[dh]\b[^>]*>", re.IGNORECASE)
# Só ``<`` seguido de letra, ``/`` ou ``!`` abre tag: ``"(<18 anos)"`` fica.
_TAG_ABERTA_RE = re.compile(r"<[a-zA-Z/!][^<>]*>")
_FIM_DE_LINHA_RE = re.compile(r"\r\n?|\n")
# Marca o fim de linha até o fim da limpeza, para que o ``\n`` do código-fonte
# e o de ``&#10;`` contem como espaço.
_SEPARADOR_DE_LINHA = "\x00"


def clean_html(text: str | None, decode_entities: bool = True) -> str | None:
    """Remove tags HTML e (opcionalmente) decodifica entidades.

    Args:
        text: Conteúdo bruto. ``None``/string vazia são retornados sem alteração.
        decode_entities: Se ``True`` (default), decodifica todas as entidades
            HTML5 via ``html.unescape`` — nomeadas (``&Aacute;``, ``&amp;``,
            ``&copy;``, ``&hellip;``, ...) e numéricas (``&#193;``, ``&#xC1;``).
            Se ``False``, só remove tags e colapsa whitespace.

    Returns:
        Texto limpo, ou o input sem alteração quando vazio/``None``.
    """
    if not text:
        return text

    text = _TAG_RE.sub(" ", text)

    if decode_entities:
        text = html.unescape(text)

    return _WHITESPACE_RE.sub(" ", text).strip()


def html_para_texto(text: str | None, *, preservar_quebras: bool = False) -> str | None:
    r"""Converte HTML de texto longo em texto com um parágrafo por linha.

    Para ementa e inteiro teor que chegam em HTML. ``<br>`` e as tags de bloco
    (``<p>``, ``<div>``, ``<li>``, ``<h3>``...) viram ``\n``. Como no
    navegador, a quebra de linha do código-fonte (e a de ``&#10;``) vale um
    espaço, as demais tags somem sem deixar espaço, ``<`` que não abre tag
    (``"<18 anos"``) fica, e comentários, ``<style>``, ``<script>`` e
    ``<title>`` saem com o conteúdo.

    Depois de decodificar as entidades, o texto passa por
    :func:`normalizar_texto`. Os espaços seguidos viram um só, as pontas de
    cada linha são aparadas e as linhas vazias saem.

    Nomes, classes e outros campos curtos continuam com :func:`clean_html`,
    que põe tudo numa linha só.

    Args:
        text: HTML bruto. ``None``/string vazia são retornados sem alteração.
        preservar_quebras: Se ``True``, a quebra de linha do texto também
            separa linhas, como ``<br>``. Para o texto que o portal exibe com
            ``white-space: pre-line`` (TJSC) e o texto com marcação esparsa
            (``<em>``, ``<br/>``) entre parágrafos separados por ``\n`` (TJMT).

    Returns:
        O texto com um parágrafo por linha (vazio sem texto no HTML), ou o input quando vazio/``None``.

    Examples: Exemplo
        >>> html_para_texto("<p>EMENTA: <b>DANO</b>, MORAL.</p><p>Recurso&nbsp;provido.</p>")
        'EMENTA: DANO, MORAL.\nRecurso provido.'
    """
    if not text:
        return text

    text = _SEM_TEXTO_RE.sub("", text)
    if preservar_quebras:
        text = _FIM_DE_LINHA_RE.sub(_SEPARADOR_DE_LINHA, text)
    text = _TAG_BLOCO_RE.sub(_SEPARADOR_DE_LINHA, text)
    text = _TAG_ABERTA_RE.sub("", _TAG_CELULA_RE.sub(" ", text))
    text = normalizar_texto(html.unescape(text))
    linhas = (" ".join(linha.split()) for linha in text.split(_SEPARADOR_DE_LINHA))
    return "\n".join(linha for linha in linhas if linha)


def coerce_date_columns(
    df: pd.DataFrame,
    cols: list[str],
    *,
    date_format: str | None = None,
) -> pd.DataFrame:
    """Coage colunas para ``date`` via ``pd.to_datetime(..., errors="coerce").dt.date``.

    Mutação **in-place** + retorno (padrão pandas para encadeamento). Colunas
    ausentes em ``df`` são ignoradas silenciosamente. ``df`` vazio retorna direto.

    Args:
        df: DataFrame alvo.
        cols: Nomes de coluna candidatas a normalizar.
        date_format: Formato strptime explícito repassado a ``pd.to_datetime``
            (keyword-only). Use para tribunais que serializam datas em formato
            ambíguo como ``DD/MM/AAAA`` — sem isso, o pandas pode interpretar o
            valor no formato americano. Default ``None`` preserva o
            comportamento de inferência do pandas (ISO e similares).

    Returns:
        O próprio ``df``.

    Examples: Exemplo
        >>> # Default: inferência do pandas (ISO e similares).
        >>> coerce_date_columns(df, ["data_julgamento"])
        >>> # Formato ambíguo DD/MM/AAAA — usar ``date_format`` explícito.
        >>> coerce_date_columns(df, ["data_julgamento"], date_format="%d/%m/%Y")
    """
    if df.empty:
        return df
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], format=date_format, errors="coerce").dt.date
    return df


@overload
def normalizar_texto(texto: str) -> str: ...


@overload
def normalizar_texto(texto: object) -> object: ...


def normalizar_texto(texto: object) -> object:
    r"""Normaliza fins de linha, espaço não separável e caracteres invisíveis.

    Troca ``\r\n`` e ``\r`` por ``\n`` e ``\xa0`` por espaço comum, e remove
    o hífen discricionário (``\xad``) e os caracteres de largura zero
    (``\u200b``, ``\u200c`` e ``\u200d``). Uma busca por ``"art. 14"`` passa a
    achar o texto que o tribunal escreveu ``"art.\xa014"``.

    Não colapsa espaços, não remove tabulações e preserva as quebras de
    linha, que separam os parágrafos. Serve a texto corrido; HTML e RTF
    brutos devem ficar como vieram.

    Args:
        texto: Valor da coluna. O que não for ``str`` (``None``, ``NaN``,
            números) volta sem alteração.

    Returns:
        O texto normalizado, ou o próprio valor quando não é ``str``.
    """
    if not isinstance(texto, str):
        return texto
    return texto.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ").translate(_INVISIVEIS)


def normalizar_colunas_texto(df: pd.DataFrame, colunas: Iterable[str]) -> pd.DataFrame:
    """Aplica :func:`normalizar_texto` às colunas de texto corrido de ``df``.

    Mutação **in-place** + retorno, como :func:`coerce_date_columns`. Colunas
    ausentes em ``df`` são ignoradas; valores que não são ``str`` ficam como
    estão.

    Args:
        df: DataFrame alvo.
        colunas: Nomes das colunas de texto corrido.

    Returns:
        O próprio ``df``.
    """
    for coluna in colunas:
        if coluna in df.columns:
            df[coluna] = df[coluna].map(normalizar_texto)
    return df


def clean_document_text(text: str | None) -> str | None:
    """Remove caracteres de controle e normaliza quebras de linha e espaços do texto bruto.

    Args:
        text: Texto como a API devolveu.

    Returns:
        O texto limpo, ou ``None`` quando a entrada é ``None``, vazia ou só tem
            espaço: documento sem texto aproveitável sai igual nos dois agregadores.
    """
    if not text:
        return None
    cleaned = normalizar_texto(text.replace("\x00", "").replace("\x1a", ""))
    cleaned = cleaned.replace("\u2028", "\n").replace("\u2029", "\n")
    return cleaned.strip() or None
