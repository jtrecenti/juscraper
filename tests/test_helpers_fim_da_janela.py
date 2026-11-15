"""Testes offline de ``run_fim_da_janela``, com raspador falso."""
from __future__ import annotations

import pandas as pd
import pytest
from helpers import DATA_ALVO_FIM_BR, DATA_PUB_FIM_BR, run_fim_da_janela

JULGAMENTO = ("data_julgamento_inicio", "data_julgamento_fim")
PUBLICACAO = ("data_publicacao_inicio", "data_publicacao_fim")


class RaspadorFalso:
    """Devolve um DataFrame por tipo de filtro e recusa os tipos não aceitos."""

    def __init__(self, respostas: dict[str, pd.DataFrame]):
        self.respostas = respostas
        self.chamadas: list[dict] = []

    def cjsg(self, pesquisa, **kwargs):
        self.chamadas.append({"pesquisa": pesquisa, **kwargs})
        tipo = "julgamento" if JULGAMENTO[0] in kwargs else "publicacao"
        if tipo not in self.respostas:
            raise TypeError(f"argumento inesperado de {tipo}")
        return self.respostas[tipo]


def _df(coluna: str, datas: list[str | None]) -> pd.DataFrame:
    return pd.DataFrame({"processo": [f"p{i}" for i in range(len(datas))], coluna: datas})


def test_publicacao_com_dia_seguinte_reprova():
    raspador = RaspadorFalso({
        "publicacao": _df("data_publicacao", ["2025-04-29", "2025-04-30T00:00:00", "2025-04-30"]),
    })
    with pytest.raises(AssertionError, match=r"2 de 3 linhas com outra data \(2025-04-30\)"):
        run_fim_da_janela(raspador)


def test_julgamento_e_publicacao_com_vazamento_saem_juntos():
    raspador = RaspadorFalso({
        "julgamento": _df("data_julgamento", ["13/03/2025", "14/03/2025"]),
        "publicacao": _df("data_publicacao", ["2025-04-30"]),
    })
    with pytest.raises(AssertionError) as erro:
        run_fim_da_janela(raspador)
    assert "2025-03-14" in str(erro.value)
    assert "2025-04-30" in str(erro.value)


def test_so_julgamento_no_dia_passa_e_envia_um_dia_e_tres_paginas():
    raspador = RaspadorFalso({"julgamento": _df("data_julgamento", ["2025-03-13"] * 4)})
    assert run_fim_da_janela(raspador) == {"data_julgamento": 4}
    chamada = raspador.chamadas[0]
    assert chamada[JULGAMENTO[0]] == chamada[JULGAMENTO[1]] == DATA_ALVO_FIM_BR
    assert chamada["paginas"] == range(1, 4)


def test_cada_filtro_confere_so_a_coluna_do_seu_tipo():
    # Filtrou por publicação; a data de julgamento vem de antes e não conta.
    df = pd.DataFrame({
        "data_julgamento": ["2025-03-01", "2025-02-10"],
        "dataPublicacao": ["2025-04-29", "2025-04-29"],
    })
    raspador = RaspadorFalso({"publicacao": df})
    assert run_fim_da_janela(raspador) == {"dataPublicacao": 2}
    assert raspador.chamadas[-1][PUBLICACAO[0]] == DATA_PUB_FIM_BR


def test_linha_sem_data_nao_conta():
    raspador = RaspadorFalso({"publicacao": _df("data_publicacao", ["2025-04-29", None, "NaT", ""])})
    assert run_fim_da_janela(raspador) == {"data_publicacao": 4}


def test_resultado_vazio_ou_sem_coluna_devolve_dicionario_vazio():
    raspador = RaspadorFalso({
        "julgamento": pd.DataFrame(),
        "publicacao": pd.DataFrame({"processo": ["p0"], "ementa": ["texto"]}),
    })
    assert run_fim_da_janela(raspador) == {}


def test_tribunal_que_recusa_os_dois_filtros_levanta_type_error():
    with pytest.raises(TypeError):
        run_fim_da_janela(RaspadorFalso({}))
