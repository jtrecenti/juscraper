"""Utility functions for normalizing public API parameters across all scrapers."""
import difflib
import warnings
from datetime import datetime
from typing import Optional, Union

from pydantic import BaseModel, ValidationError

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


def to_br_date(date_str):
    """Convert ``YYYY-MM-DD`` to ``DD/MM/YYYY``. Passthrough for other formats/None.

    Most Brazilian court search forms (eSAJ, PJe) reject ISO dates silently and
    fall back to an unfiltered query, so normalize at the scraper boundary.
    """
    if not date_str:
        return date_str
    parts = date_str.split("-")
    if len(parts) == 3 and len(parts[0]) == 4:
        return f"{parts[2]}/{parts[1]}/{parts[0]}"
    return date_str


def to_iso_date(date_str):
    """Convert ``DD/MM/YYYY`` to ``YYYY-MM-DD``. Passthrough for other formats/None.

    Counterpart to :func:`to_br_date` — used by scrapers whose backends speak
    JSON/GraphQL and expect ISO-8601 dates (TJBA, some PJe APIs).
    """
    if not date_str:
        return date_str
    parts = date_str.split("/")
    if len(parts) == 3 and len(parts[2]) == 4:
        return f"{parts[2]}-{parts[1]}-{parts[0]}"
    return date_str


def validate_intervalo_datas(
    data_inicio,
    data_fim,
    *,
    max_dias: Optional[int] = 366,
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
            full calendar year even across a leap day). ``None`` disables the
            window check while still validating ``formato`` and
            ``data_inicio <= data_fim`` — used by tribunals whose backend has
            no documented limit (audited under #128).
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

    if max_dias is None:
        return

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


def raise_on_extra_kwargs(
    exc: ValidationError,
    method: str,
    *,
    schema_cls: Optional[type[BaseModel]] = None,
) -> None:
    """Convert pydantic ``extra_forbidden`` errors into a friendly ``TypeError``.

    Regular users expect ``TypeError: got unexpected keyword argument`` when
    they mistype a param name. Raising pydantic's ``ValidationError`` for that
    case is accurate but unfriendly. Other validation errors (bad date format,
    wrong literal, etc.) surface as-is so the caller can see them.

    When ``schema_cls`` is provided, each unknown kwarg is matched against the
    schema's declared fields via :func:`difflib.get_close_matches`; if a close
    match is found, it is included in the error message as ``(você quis dizer
    'X'?)``. This catches typos like ``data_juglamento_inicio`` ->
    ``data_julgamento_inicio``.

    Args:
        exc: The :class:`pydantic.ValidationError` raised by ``Schema(...)``.
        method: Human-readable method identifier for the error message
            (e.g. ``"TJRNScraper.cjsg()"``).
        schema_cls: Optional pydantic model whose fields are used to suggest
            close matches for unknown kwargs. When ``None``, no suggestion is
            emitted.

    Raises:
        TypeError: When *all* errors in ``exc`` are ``extra_forbidden``. The
            offending field names (and suggestions, when available) are included
            in the message. When the error mix is not pure ``extra_forbidden``
            the function returns ``None`` and the caller is expected to
            ``raise`` the original exception.
    """
    extras = [err for err in exc.errors() if err["type"] == "extra_forbidden"]
    if extras and len(extras) == len(exc.errors()):
        valid_fields = list(schema_cls.model_fields) if schema_cls is not None else []
        parts = []
        for err in extras:
            name = str(err["loc"][-1])
            close = difflib.get_close_matches(name, valid_fields, n=1, cutoff=0.7)
            if close:
                parts.append(f"'{name}' (você quis dizer '{close[0]}'?)")
            else:
                parts.append(repr(name))
        raise TypeError(
            f"{method} got unexpected keyword argument(s): {', '.join(parts)}"
        ) from exc


def apply_input_pipeline_search(
    schema_cls: type[BaseModel],
    method_name: str,
    *,
    pesquisa: str,
    paginas,
    kwargs: dict,
    max_dias: Optional[int] = None,
    origem_mensagem: Optional[str] = None,
    **canonical_filters,
) -> BaseModel:
    """Run the canonical input-validation pipeline for search endpoints (cjsg/cjpg).

    Order:

    1. :func:`normalize_paginas` — int → ``range(1, n+1)``; list/range/None passthrough.
    2. :func:`normalize_datas` — pop date aliases (``_de``/``_ate``,
       ``data_inicio``/``data_fim``) emitting :class:`DeprecationWarning` and
       returning canonical names.
    3. :func:`pop_normalize_aliases` — strip from ``kwargs`` everything already
       consumed (search aliases, date aliases, canonical date keys), so the
       same value isn't propagated twice into the schema.
    4. :func:`validate_intervalo_datas` for julgamento *and* publicação. Format
       and ``inicio <= fim`` are always validated; the window cap is applied
       only when ``max_dias`` is set.
    5. ``schema_cls(pesquisa, paginas, **datas, **canonical_filters, **kwargs)``
       — pydantic validation with ``extra="forbid"``.
    6. :func:`raise_on_extra_kwargs` translates ``extra_forbidden`` errors into
       a :class:`TypeError`. Other validation errors propagate as-is.

    The caller is responsible for:

    - Calling :func:`normalize_pesquisa` (or skipping it when the endpoint
      accepts ``pesquisa=""``, e.g. TJSP cjpg).
    - Popping tribunal-specific deprecated aliases (``nr_processo``,
      ``magistrado``) **before** invoking this helper, otherwise pydantic
      rejects them as ``extra_forbidden``.
    - Running tribunal-specific validators that should fire before pydantic
      (e.g. ``validate_pesquisa_length`` in TJSP).
    - Passing ``max_dias`` and ``origem_mensagem`` when the backend has a
      documented window limit (e.g. eSAJ: ``max_dias=366,
      origem_mensagem="O eSAJ"``). The defaults disable the window check,
      since most non-eSAJ backends accept arbitrarily wide ranges (audited
      under #128).

    The parameter is named ``origem_mensagem`` (not ``origem``) on purpose:
    several tribunal scrapers use ``origem`` as a backend filter (e.g. TJPA's
    list of jurisdictional origins). Naming the helper parameter ``origem``
    would silently capture the caller's filter via Python's keyword binding
    rules, instead of forwarding it to the schema via ``**canonical_filters``.

    The date format used by :func:`validate_intervalo_datas` is read from the
    schema's ``BACKEND_DATE_FORMAT`` :class:`ClassVar`, defaulting to
    ``"%d/%m/%Y"`` (eSAJ). Tribunals whose backend speaks ISO declare
    ``BACKEND_DATE_FORMAT: ClassVar[str] = "%Y-%m-%d"`` in their schema. This
    keeps the format coupled to the schema (where it logically belongs) instead
    of being passed redundantly by every caller.

    Args:
        schema_cls: Pydantic model class to instantiate (e.g. :class:`InputCJSGTJRN`).
        method_name: Human-readable identifier used in the ``TypeError`` message
            when ``extra_forbidden`` triggers (e.g. ``"TJRNScraper.cjsg()"``).
        pesquisa: Already-normalized search term (or ``""`` for endpoints that
            allow open searches).
        paginas: Pages parameter as accepted by the public method (``int``,
            ``list``, ``range``, or ``None``).
        kwargs: The caller's local ``kwargs`` dict. Mutated in place by
            :func:`pop_normalize_aliases` and consumed by ``schema_cls``.
        max_dias: Window cap for date intervals, in days. ``None`` (default)
            disables the cap — used by tribunals whose backend has no
            documented limit (refs #128). The eSAJ family passes
            ``max_dias=366`` explicitly. Format and ordering of the dates are
            validated regardless of this value.
        origem_mensagem: Subject of the over-limit error message (only emitted
            when ``max_dias`` is set). Examples: ``"O eSAJ"``, ``"O TJRS"``.
            ``None`` (default) falls back to ``"O backend"`` so non-eSAJ
            tribunals invoking the helper without an explicit subject don't
            leak ``"eSAJ"`` into their error messages.
        **canonical_filters: Tribunal-specific filters already extracted from
            the public method signature (e.g. ``numero_processo=...``,
            ``relator=...``). They are forwarded to the schema as-is. **A key
            present in both ``canonical_filters`` and ``kwargs`` raises
            :class:`TypeError` (Python's ``schema_cls(**a, **b)`` semantics) —
            the caller is expected to pop conflicting kwargs beforehand.**

    Returns:
        Instantiated pydantic model with all fields validated.

    Raises:
        TypeError: When ``kwargs`` contains keys not declared in the schema.
        ValidationError: For other validation failures (bad type, format,
            literal mismatch).
        ValueError: When :func:`validate_intervalo_datas` rejects an interval.
    """
    paginas_norm = normalize_paginas(paginas)
    datas = normalize_datas(**kwargs)
    pop_normalize_aliases(kwargs, include_canonical=True)

    origem_resolvida = origem_mensagem if origem_mensagem is not None else "O backend"
    date_format = getattr(schema_cls, "BACKEND_DATE_FORMAT", "%d/%m/%Y")
    validate_intervalo_datas(
        datas["data_julgamento_inicio"],
        datas["data_julgamento_fim"],
        rotulo="data_julgamento",
        max_dias=max_dias,
        origem=origem_resolvida,
        formato=date_format,
    )
    validate_intervalo_datas(
        datas["data_publicacao_inicio"],
        datas["data_publicacao_fim"],
        rotulo="data_publicacao",
        max_dias=max_dias,
        origem=origem_resolvida,
        formato=date_format,
    )

    try:
        return schema_cls(
            pesquisa=pesquisa,
            paginas=paginas_norm,
            **{k: v for k, v in datas.items() if v is not None},
            **canonical_filters,
            **kwargs,
        )
    except ValidationError as exc:
        raise_on_extra_kwargs(exc, method_name, schema_cls=schema_cls)
        raise


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
    - Ambos setados: levanta ``ValueError`` explicando a colisao **sem
      emitir o ``DeprecationWarning``** — o uso esta errado (conflito), nao
      e o caso de uso "alias funcionando ainda" que o warning sinaliza.

    ``sentinel`` descreve o "nao setado" do parametro canonico:
    ``None`` para ``Optional[...]``, ``""`` para ``str = ""``. Kw-only
    pra forcar o autor a pensar sobre o default do seu metodo.
    """
    if old not in kwargs:
        return current_value
    if current_value != sentinel:
        kwargs.pop(old)
        raise ValueError(
            f"Não é possível passar '{new}' e '{old}' simultaneamente."
        )
    return pop_deprecated_alias(kwargs, old, new)
