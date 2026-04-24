"""Utility functions for normalizing public API parameters across all scrapers."""
import warnings
from datetime import datetime
from typing import Optional, Union

# Deprecated aliases consumed by ``normalize_pesquisa``. Keep in sync with the
# loop inside that function.
SEARCH_ALIASES: tuple[str, ...] = ("query", "termo")

# Canonical date keys produced by ``normalize_datas``. Callers that route dates
# through ``**kwargs`` (instead of naming them explicitly) must pop these too
# so the normalized values materialized via ``normalize_datas`` are the only
# ones propagated downstream.
DATE_CANONICAL: tuple[str, ...] = (
    "data_julgamento_inicio", "data_julgamento_fim",
    "data_publicacao_inicio", "data_publicacao_fim",
)

# Deprecated date aliases consumed by ``normalize_datas``. Keep in sync with
# the ``deprecated_map``/``generic_map`` dicts inside that function.
DATE_ALIASES: tuple[str, ...] = (
    "data_julgamento_de", "data_julgamento_ate",
    "data_publicacao_de", "data_publicacao_ate",
    "data_inicio", "data_fim",
)


def pop_normalize_aliases(kwargs: dict, *, include_canonical: bool = False) -> None:
    """Drop from ``kwargs`` all keys consumed by ``normalize_pesquisa``/``normalize_datas``.

    Background: ``normalize_pesquisa(..., **kwargs)`` and ``normalize_datas(**kwargs)``
    pop from their *own* local ``kwargs`` parameter — a copy built by Python when
    the caller unpacks with ``**``. The caller's dict is not mutated, so the
    deprecated aliases and canonical date keys survive and would be re-propagated
    into downstream ``**kwargs`` calls, clashing with the canonical keyword
    arguments the caller already materialized.

    Args:
        kwargs: The caller's local ``kwargs`` dict (mutated in place).
        include_canonical: When ``True``, also pop the canonical date keys
            (``data_julgamento_inicio``, ...). Use this when the caller receives
            dates through ``**kwargs`` rather than naming them explicitly in the
            function signature (e.g. ``_esaj/base.py``, ``tjsp/client.py`` cjpg).
    """
    for alias in SEARCH_ALIASES + DATE_ALIASES:
        kwargs.pop(alias, None)
    if include_canonical:
        for key in DATE_CANONICAL:
            kwargs.pop(key, None)


def normalize_paginas(paginas) -> Optional[Union[list, range]]:
    """Normalize the ``paginas`` parameter to a consistent type.

    Args:
        paginas: ``None`` (all pages), ``int`` (shorthand for ``range(1, n+1)``),
                 ``list`` or ``range`` (passthrough).

    Returns:
        ``None``, ``list``, or ``range``.

    Raises:
        TypeError: If *paginas* is not one of the accepted types.
    """
    if paginas is None:
        return None
    if isinstance(paginas, int):
        return range(1, paginas + 1)
    if isinstance(paginas, (list, range)):
        return paginas
    raise TypeError(
        f"paginas deve ser int, list, range ou None, não {type(paginas).__name__}"
    )


def normalize_pesquisa(pesquisa: Optional[str] = None, **kwargs) -> str:
    """Normalize the search-term parameter.

    Canonical name is ``pesquisa``.  ``query`` and ``termo`` are accepted
    with a ``DeprecationWarning`` and are popped from *kwargs*.

    Returns:
        The search string (never ``None``: missing input raises ``TypeError``).

    Raises:
        ValueError: If both ``pesquisa`` and a deprecated alias are given.
        TypeError: If no search term is provided at all.
    """
    deprecated_value = None
    deprecated_name = None

    for name in ("query", "termo"):
        if name in kwargs:
            if deprecated_value is not None:
                raise ValueError(
                    f"Não é possível passar '{deprecated_name}' e '{name}' ao mesmo tempo. "
                    "Use apenas 'pesquisa'."
                )
            deprecated_value = kwargs.pop(name)
            deprecated_name = name

    if pesquisa is not None and deprecated_value is not None:
        raise ValueError(
            f"Não é possível passar 'pesquisa' e '{deprecated_name}' ao mesmo tempo. "
            "Use apenas 'pesquisa'."
        )

    if deprecated_value is not None:
        warnings.warn(
            f"O parâmetro '{deprecated_name}' está deprecado. Use 'pesquisa' em vez disso.",
            DeprecationWarning,
            stacklevel=3,
        )
        return str(deprecated_value)

    if pesquisa is not None:
        return pesquisa

    raise TypeError("É necessário fornecer o parâmetro 'pesquisa'.")


def normalize_datas(**kwargs):
    """Normalize date parameters to canonical names.

    Canonical names:
        ``data_julgamento_inicio``, ``data_julgamento_fim``,
        ``data_publicacao_inicio``, ``data_publicacao_fim``.

    Deprecated aliases (``_de`` / ``_ate``):
        ``data_julgamento_de`` → ``data_julgamento_inicio``
        ``data_julgamento_ate`` → ``data_julgamento_fim``
        ``data_publicacao_de`` → ``data_publicacao_inicio``
        ``data_publicacao_ate`` → ``data_publicacao_fim``

    Generic aliases:
        ``data_inicio`` → ``data_julgamento_inicio``
        ``data_fim`` → ``data_julgamento_fim``

    Returns:
        dict with the four canonical keys (values may be ``None``).

    Raises:
        ValueError: If a generic alias conflicts with the specific canonical name.
    """
    result = {
        "data_julgamento_inicio": None,
        "data_julgamento_fim": None,
        "data_publicacao_inicio": None,
        "data_publicacao_fim": None,
    }

    deprecated_map = {
        "data_julgamento_de": "data_julgamento_inicio",
        "data_julgamento_ate": "data_julgamento_fim",
        "data_publicacao_de": "data_publicacao_inicio",
        "data_publicacao_ate": "data_publicacao_fim",
    }

    generic_map = {
        "data_inicio": "data_julgamento_inicio",
        "data_fim": "data_julgamento_fim",
    }

    # 1. Canonical names first
    for key in list(result.keys()):
        if key in kwargs:
            result[key] = kwargs.pop(key)

    # 2. Deprecated _de/_ate aliases
    for old_name, canonical in deprecated_map.items():
        if old_name in kwargs:
            value = kwargs.pop(old_name)
            if value is not None:
                if result[canonical] is not None:
                    raise ValueError(
                        f"Não é possível passar '{old_name}' e '{canonical}' ao mesmo tempo. "
                        f"Use apenas '{canonical}'."
                    )
                warnings.warn(
                    f"O parâmetro '{old_name}' está deprecado. Use '{canonical}' em vez disso.",
                    DeprecationWarning,
                    stacklevel=2,
                )
                result[canonical] = value

    # 3. Generic aliases
    for generic, canonical in generic_map.items():
        if generic in kwargs:
            value = kwargs.pop(generic)
            if value is not None:
                if result[canonical] is not None:
                    raise ValueError(
                        f"Não é possível passar '{generic}' e '{canonical}' ao mesmo tempo. "
                        f"Use apenas '{canonical}'."
                    )
                warnings.warn(
                    f"O parâmetro '{generic}' está deprecado. Use '{canonical}' em vez disso.",
                    DeprecationWarning,
                    stacklevel=2,
                )
                result[canonical] = value

    return result


def validate_intervalo_datas(
    data_inicio,
    data_fim,
    *,
    max_dias=366,
    formato="%d/%m/%Y",
    rotulo="data",
    origem="O eSAJ",
):
    """Validate a date interval before firing an HTTP request.

    Several tribunal search endpoints reject date ranges wider than a
    platform-specific window. The eSAJ jurisprudence endpoints (cjpg/cjsg),
    for example, cap the range at one year ("A faixa entre data de início e
    data de fim deve ser de no máximo 1 ano."). Checking the interval
    client-side turns a cryptic downstream failure (missing paginator,
    truncated HTML) into an actionable error raised before the request.

    Args:
        data_inicio: Start date as a string (``DD/MM/YYYY`` by default) or
            ``None``. ``None`` skips validation — single-bound searches are
            left to the server.
        data_fim: End date as a string or ``None``.
        max_dias: Maximum allowed interval in days (default: 366 to admit a
            full calendar year even across a leap day).
        formato: ``strptime`` format of the input strings.
        rotulo: Human-readable label for the parameter pair in error messages
            (e.g. ``"data_julgamento"``).
        origem: Subject of the over-limit error message (e.g. ``"O eSAJ"``,
            ``"O TJRS"``). Appears as ``"{origem} aceita no máximo N dias..."``.

    Raises:
        ValueError: If either string does not match ``formato``, if
            ``data_inicio > data_fim``, or if the interval exceeds
            ``max_dias``.
    """
    if data_inicio is None or data_fim is None:
        return

    try:
        dt_inicio = datetime.strptime(data_inicio, formato)
    except ValueError as exc:
        raise ValueError(
            f"'{rotulo}_inicio' inválida: {data_inicio!r}. Formato esperado: {formato}."
        ) from exc
    try:
        dt_fim = datetime.strptime(data_fim, formato)
    except ValueError as exc:
        raise ValueError(
            f"'{rotulo}_fim' inválida: {data_fim!r}. Formato esperado: {formato}."
        ) from exc

    if dt_inicio > dt_fim:
        raise ValueError(
            f"'{rotulo}_inicio' ({data_inicio}) é posterior a "
            f"'{rotulo}_fim' ({data_fim})."
        )

    dias = (dt_fim - dt_inicio).days
    if dias > max_dias:
        raise ValueError(
            f"{origem} aceita no máximo {max_dias} dias entre '{rotulo}_inicio' "
            f"e '{rotulo}_fim' (recebido: {dias} dias, de {data_inicio} a "
            f"{data_fim}). Divida a consulta em janelas menores."
        )


def warn_unsupported(param_name, tribunal):
    """Emit a ``UserWarning`` for an unsupported parameter.

    Args:
        param_name: Name of the parameter.
        tribunal: Tribunal identifier (e.g. ``"TJDFT"``).
    """
    warnings.warn(
        f"O parâmetro '{param_name}' não é suportado pelo {tribunal} e será ignorado.",
        UserWarning,
        stacklevel=2,
    )


def pop_deprecated_alias(kwargs: dict, old: str, new: str):
    """Pop ``old`` from ``kwargs``, emit ``DeprecationWarning``, return the value.

    Returns ``None`` when the alias is absent. Used by scraper clients to
    accept legacy parameter names for one release cycle after a canonical
    rename (refs #93 output/input name unification).
    """
    if old not in kwargs:
        return None
    value = kwargs.pop(old)
    warnings.warn(
        f"O parâmetro '{old}' está deprecado. Use '{new}' em vez disso.",
        DeprecationWarning,
        stacklevel=3,
    )
    return value


def resolve_deprecated_alias(
    kwargs: dict,
    old: str,
    new: str,
    current_value,
    *,
    sentinel=None,
):
    """Pop ``old`` alias from ``kwargs`` and merge with ``current_value``.

    Centraliza o padrao repetido em cada raspador que deprecou um
    parametro (refs #93): ``pop_deprecated_alias`` + checagem de colisao
    + reatribuicao.

    - Alias ausente em ``kwargs``: retorna ``current_value`` inalterado.
    - Alias presente e ``current_value == sentinel`` (canonico nao
      setado pelo usuario): emite ``DeprecationWarning`` e retorna o
      valor do alias.
    - Ambos setados: levanta ``ValueError`` explicando a colisao.

    ``sentinel`` descreve o "nao setado" do parametro canonico:
    ``None`` para ``Optional[...]``, ``""`` para ``str = ""``. Kw-only
    pra forcar o autor a pensar sobre o default do seu metodo.
    """
    old_value = pop_deprecated_alias(kwargs, old, new)
    if old_value is None:
        return current_value
    if current_value != sentinel:
        raise ValueError(
            f"Não é possível passar '{new}' e '{old}' simultaneamente."
        )
    return old_value
