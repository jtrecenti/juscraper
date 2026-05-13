"""Type aliases reutilizados pelos schemas pydantic (refs #232).

Centraliza coercoes que aparecem em multiplos endpoints. Cada alias usa
``Annotated[..., BeforeValidator(...)]`` para colar a coercao no field, em vez
de duplicar helpers ``coerce_*`` no caller (padrao novo no projeto, alinhado a
pydantic v2).

Tipos disponiveis:

- :data:`IdFiltro` — IDs internos do tribunal que aceitam ``int``, ``str`` ou
  ``list[int | str]``. Coage para ``str | None``, montando CSV quando lista.
  Use em campos cujo backend interpreta CSV (``classeTreeSelection.values``,
  ``assuntosTreeSelection.values``, ``secoesTreeSelection.values``,
  ``varasTreeSelection.values``).
- :data:`IdFiltroUnico` — IDs single-value (``cdComarca`` no eSAJ). Rejeita
  ``list``/``tuple`` para nao mascarar uso indevido.
"""
from __future__ import annotations

from typing import Annotated

from pydantic import BeforeValidator


def _coerce_id_filtro(value):
    """Coage ``int | str | list[int | str] | None`` para ``str | None``.

    Lista vazia vira ``None`` (semanticamente equivalente a "sem filtro"); lista
    nao-vazia vira CSV. ``int`` vira ``str(int)``. Levanta ``ValueError`` (que
    o pydantic embrulha em ``ValidationError``) para tipos nao suportados.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        # bool e subclasse de int em Python; rejeitar explicitamente para
        # nao mascarar uso indevido (``classe=True`` viraria ``"True"``).
        raise ValueError(
            f"IdFiltro aceita int, str, list ou None — recebeu bool ({value!r})"
        )
    if isinstance(value, (list, tuple)):
        if not value:
            return None
        return ",".join(str(v) for v in value)
    if isinstance(value, (int, str)):
        return str(value)
    raise ValueError(
        f"IdFiltro aceita int, str, list ou None — recebeu {type(value).__name__}"
    )


def _coerce_id_filtro_unico(value):
    """Igual a :func:`_coerce_id_filtro` mas rejeita ``list``/``tuple``.

    Usado em campos single-value do backend (ex.: ``cdComarca``), onde aceitar
    lista mascararia uso indevido — o tribunal so consulta uma comarca por
    chamada. Levanta ``ValueError`` para que o pydantic embrulhe em
    ``ValidationError``.
    """
    if isinstance(value, (list, tuple)):
        raise ValueError(
            "Campo single-value: aceita apenas int/str (backend nao suporta CSV aqui)."
        )
    return _coerce_id_filtro(value)


IdFiltro = Annotated[
    int | str | list[int | str] | None, BeforeValidator(_coerce_id_filtro)
]
IdFiltroUnico = Annotated[int | str | None, BeforeValidator(_coerce_id_filtro_unico)]
