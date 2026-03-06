"""
Utility functions for normalizing public API parameters across all scrapers.
"""
import warnings


def normalize_paginas(paginas):
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


def normalize_pesquisa(pesquisa=None, **kwargs):
    """Normalize the search-term parameter.

    Canonical name is ``pesquisa``.  ``query`` and ``termo`` are accepted
    with a ``DeprecationWarning`` and are popped from *kwargs*.

    Returns:
        The search string.

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
        return deprecated_value

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
