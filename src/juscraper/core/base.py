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


def _texto_ausente_como_none(tabela: pd.DataFrame) -> pd.DataFrame:
    """Devolve as colunas do tipo ``str`` do pandas 3 como ``object``, com ``None``.

    O pandas 3 infere colunas de texto com o tipo ``str``, em que o ausente é
    ``NaN``; até o pandas 2 elas saíam como ``object``, com ``None``. Só o
    ``str`` com ausente ``NaN`` é tocado: o ``"string"`` explícito usa
    ``pd.NA`` desde o pandas 1, e quem o pede quer esse tipo. A troca é por
    posição, para valer também com nomes de coluna repetidos.
    """
    posicoes = [
        posicao
        for posicao, tipo in enumerate(tabela.dtypes)
        if isinstance(tipo, pd.StringDtype) and tipo.na_value is not pd.NA
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


class BaseScraper(ABC):
    """Base scraper class for court data extraction."""

    # Prefixo do diretório temporário criado quando o usuário não informa
    # ``download_path``. ``None`` usa o padrão do ``tempfile``.
    PREFIXO_DIRETORIO_TEMPORARIO: ClassVar[str | None] = None

    # ``None`` enquanto ninguém informou caminho nem leu ``download_path``.
    _download_path: str | None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Embrulha os métodos públicos para que texto ausente saia como ``None``.

        Vale para todo método público alcançável pela classe, inclusive os
        herdados de mixins que não derivam de ``BaseScraper``: esses recebem
        o embrulho na subclasse, sem tocar o mixin. O marcador
        ``_normaliza_saida`` impede embrulhar duas vezes o que veio da base.
        """
        super().__init_subclass__(**kwargs)
        for nome in dir(cls):
            if nome.startswith("_"):
                continue
            atributo = inspect.getattr_static(cls, nome)
            if inspect.isfunction(atributo) and not getattr(atributo, _MARCA_SAIDA_NORMALIZADA, False):
                setattr(cls, nome, _com_saida_normalizada(atributo))

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
