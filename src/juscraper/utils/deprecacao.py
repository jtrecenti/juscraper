"""Valores deprecados de parametros publicos.

Fica fora de :mod:`juscraper.utils.params`, onde estao os aliases de nome
(``pop_deprecated_alias``, ``resolve_deprecated_alias``), porque aquele
modulo esta no limite de linhas do pylint.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import TypeVar

from ..core.avisos import avisar

V = TypeVar("V")


def resolve_deprecated_value(valor: V, substitutos: Mapping[str, V], mensagem: str) -> V:
    """Troca um valor deprecado de parametro pelo substituto, com ``DeprecationWarning``.

    Contraparte de ``resolve_deprecated_alias`` para valores: o nome do
    parametro continua, mas um valor aceito antes (``votacao="Unanime"`` no
    TJAP, ``id_instancia=2`` no TJGO) passa a ir ao backend como outro.

    - ``str(valor)`` fora de ``substitutos``: retorna ``valor`` inalterado, sem aviso.
    - ``str(valor)`` em ``substitutos``: emite ``DeprecationWarning`` por
      :func:`~juscraper.core.avisos.avisar` e retorna o substituto.

    A busca por ``str(valor)`` faz ``2`` e ``"2"`` valerem pela mesma chave,
    sem casar ``2.0`` nem ``True``. ``mensagem`` e um template de
    :meth:`str.format` com ``{antigo}`` (o ``valor`` recebido) e ``{novo}``;
    aceita conversoes como ``{antigo!r}``.

    Returns:
        O substituto, ou ``valor`` quando ele nao esta deprecado.
    """
    chave = str(valor)
    if chave not in substitutos:
        return valor
    novo = substitutos[chave]
    avisar(mensagem.format(antigo=valor, novo=novo), DeprecationWarning)
    return novo
