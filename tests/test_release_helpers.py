"""Testes offline dos helpers da bateria de release de filtro de data."""
from __future__ import annotations

import pandas as pd
import pytest
from helpers import run_filtro_data_unica

_LINHA = {"data_julgamento": "2025-02-20", "data_publicacao": "2025-03-11"}


class _SoPublicacao:
    """Tribunal que filtra só por publicação e devolve também a data de julgamento."""

    def cjsg(self, _pesquisa: str, **kwargs: str) -> pd.DataFrame:
        if any(chave.startswith("data_julgamento") for chave in kwargs):
            raise TypeError("data_julgamento_inicio não é aceito")
        return pd.DataFrame([_LINHA])


class _AmbasAsDatas:
    """Tribunal que aceita julgamento e publicação juntos."""

    def cjsg(self, _pesquisa: str, **_kwargs: str) -> pd.DataFrame:
        return pd.DataFrame([_LINHA])


def test_filtro_so_de_publicacao_valida_a_coluna_de_publicacao():
    """Com só o filtro de publicação aplicado, o julgamento pode ser anterior à janela."""
    run_filtro_data_unica(_SoPublicacao())


def test_filtro_com_julgamento_continua_validando_a_coluna_de_julgamento():
    with pytest.raises(AssertionError, match="data_julgamento"):
        run_filtro_data_unica(_AmbasAsDatas())
