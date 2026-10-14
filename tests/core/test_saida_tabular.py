"""Texto ausente sai como ``None`` nos métodos públicos, com pandas 2 ou 3.

O pandas 3 passou a inferir colunas de texto com o tipo ``str``, em que o
valor ausente é ``NaN``. Até o pandas 2, a mesma coluna saía como ``object``,
com ``None``. ``BaseScraper`` embrulha os métodos públicos das subclasses para
devolver o contrato do pandas 2 nas duas versões.

``future.infer_string`` liga no pandas 2.3 a mesma inferência do pandas 3, o
que deixa estes testes exercitarem o caso do pandas 3 em qualquer ambiente.
"""
from __future__ import annotations

import inspect
from importlib import import_module

import numpy as np
import pandas as pd
import pytest

from juscraper import _SCRAPERS
from juscraper.core.base import BaseScraper


def _classe(sigla: str) -> type:
    modulo, nome = _SCRAPERS[sigla].split(":")
    classe: type = getattr(import_module(modulo), nome)
    return classe


class _Mixin:
    def tabela_do_mixin(self) -> pd.DataFrame:
        return pd.DataFrame([{"texto": None}, {"texto": "b"}])


class _Raspador(_Mixin, BaseScraper):
    def __init__(self):
        super().__init__("teste")

    def tabela(self) -> pd.DataFrame:
        return pd.DataFrame([{"texto": None, "numero": 1.0}, {"texto": "b", "numero": None}])

    def tabelas(self) -> dict:
        return {"a": pd.DataFrame([{"texto": None}, {"texto": "b"}]), "total": 2}

    def tabela_string_explicita(self) -> pd.DataFrame:
        return pd.DataFrame({"texto": pd.array([None, "b"], dtype="string")})

    def contagem(self) -> int:
        return 3

    def paginas(self):
        yield pd.DataFrame([{"texto": None}, {"texto": "b"}])


@pytest.fixture
def inferencia_do_pandas_3():
    with pd.option_context("future.infer_string", True):  # noqa: FBT003 - a API do pandas recebe o valor posicional
        yield


@pytest.mark.usefixtures("inferencia_do_pandas_3")
def test_coluna_de_texto_sai_como_object_com_none():
    tabela = _Raspador().tabela()

    assert tabela["texto"].dtype == object
    assert tabela["texto"].tolist() == [None, "b"]


@pytest.mark.usefixtures("inferencia_do_pandas_3")
def test_coluna_numerica_continua_com_nan():
    tabela = _Raspador().tabela()

    assert tabela["numero"].dtype == np.float64
    assert np.isnan(tabela.loc[1, "numero"])


@pytest.mark.usefixtures("inferencia_do_pandas_3")
def test_dicionario_de_tabelas_e_normalizado_e_o_resto_fica():
    resultado = _Raspador().tabelas()

    assert resultado["a"]["texto"].tolist() == [None, "b"]
    assert resultado["total"] == 2


@pytest.mark.usefixtures("inferencia_do_pandas_3")
def test_metodo_herdado_de_mixin_tambem_e_normalizado():
    assert _Raspador().tabela_do_mixin()["texto"].tolist() == [None, "b"]


def test_tipo_string_explicito_nao_e_tocado():
    # ``dtype="string"`` usa ``pd.NA`` desde o pandas 1; quem o pede quer esse
    # tipo, e trocá-lo mudaria a saída também no pandas 2.
    tabela = _Raspador().tabela_string_explicita()

    assert isinstance(tabela["texto"].dtype, pd.StringDtype)
    assert tabela.loc[0, "texto"] is pd.NA


@pytest.mark.usefixtures("inferencia_do_pandas_3")
def test_colunas_com_nome_repetido_sao_normalizadas_por_posicao():
    class ComRepetidas(BaseScraper):
        def tabela(self) -> pd.DataFrame:
            return pd.DataFrame([[None, "x"], ["y", None]], columns=["texto", "texto"])

    tabela = ComRepetidas("teste").tabela()

    assert tabela.iloc[:, 0].tolist() == [None, "y"]
    assert tabela.iloc[:, 1].tolist() == ["x", None]


def test_retorno_que_nao_e_tabela_passa_intacto():
    raspador = _Raspador()

    assert raspador.contagem() == 3
    assert inspect.isgenerator(raspador.paginas())


def test_tabela_sem_texto_novo_volta_a_mesma():
    original = pd.DataFrame({"numero": [1.0, None]})

    class Identidade(BaseScraper):
        def tabela(self) -> pd.DataFrame:
            return original

    assert Identidade("teste").tabela() is original


def test_embrulho_preserva_assinatura_e_docstring():
    class Documentado(BaseScraper):
        def cjsg(self, pesquisa: str, paginas: int | None = None, **kwargs) -> pd.DataFrame:
            """Busca de jurisprudência."""
            return pd.DataFrame({"pesquisa": [pesquisa], "paginas": [paginas], "extras": [len(kwargs)]})

    metodo = Documentado.cjsg
    assert list(inspect.signature(metodo).parameters) == ["self", "pesquisa", "paginas", "kwargs"]
    assert inspect.unwrap(metodo) is not metodo
    assert inspect.unwrap(metodo).__name__ == "cjsg"
    assert inspect.getdoc(metodo) == "Busca de jurisprudência."


@pytest.mark.parametrize("sigla", sorted(_SCRAPERS))
def test_todo_metodo_publico_de_raspador_registrado_e_embrulhado(sigla):
    classe = _classe(sigla)
    sem_embrulho = [
        nome
        for nome in dir(classe)
        if not nome.startswith("_")
        and inspect.isfunction(inspect.getattr_static(classe, nome))
        and not getattr(inspect.getattr_static(classe, nome), "_normaliza_saida", False)
    ]

    assert sem_embrulho == []
