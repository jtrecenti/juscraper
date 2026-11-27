"""Type aliases reutilizados pelos schemas pydantic (refs #232).

Centraliza coercoes que aparecem em multiplos endpoints. Cada alias usa
``Annotated[..., BeforeValidator(...)]`` para colar a coercao no field, em vez
de duplicar helpers ``coerce_*`` no caller (padrao novo no projeto, alinhado a
pydantic v2).

Tipos disponiveis:

- :data:`InteiroSemBool` — inteiro que rejeita ``bool`` (inclusive
  ``numpy.bool_``) antes da coercao do pydantic, mantendo a coercao de strings
  numericas. Base de :data:`TamanhoPagina`; use direto quando o endpoint tem
  dominio proprio que o ``ge=1`` atropelaria na mensagem (Falcao: 5 ou 10).
- :data:`TamanhoPagina` — :data:`InteiroSemBool` positivo. Limites proprios do
  endpoint entram como ``Field(...)`` no campo.
- :data:`IdFiltro` — IDs internos do tribunal que aceitam ``int``, ``str`` ou
  ``list[int | str]``. Coage para ``str | None``, montando CSV quando lista;
  o campo validado e anotado como ``str | None``.
  Use em campos cujo backend interpreta CSV (``classeTreeSelection.values``,
  ``assuntosTreeSelection.values``, ``secoesTreeSelection.values``,
  ``varasTreeSelection.values``).
- :data:`BuscarEm` — onde procurar ``pesquisa``: ``"ementa"`` ou
  ``"inteiro_teor"`` (ver ``docs/api-conventions.qmd``). Tribunal com valor
  proprio declara o seu ``Literal`` (STM: ``"numero"``).
- :data:`IdFiltroUnico` — IDs single-value (``cdComarca`` no eSAJ). Rejeita
  ``list``/``tuple`` para nao mascarar uso indevido.
"""
from __future__ import annotations

from typing import Annotated, Literal

import numpy as np
from pydantic import BeforeValidator, Field


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


def _reject_bool(value: object) -> object:
    """Rejeita ``bool`` sem impedir a coercao de strings numericas para int.

    ``numpy.bool_`` nao herda de ``bool``, mas o pydantic o coage para ``int``
    do mesmo jeito; por isso entra na checagem.
    """
    if isinstance(value, (bool, np.bool_)):
        raise ValueError("esperado um inteiro, não bool.")
    return value


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


# O tipo base e o de saida (o validador sempre devolve ``str | None``), para
# quem le o campo validado nao precisar de ``cast``. ``json_schema_input_type``
# mantem no JSON schema de entrada as formas aceitas.
IdFiltro = Annotated[
    str | None,
    BeforeValidator(_coerce_id_filtro, json_schema_input_type=int | str | list[int | str] | None),
]
IdFiltroUnico = Annotated[
    str | None,
    BeforeValidator(_coerce_id_filtro_unico, json_schema_input_type=int | str | None),
]
InteiroSemBool = Annotated[int, BeforeValidator(_reject_bool)]
TamanhoPagina = Annotated[InteiroSemBool, Field(ge=1)]

BuscarEm = Literal["ementa", "inteiro_teor"]
