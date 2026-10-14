"""Texto ausente sai como ``None`` nos métodos públicos, com pandas 2 ou 3.

O pandas 3 infere colunas de texto com o tipo ``str``, em que o valor ausente
é ``NaN``. No pandas 2 a coluna sai ``object``, mas também traz ``NaN`` quando
a chave falta num registro ou vem de ``concat``/``merge``. ``BaseScraper``
embrulha os métodos públicos das subclasses e devolve essas colunas como
``object`` com ``None``, igual em toda versão do Python e do pandas.

``future.infer_string`` liga no pandas 2.3 a mesma inferência do pandas 3, o
que deixa estes testes exercitarem o caso do pandas 3 em qualquer ambiente.
"""
from __future__ import annotations

import datetime
import importlib.util
import inspect
import pickle
import threading
from collections.abc import Callable
from importlib import import_module

import numpy as np
import pandas as pd
import pytest

from juscraper import _SCRAPERS
from juscraper.aggregators.pdpj.client import PdpjScraper
from juscraper.core.base import BaseScraper
from juscraper.core.parse_utils import coerce_date_columns


def _classe(sigla: str) -> type:
    modulo, nome = _SCRAPERS[sigla].split(":")
    classe: type = getattr(import_module(modulo), nome)
    return classe


class _Mixin:
    # Faz as vezes de um mixin interno, como o do login PDPJ: só classes do
    # pacote ``juscraper`` e raspadores recebem o embrulho.
    __module__ = "juscraper._mixin_de_teste"

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

    @staticmethod
    def tabela_estatica() -> pd.DataFrame:
        return pd.DataFrame([{"texto": None}, {"texto": "b"}])

    @classmethod
    def tabela_de_classe(cls) -> pd.DataFrame:
        return pd.DataFrame([{"texto": None}, {"texto": cls.__name__}])

    def devolve(self, tabela: pd.DataFrame) -> pd.DataFrame:
        return tabela

    def _interno(self) -> pd.DataFrame:
        return pd.DataFrame([{"texto": "a"}, {"outro": "b"}])


class _Neto(_Raspador):
    def tabela(self) -> pd.DataFrame:
        return super().tabela()


@pytest.fixture
def inferencia_do_pandas_3():
    # ``future.infer_string`` existe a partir do pandas 2.1; o piso declarado é 2.0.
    try:
        pd.get_option("future.infer_string")
    except pd.errors.OptionError:
        pytest.skip("pandas sem a opção future.infer_string")
    # No pandas 2.1 e 2.2, a opção só cria colunas de texto com o pyarrow
    # instalado; sem ele, o DataFrame de teste levanta ImportError. O pandas 2.3
    # cai no armazenamento em Python. O Colab traz o pandas 2.2.
    versao = tuple(int(parte) for parte in pd.__version__.split(".")[:2])
    if versao < (2, 3) and importlib.util.find_spec("pyarrow") is None:
        pytest.skip("future.infer_string exige pyarrow no pandas < 2.3")
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
def test_staticmethod_e_classmethod_tambem_sao_normalizados():
    assert _Raspador.tabela_estatica()["texto"].tolist() == [None, "b"]
    assert _Raspador().tabela_de_classe()["texto"].tolist() == [None, "_Raspador"]


@pytest.mark.usefixtures("inferencia_do_pandas_3")
def test_tabela_recebida_nao_e_alterada():
    recebida = pd.DataFrame([{"texto": None}, {"texto": "b"}])
    tipo_antes = recebida["texto"].dtype

    devolvida = _Raspador().devolve(recebida)

    assert devolvida["texto"].tolist() == [None, "b"]
    assert recebida["texto"].dtype == tipo_antes
    assert recebida["texto"].isna().tolist() == [True, False]


def test_metodo_nao_e_embrulhado_duas_vezes():
    # ``_Neto`` herda o embrulho de ``_Raspador`` e redefine ``tabela``.
    metodos: tuple[Callable[..., object], ...] = (_Raspador.tabela, _Neto.tabela, _Neto.tabela_do_mixin, _Neto.devolve)
    for metodo in metodos:
        original = inspect.unwrap(metodo)
        assert metodo.__wrapped__ is original  # type: ignore[attr-defined]


def test_patch_no_mixin_alcanca_a_subclasse(mocker):
    mocker.patch.object(_Mixin, "tabela_do_mixin", return_value="substituto")

    assert _Raspador().tabela_do_mixin() == "substituto"


def test_metodo_embrulhado_continua_serializavel():
    # ``auth_govbr`` vem do mixin interno do login PDPJ.
    for metodo in (_Raspador.tabela, PdpjScraper.auth_govbr):
        assert pickle.loads(pickle.dumps(metodo)) is metodo


def test_metodo_privado_nao_e_embrulhado():
    # A garantia vale na fronteira pública; o parse interno devolve o que o
    # pandas produzir.
    assert not hasattr(_Raspador._interno, "__wrapped__")  # noqa: SLF001
    assert _Raspador()._interno()["texto"].isna().tolist() == [False, True]  # noqa: SLF001


def test_classe_de_fora_misturada_ao_raspador_nao_e_alterada():
    class Relatorio:
        def tabela(self) -> pd.DataFrame:
            return pd.DataFrame([{"a": "a"}, {"b": "b"}])

    class Planilha(Relatorio):
        pass

    class RaspadorComRelatorio(Relatorio, BaseScraper):
        pass

    class RaspadorThread(BaseScraper, threading.Thread):
        pass

    assert not hasattr(Relatorio.tabela, "__wrapped__")
    assert pd.isna(Planilha().tabela()["a"].tolist()[1])
    assert not hasattr(threading.Thread.start, "__wrapped__")
    assert issubclass(RaspadorComRelatorio, BaseScraper)
    assert issubclass(RaspadorThread, threading.Thread)


def test_metodo_publico_de_subclasse_do_usuario_e_normalizado():
    class MeuRaspador(BaseScraper):
        def minha_analise(self) -> pd.DataFrame:
            return pd.DataFrame([{"texto": "a"}, {"outro": "b"}])

    assert MeuRaspador("teste").minha_analise()["texto"].tolist() == ["a", None]


@pytest.mark.usefixtures("inferencia_do_pandas_3")
def test_metodo_herdado_de_mixin_tambem_e_normalizado():
    assert _Raspador().tabela_do_mixin()["texto"].tolist() == [None, "b"]


def test_coluna_object_com_nan_sai_com_none_tambem_no_pandas_2():
    # Chave ausente num registro gera ``NaN`` em coluna ``object`` mesmo no
    # pandas 2; sem a normalização, a coluna sairia com ``NaN``, como ``object``
    # no pandas 2 e como ``str`` no pandas 3.
    class Registros(BaseScraper):
        def tabela(self) -> pd.DataFrame:
            return pd.DataFrame([{"texto": "a"}, {"outro": "b"}])

    tabela = Registros("teste").tabela()

    assert tabela["texto"].tolist() == ["a", None]
    assert tabela["outro"].tolist() == [None, "b"]


def test_ausentes_de_coluna_object_viram_none_e_o_resto_fica():
    lista = [1, 2]
    original = pd.DataFrame({"valores": pd.Series([lista, np.nan, pd.NaT, pd.NA, {"a": 1}], dtype=object)})

    class Mista(BaseScraper):
        def tabela(self) -> pd.DataFrame:
            return original

    valores = Mista("teste").tabela()["valores"].tolist()

    assert valores[0] is lista
    assert valores[1:4] == [None, None, None]
    assert valores[4] == {"a": 1}


@pytest.mark.parametrize(
    "valores",
    [
        [datetime.date(2024, 3, 10), pd.NaT, np.nan],
        [datetime.datetime(2024, 3, 10, 12, 0, tzinfo=datetime.UTC), pd.NaT],
        [datetime.time(12, 0), pd.NaT],
    ],
)
def test_coluna_object_de_datas_mantem_nat(valores):
    # ``pd.to_datetime(...).dt.date``, que os parsers usam, dá coluna ``object``
    # de ``date`` com ``NaT`` no ausente; ``.year`` sobre ``None`` quebraria.
    original = pd.DataFrame({"data": pd.Series(valores, dtype=object)})

    class Datas(BaseScraper):
        def tabela(self) -> pd.DataFrame:
            return original

    assert Datas("teste").tabela() is original


def test_coluna_de_datas_do_parser_continua_com_nat():
    class Datas(BaseScraper):
        def tabela(self) -> pd.DataFrame:
            return coerce_date_columns(pd.DataFrame({"data": ["2024-03-10", None]}), ["data"])

    valores = Datas("teste").tabela()["data"].tolist()

    assert valores[0] == datetime.date(2024, 3, 10)
    assert valores[1] is pd.NaT


def test_coluna_object_ja_com_none_nao_gera_copia():
    original = pd.DataFrame({"texto": pd.Series([None, "b"], dtype=object)})

    class SemTroca(BaseScraper):
        def tabela(self) -> pd.DataFrame:
            return original

    assert SemTroca("teste").tabela() is original


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
    sem_embrulho = []
    for nome in dir(classe):
        if nome.startswith("_"):
            continue
        atributo = inspect.getattr_static(classe, nome)
        funcao = atributo.__func__ if isinstance(atributo, (staticmethod, classmethod)) else atributo
        if inspect.isfunction(funcao) and not getattr(funcao, "_normaliza_saida", False):
            sem_embrulho.append(nome)

    assert sem_embrulho == []
