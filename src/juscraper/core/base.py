"""
Base scraper class for court data extraction.
"""
import logging
import tempfile
import threading
from abc import ABC
from pathlib import Path
from typing import ClassVar

logger = logging.getLogger("juscraper.core.base")

# Serializa a criação sob demanda de ``download_path``: sem ela, threads que
# leem o atributo pela primeira vez ao mesmo tempo criariam um diretório
# cada, e só o último ficaria gravado. Fica no módulo, e não na instância,
# porque um ``Lock`` como atributo impediria ``pickle`` e ``copy`` do raspador.
_TRAVA_DIRETORIO_TEMPORARIO = threading.Lock()


class BaseScraper(ABC):
    """Base scraper class for court data extraction."""

    # Prefixo do diretório temporário criado quando o usuário não informa
    # ``download_path``. ``None`` usa o padrão do ``tempfile``.
    PREFIXO_DIRETORIO_TEMPORARIO: ClassVar[str | None] = None

    # ``None`` enquanto ninguém informou caminho nem leu ``download_path``.
    _download_path: str | None

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
