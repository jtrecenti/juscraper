"""Valores deprecados de parametros publicos.

Fica fora de :mod:`juscraper.utils.params`, onde estao os aliases de nome
(``pop_deprecated_alias``, ``resolve_deprecated_alias``), porque aquele
modulo esta no limite de linhas do pylint. :func:`resolve_buscar_em` junta
os dois casos: troca o nome antigo e converte o valor.
"""
from __future__ import annotations

from collections.abc import Hashable, Mapping
from typing import Any, TypeVar

from ..core.avisos import avisar

V = TypeVar("V")

#: Valores de ``inteiro_teor`` (bool), alias deprecado de ``buscar_em`` no STF e no TJDFT.
BUSCAR_EM_DE_INTEIRO_TEOR: Mapping[Any, str] = {True: "inteiro_teor", False: "ementa"}


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


def resolve_buscar_em(
    kwargs: dict[str, Any],
    antigo: str,
    buscar_em: str | None = None,
    valores: Mapping[Any, str] | None = None,
) -> None:
    """Grava em ``kwargs["buscar_em"]`` o valor de ``buscar_em`` ou do nome antigo, convertido.

    ``buscar_em`` diz onde procurar ``pesquisa`` (``"ementa"`` ou
    ``"inteiro_teor"``; ver ``docs/api-conventions.qmd``). Os tribunais que
    escolhiam o campo com outro nome (``campo``, ``query_scope``,
    ``inteiro_teor``) e outros valores (``"E"``/``"I"``, ``"inteiroTeor"``,
    ``True``/``False``) aceitam o nome antigo como alias deprecado.

    - ``buscar_em`` vem no argumento, quando e parametro explicito do metodo
      (sentinela ``None``), ou em ``kwargs``, quando chega por ``**kwargs``.
    - ``antigo`` ausente de ``kwargs``: grava ``buscar_em``, se informado.
    - ``antigo`` presente: sai de ``kwargs``, o valor passa por ``valores``
      (valor fora do mapa segue igual, para o schema recusa-lo) e vira
      ``buscar_em``, com ``DeprecationWarning`` que diz o valor novo.
    - ``antigo`` e ``buscar_em`` juntos: ``ValueError``, sem aviso, como em
      :func:`~juscraper.utils.params.resolve_deprecated_alias`.

    O schema do tribunal valida o resultado, e sem ``buscar_em`` nem
    ``antigo`` vale o default dele.
    """
    if buscar_em is None:
        buscar_em = kwargs.pop("buscar_em", None)
    if antigo in kwargs:
        valor = kwargs.pop(antigo)
        if buscar_em is not None:
            raise ValueError(
                f"Não é possível passar 'buscar_em' e '{antigo}' ao mesmo tempo. Use apenas 'buscar_em'."
            )
        mapa = valores or {}
        buscar_em = mapa[valor] if isinstance(valor, Hashable) and valor in mapa else valor
        avisar(
            f"O parâmetro '{antigo}' está deprecado. Use buscar_em={buscar_em!r} em vez de {antigo}={valor!r}.",
            DeprecationWarning,
        )
    if buscar_em is not None:
        kwargs["buscar_em"] = buscar_em
