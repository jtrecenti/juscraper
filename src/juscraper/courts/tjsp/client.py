"""
Main scraper for Tribunal de Justica de Sao Paulo (TJSP).
"""
import os
import tempfile
from typing import Union, List, Literal
import logging
import shutil
import warnings
import urllib3
import requests

from ...core.base import BaseScraper

from .cpopg_download import cpopg_download_html, cpopg_download_api
from .cpopg_parse import get_cpopg_download_links, cpopg_parse_manager

from .cposg_download import cposg_download_html, cposg_download_api
from .cposg_parse import cposg_parse_manager

from .cjsg_download import cjsg_download as cjsg_download_mod
from .cjsg_parse import cjsg_n_pags, cjsg_parse_manager

from .cjpg_download import cjpg_download as cjpg_download_mod
from .cjpg_parse import cjpg_n_pags, cjpg_parse_manager

logger = logging.getLogger('juscraper.tjsp')

warnings.filterwarnings('ignore', category=urllib3.exceptions.InsecureRequestWarning)

class TJSPScraper(BaseScraper):
    """Main scraper for Tribunal de Justica de Sao Paulo."""

    def __init__(
        self,
        verbose: int = 0,
        download_path: str | None = None,
        sleep_time: float = 0.5,
        **kwargs
    ):
        """
        Initializes the scraper for TJSP.

        Args:
            verbose (int, optional): Verbosity level. Default is 0 (no logging).
            download_path (str, optional): Path to save downloaded files. Default is None (uses temporary directory).
            sleep_time (float, optional): Time to wait between requests. Default is 0.5 seconds.
            **kwargs: Argumentos adicionais.
        """
        super().__init__("TJSP")
        self.session = requests.Session()
        self.u_base = 'https://esaj.tjsp.jus.br/'
        self.api_base = 'https://api.tjsp.jus.br/'
        self.set_verbose(verbose)
        self.set_download_path(download_path)
        self.sleep_time = sleep_time
        self.args = kwargs
        self.method = None

    def set_download_path(self, path: str | None = None):
        """
        Sets the base directory for saving downloaded files.

        Args:
            path (str, optional): Path to save downloaded files. Default is None (uses temporary directory).
        """
        if path is None:
            path = tempfile.mkdtemp()
        self.download_path = path

    def set_method(self, method: Literal['html', 'api']):
        """
        Sets the method for accessing TJSP data.

        Args:
            method: Literal['html', 'api']. The methods supported are 'html' and 'api'.

        Raises:
            Exception: If the method is not 'html' or 'api'.
        """
        if method not in ['html', 'api']:
            raise ValueError(
                f"Método {method} nao suportado."
                "Os métodos suportados são 'html' e 'api'."
            )
        self.method = method

    # cpopg ------------------------------------------------------------------
    def cpopg(self, id_cnj: Union[str, List[str]], method: Literal['html', 'api'] = 'html'):
        """
        Scrapes a process from Primeiro Grau (CPOPG).
        """
        self.set_method(method)
        self.cpopg_download(id_cnj, method)
        result = self.cpopg_parse(self.download_path)
        shutil.rmtree(self.download_path)
        return result

    def cpopg_download(
        self,
        id_cnj: Union[str, List[str]],
        method: Literal['html', 'api'] = 'html'
    ):
        """Downloads a process from Primeiro Grau (CPOPG).

        Args:
            id_cnj: string with the CNJ of the process, or list of strings with CNJs.
            method: Literal['html', 'api']. The methods supported are 'html' and 'api'. The default is 'html'.

        Raises:
            Exception: If the method passed as parameter is not 'html' or 'api'.
        """
        self.set_method(method)
        path = self.download_path
        if isinstance(id_cnj, str):
            id_cnj = [id_cnj]
        if self.method == 'html':
            def get_links_callback(response):
                return get_cpopg_download_links(response)
            cpopg_download_html(
                id_cnj_list=id_cnj,
                session=self.session,
                u_base=self.u_base,
                download_path=path,
                sleep_time=self.sleep_time,
                get_links_callback=get_links_callback
            )
        elif self.method == 'api':
            cpopg_download_api(
                id_cnj_list=id_cnj,
                session=self.session,
                api_base=self.api_base,
                download_path=path
            )
        else:
            raise ValueError(f"Método '{method}' não é suportado.")

    def cpopg_parse(self, path: str):
        """
        Wrapper for parsing downloaded files from CPOPG.
        """
        return cpopg_parse_manager(path)

    # cposg ------------------------------------------------------------------

    def cposg(self, id_cnj: str, method: Literal['html', 'api'] = 'html'):
        """
        Orchestrates the download and parsing of processes from Segundo Grau (CPOSG).
        """
        self.set_method(method)
        path = self.download_path
        self.cposg_download(id_cnj, method)
        result = self.cposg_parse(path)
        if os.path.exists(path):
            shutil.rmtree(path)
        else:
            logger.warning("[TJSP] Aviso: diretório %s não existe e não pôde ser removido.", path)
        return result

    def cposg_download(self, id_cnj: Union[str, list], method: Literal['html', 'api'] = 'html'):
        """
        Downloads processes from Segundo Grau (CPOSG), via HTML or API, using modularized functions.
        """
        self.set_method(method)
        if isinstance(id_cnj, str):
            id_cnj = [id_cnj]
        if self.method == 'html':
            cposg_download_html(
                id_cnj_list=id_cnj,
                session=self.session,
                u_base=self.u_base,
                download_path=self.download_path,
                sleep_time=self.sleep_time
            )
        elif self.method == 'json':
            cposg_download_api(
                id_cnj_list=id_cnj,
                session=self.session,
                api_base=self.api_base,
                download_path=self.download_path,
                sleep_time=self.sleep_time
            )
        else:
            raise ValueError(f"Método '{method}' não é suportado.")

    def cposg_parse(self, path: str):
        """
        Wrapper for parsing downloaded files from CPOSG.
        """
        return cposg_parse_manager(path)

    # cjsg ----------------------------------------------------------------------
    def cjsg(
        self,
        pesquisa: str,
        ementa: str | None = None,
        classe: str | None = None,
        assunto: str | None = None,
        comarca: str | None = None,
        orgao_julgador: str | None = None,
        data_inicio: str | None = None,
        data_fim: str | None = None,
        baixar_sg: bool = True,
        tipo_decisao: str | Literal['acordao', 'monocratica'] = 'acordao',
        paginas: range | None = None,
    ):
        """
        Orchestrates the download and parsing of processes from CJSG.
        """
        path_result = self.cjsg_download(
            pesquisa=pesquisa,
            ementa=ementa,
            classe=classe,
            assunto=assunto,
            comarca=comarca,
            orgao_julgador=orgao_julgador,
            data_inicio=data_inicio,
            data_fim=data_fim,
            baixar_sg=baixar_sg,
            tipo_decisao=tipo_decisao,
            paginas=paginas,
        )
        data_parsed = self.cjsg_parse(path_result)
        # delete folder
        shutil.rmtree(path_result)
        return data_parsed

    def cjsg_download(
        self,
        pesquisa: str,
        ementa: str | None = None,
        classe: str | None = None,
        assunto: str | None = None,
        comarca: str | None = None,
        orgao_julgador: str | None = None,
        data_inicio: str | None = None,
        data_fim: str | None = None,
        baixar_sg: bool = True,
        tipo_decisao: str | Literal['acordao', 'monocratica'] = 'acordao',
        paginas: range | None = None,
    ):
        """
        Downloads the HTML files of the pages of results of the
        Second Stage Judgment Consultation (CJSG).

        Args:
            pesquisa (str): Search term.
            ementa (str, optional): Filter by text of the ementa.
            classe: Class of the process.
            assunto: Subject of the process.
            comarca: Court of the process.
            orgao_julgador: Court of appeal of the process.
            data_inicio: Start date of the process.
            data_fim: End date of the process.
            baixar_sg (bool): If True, also downloads from Second Stage.
            tipo_decisao (str): 'acordao' or 'monocratica'.
            paginas (range, optional): Range of pages to download.
        
        NOTE: range(0, n) downloads pages 1 to n (inclusive), following
        the user's expectation (example: range(0,3) downloads pages 1, 2 and 3).
        """
        return cjsg_download_mod(
            pesquisa=pesquisa,
            download_path=self.download_path,
            u_base=self.u_base,
            sleep_time=self.sleep_time,
            verbose=self.verbose,
            ementa=ementa,
            classe=classe,
            assunto=assunto,
            comarca=comarca,
            orgao_julgador=orgao_julgador,
            data_inicio=data_inicio,
            data_fim=data_fim,
            baixar_sg=baixar_sg,
            tipo_decisao=tipo_decisao,
            paginas=paginas,
            get_n_pags_callback=cjsg_n_pags,
        )

    # cjpg ----------------------------------------------------------------------
    def cjpg(
        self,
        pesquisa: str = '',
        classes: list[str] | None = None,
        assuntos: list[str] | None = None,
        varas: list[str] | None = None,
        id_processo: str | None = None,
        data_inicio: str | None = None,
        data_fim: str | None = None,
        paginas: range | None = None,
    ):
        """
        Orchestrates the download and parsing of processes from CJPG.

        Args:
            pesquisa (str): The search term. Default is "" (empty string).
            classes (list[str], optional): List of classes of the process. Default is None.
            assuntos (list[str], optional): List of subjects of the process. Default is None.
            varas (list[str], optional): List of varas of the process. Default is None.
            id_processo (str, optional): ID of the process. Default is None.
            data_inicio (str, optional): Start date of the search. Default is None.
            data_fim (str, optional): End date of the search. Default is None.
            paginas (range, optional): Range of pages to download. Default is None.
        """
        path_result = self.cjpg_download(
            pesquisa=pesquisa,
            classes=classes,
            assuntos=assuntos,
            varas=varas,
            id_processo=id_processo,
            data_inicio=data_inicio,
            data_fim=data_fim,
            paginas=paginas
        )
        data_parsed = self.cjpg_parse(path_result)
        # delete folder
        shutil.rmtree(path_result)
        return data_parsed

    def cjpg_download(
        self,
        pesquisa: str,
        classes: list[str] | None = None,
        assuntos: list[str] | None = None,
        varas: list[str] | None = None,
        id_processo: str | None = None,
        data_inicio: str | None = None,
        data_fim: str | None = None,
        paginas: range | None = None,
    ):
        """
        Downloads the processes from the TJSP jurisprudence.

        Args:
            pesquisa (str): The search term.
            classes (list[str], optional): List of classes of the process. Default is None.
            assuntos (list[str], optional): List of subjects of the process. Default is None.
            varas (list[str], optional): List of varas of the process. Default is None.
            id_processo (str, optional): ID of the process. Default is None.
            data_inicio (str, optional): Start date of the search. Default is None.
            data_fim (str, optional): End date of the search. Default is None.
            paginas (range, optional): Pages to download. Default is None.
        """
        def get_n_pags_callback(r0):
            # r0 pode ser requests.Response ou HTML string
            html = r0.content if hasattr(r0, 'content') else r0
            return cjpg_n_pags(html)
        return cjpg_download_mod(
            pesquisa=pesquisa,
            session=self.session,
            u_base=self.u_base,
            download_path=self.download_path,
            sleep_time=self.sleep_time,
            classes=classes,
            assuntos=assuntos,
            varas=varas,
            id_processo=id_processo,
            data_inicio=data_inicio,
            data_fim=data_fim,
            paginas=paginas,
            get_n_pags_callback=get_n_pags_callback
        )

    def cjpg_parse(self, path: str):
        """
        Wrapper for parsing downloaded files from CJPG.
        """
        return cjpg_parse_manager(path)

    def cjsg_parse(self, path: str):
        """
        Wrapper for parsing downloaded files from CJSG.
        """
        return cjsg_parse_manager(path)
