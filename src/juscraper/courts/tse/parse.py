"""Leitura dos catálogos do formulário de jurisprudência do TSE."""

from __future__ import annotations

import pandas as pd

from juscraper.core.exceptions import HTTPSemanticError

COLUNAS_CLASSES = {"siglaClasse": "sigla_classe", "descricaoClasse": "descricao_classe"}
COLUNAS_NORMAS = ("sigla", "tipo", "numero", "ano", "norma")


class CatalogoInesperadoError(HTTPSemanticError):
    """O catálogo veio em JSON, mas fora do formato esperado (lista de itens)."""


def _itens(dados: object, catalogo: str, tipo: type) -> list:
    if not isinstance(dados, list) or not all(isinstance(item, tipo) for item in dados):
        raise CatalogoInesperadoError(
            f"O catálogo {catalogo!r} do TSE não veio como lista de {tipo.__name__}: {str(dados)[:200]!r}"
        )
    return dados


def parse_registros(dados: object, catalogo: str, colunas: dict[str, str] | tuple[str, ...]) -> pd.DataFrame:
    """Tabela de um catálogo que vem como lista de objetos.

    ``colunas`` vêm primeiro e existem também no catálogo vazio; um ``dict``
    as renomeia. Chave que o backend acrescentar entra depois delas.
    """
    tabela = pd.DataFrame(_itens(dados, catalogo, dict))
    extras = [coluna for coluna in tabela.columns if coluna not in colunas]
    tabela = tabela.reindex(columns=[*colunas, *extras])
    return tabela.rename(columns=colunas) if isinstance(colunas, dict) else tabela


def parse_lista(dados: object, catalogo: str, coluna: str) -> pd.DataFrame:
    """Tabela de uma coluna para um catálogo que vem como lista de textos."""
    return pd.DataFrame({coluna: pd.Series(_itens(dados, catalogo, str), dtype=object)})
