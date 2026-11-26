"""Valores deprecados de parametros publicos.

Fica fora de :mod:`juscraper.utils.params`, onde estao os aliases de nome
(``pop_deprecated_alias``, ``resolve_deprecated_alias``), porque aquele
modulo esta no limite de linhas do pylint. :func:`resolve_buscar_em` junta
os dois casos: troca o nome antigo e converte o valor.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, TypeVar

from pydantic import TypeAdapter, ValidationError

from ..core.avisos import avisar

V = TypeVar("V")

_BOOL = TypeAdapter(bool)
#: Conversao do valor antigo no canonico: mapa, ou funcao que devolve ``None`` para valor desconhecido.
_Valores = Mapping[Any, str] | Callable[[object], "str | None"]


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


def buscar_em_de_inteiro_teor(valor: object) -> str | None:
    """Converte ``inteiro_teor``, alias deprecado de ``buscar_em`` no STF e no TJDFT.

    Le o valor como o schema lia o ``bool`` antigo (``True``, ``1``,
    ``"true"``...). ``None`` quando o valor nao e booleano.
    """
    try:
        return "inteiro_teor" if _BOOL.validate_python(valor) else "ementa"
    except ValidationError:
        return None


def _converter(valores: _Valores, valor: object) -> str | None:
    if callable(valores):
        return valores(valor)
    try:
        return valores.get(valor)
    except TypeError:  # valor sem hash: o schema o recusa
        return None


def resolve_buscar_em(
    kwargs: dict[str, Any],
    antigo: str,
    buscar_em: object = None,
    valores: _Valores | None = None,
) -> None:
    """Grava em ``kwargs["buscar_em"]`` o valor de ``buscar_em`` ou do nome antigo, convertido.

    ``buscar_em`` diz onde procurar ``pesquisa`` (``"ementa"`` ou
    ``"inteiro_teor"``; ver ``docs/api-conventions.qmd``). Os tribunais que
    escolhiam o campo com outro nome (``campo``, ``query_scope``,
    ``inteiro_teor``) e outros valores (``"E"``/``"I"``, ``"inteiroTeor"``,
    ``True``/``False``) aceitam o nome antigo como alias deprecado.
    ``valores`` converte o valor antigo no canonico: um mapa ou uma funcao
    que devolve ``None`` para valor que nao conhece. Sem ``valores``, os
    valores sao os mesmos.

    - ``buscar_em`` vem no argumento, quando e parametro explicito do metodo
      (sentinela ``None``), ou em ``kwargs``, quando chega por ``**kwargs``.
    - ``antigo`` presente: sai de ``kwargs`` e o valor convertido vira
      ``buscar_em``, com ``DeprecationWarning``. Valor que ``valores`` nao
      conhece segue igual, para o schema recusa-lo.
    - ``antigo`` e ``buscar_em`` juntos: ``ValueError``, sem aviso, como em
      :func:`~juscraper.utils.params.resolve_deprecated_alias`.
    - Valor antigo em ``buscar_em`` (o parametro antigo passado por posicao,
      como ``cjsg("dano", 1, "I")`` no TJSC): convertido, com
      ``DeprecationWarning``.

    O schema do tribunal valida o resultado, e sem ``buscar_em`` nem
    ``antigo`` vale o default dele.
    """
    if buscar_em is None:
        buscar_em = kwargs.pop("buscar_em", None)
    if antigo in kwargs:
        if buscar_em is not None:
            kwargs.pop(antigo)
            raise ValueError(
                f"Não é possível passar 'buscar_em' e '{antigo}' ao mesmo tempo. Use apenas 'buscar_em'."
            )
        buscar_em = _valor_do_alias(antigo, kwargs.pop(antigo), valores)
    elif buscar_em is not None and valores is not None:
        buscar_em = _valor_antigo_em_buscar_em(antigo, buscar_em, valores)
    if buscar_em is not None:
        kwargs["buscar_em"] = buscar_em


def _valor_do_alias(antigo: str, valor: object, valores: _Valores | None) -> object:
    """Converte o valor do alias, com aviso; o aviso so sugere valor que a conversao conhece."""
    novo = valor if valores is None else _converter(valores, valor)
    if valores is None:
        sugestao = "Use 'buscar_em', com o mesmo valor."
    elif novo is None:
        sugestao = "Use 'buscar_em'."
    else:
        sugestao = f"Use buscar_em={novo!r} em vez de {antigo}={valor!r}."
    avisar(f"O parâmetro '{antigo}' está deprecado. {sugestao}", DeprecationWarning)
    return valor if novo is None else novo


def _valor_antigo_em_buscar_em(antigo: str, buscar_em: object, valores: _Valores) -> object:
    """Converte, com aviso, o valor antigo passado em ``buscar_em`` (o parametro antigo por posicao)."""
    novo = _converter(valores, buscar_em)
    if novo is None or novo == buscar_em:
        return buscar_em
    avisar(
        f"buscar_em={buscar_em!r} é valor do parâmetro deprecado '{antigo}'. Use buscar_em={novo!r}.",
        DeprecationWarning,
    )
    return novo
