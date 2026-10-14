"""
Base scraper class for court data extraction.
"""
import functools
import inspect
import logging
import tempfile
import threading
from abc import ABC
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar, ParamSpec, TypeVar, cast

import pandas as pd

logger = logging.getLogger("juscraper.core.base")

# Serializa a criação sob demanda de ``download_path``: sem ela, threads que
# leem o atributo pela primeira vez ao mesmo tempo criariam um diretório
# cada, e só o último ficaria gravado. Fica no módulo, e não na instância,
# porque um ``Lock`` como atributo impediria ``pickle`` e ``copy`` do raspador.
_TRAVA_DIRETORIO_TEMPORARIO = threading.Lock()


def _coluna_com_ausente_a_trocar(coluna: pd.Series) -> bool:
    tipo = coluna.dtype
    if isinstance(tipo, pd.StringDtype):
        return tipo.na_value is not pd.NA
    if tipo == object:
        ausentes = coluna.isna()
        return bool(ausentes.any()) and any(valor is not None for valor in coluna[ausentes])
    return False


def _texto_ausente_como_none(tabela: pd.DataFrame) -> pd.DataFrame:
    """Devolve colunas de texto como ``object``, com ``None`` no lugar de ausente.

    Dois casos entram. O tipo ``str`` do pandas 3, em que o ausente é ``NaN``,
    vira ``object``. E coluna ``object`` com ``NaN``, ``NaT`` ou ``pd.NA``, que
    o pandas 2 também produz quando a chave falta num registro ou vem de
    ``concat``/``merge``, troca esses valores por ``None``. Assim a mesma
    chamada devolve o mesmo marcador em toda versão do Python e do pandas.
    Fica de fora o ``"string"`` explícito, que usa ``pd.NA`` desde o pandas 1 e
    é pedido de propósito, e as colunas numéricas e de data, em que ``NaN`` e
    ``NaT`` são o ausente do próprio tipo. Sem nada a trocar, a tabela volta a
    mesma, sem cópia. A troca é por posição, para valer também com nomes de
    coluna repetidos.
    """
    posicoes = [
        posicao for posicao in range(tabela.shape[1]) if _coluna_com_ausente_a_trocar(tabela.iloc[:, posicao])
    ]
    if not posicoes:
        return tabela
    tabela = tabela.copy()
    for posicao in posicoes:
        coluna = tabela.iloc[:, posicao].astype(object)
        tabela.isetitem(posicao, coluna.where(coluna.notna(), None))
    return tabela


_P = ParamSpec("_P")
_R = TypeVar("_R")

# Atributo que marca um método já embrulhado, para não embrulhar duas vezes.
_MARCA_SAIDA_NORMALIZADA = "_normaliza_saida"


def _normalizar_saida(resultado: object) -> object:
    if isinstance(resultado, pd.DataFrame):
        return _texto_ausente_como_none(resultado)
    # ``TJSPScraper.cpopg`` devolve um dicionário de tabelas.
    if isinstance(resultado, dict) and any(isinstance(valor, pd.DataFrame) for valor in resultado.values()):
        return {
            chave: _texto_ausente_como_none(valor) if isinstance(valor, pd.DataFrame) else valor
            for chave, valor in resultado.items()
        }
    return resultado


def _com_saida_normalizada(metodo: Callable[_P, _R]) -> Callable[_P, _R]:
    @functools.wraps(metodo)
    def embrulhado(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        return cast("_R", _normalizar_saida(metodo(*args, **kwargs)))

    setattr(embrulhado, _MARCA_SAIDA_NORMALIZADA, True)
    return embrulhado


def _embrulhar_atributo(atributo: object) -> object | None:
    """Devolve o atributo embrulhado, ou ``None`` se não for método a embrulhar."""
    if isinstance(atributo, (staticmethod, classmethod)):
        funcao = atributo.__func__
        if inspect.isfunction(funcao) and not getattr(funcao, _MARCA_SAIDA_NORMALIZADA, False):
            return type(atributo)(_com_saida_normalizada(funcao))
        return None
    if inspect.isfunction(atributo) and not getattr(atributo, _MARCA_SAIDA_NORMALIZADA, False):
        return _com_saida_normalizada(atributo)
    return None


class BaseScraper(ABC):
    """Base scraper class for court data extraction."""

    # Prefixo do diretório temporário criado quando o usuário não informa
    # ``download_path``. ``None`` usa o padrão do ``tempfile``.
    PREFIXO_DIRETORIO_TEMPORARIO: ClassVar[str | None] = None

    # ``None`` enquanto ninguém informou caminho nem leu ``download_path``.
    _download_path: str | None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Embrulha os métodos públicos para que texto ausente saia como ``None``.

        Vale para todo método público alcançável pela classe, inclusive
        ``staticmethod``, ``classmethod`` e os herdados de mixins que não
        derivam de ``BaseScraper``. O embrulho é gravado na classe que define
        o método, e não na subclasse: assim ``mock.patch.object`` no mixin
        continua alcançando as subclasses pelo MRO, e o ``pickle`` do método,
        que procura a função pelo ``__qualname__``, encontra o mesmo objeto.
        O marcador ``_normaliza_saida`` impede embrulhar duas vezes.
        """
        super().__init_subclass__(**kwargs)
        for nome in dir(cls):
            if nome.startswith("_"):
                continue
            dono = next(classe for classe in cls.__mro__ if nome in vars(classe))
            embrulhado = _embrulhar_atributo(vars(dono)[nome])
            if embrulhado is not None:
                setattr(dono, nome, embrulhado)

    def __init__(self, tribunal_name: str):
        self.tribunal_name = tribunal_name
        self.verbose = 0
        self._download_path = None

    @property
    def download_path(self) -> str:
        """Diretório de download.

        Sem caminho informado, o diretório temporário é criado na primeira
        leitura, e não na construção: a maior parte dos raspadores nunca
        grava nele, e um ``mkdtemp`` por construção deixava um diretório
        vazio para trás a cada instância.
        """
        if self._download_path is None:
            with _TRAVA_DIRETORIO_TEMPORARIO:
                # Segunda checagem: outra thread pode ter criado o diretório
                # enquanto esta esperava a trava.
                if self._download_path is None:
                    self._download_path = tempfile.mkdtemp(prefix=self.PREFIXO_DIRETORIO_TEMPORARIO)
                    if self.verbose:
                        logger.info(
                            "Caminho de download definido como '%s'.",
                            self._download_path
                        )
        return self._download_path

    @download_path.setter
    def download_path(self, path: str) -> None:
        self._download_path = path

    def set_verbose(self, verbose: int):
        """Set the verbosity level of the scraper.

        Args:
            verbose (int): Verbosity level.
        """
        self.verbose = verbose

    def set_download_path(self, path: str | None) -> None:
        """Set the download path. If None, a temporary directory is created on first use."""
        if path is None:
            self._download_path = None
            return
        if not Path(path).is_dir():
            if self.verbose:
                logger.info(
                    "O caminho de download '%s' não é um diretório. Criando esse diretório...",
                    path
                )
            Path(path).mkdir(parents=True, exist_ok=True)
        self._download_path = path
        if self.verbose:
            logger.info(
                "Caminho de download definido como '%s'.",
                path
            )
