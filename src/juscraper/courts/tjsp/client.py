"""
Modulo client.py: Scraper principal para o Tribunal de Justiça de São Paulo (TJSP).
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
    """Raspador para o Tribunal de Justiça de São Paulo."""

    def __init__(
        self,
        verbose: int = 0,
        download_path: str | None = None,
        sleep_time: float = 0.5,
        **kwargs
    ):
        """
        Inicializa o scraper para o TJSP.

        Args:
            verbose (int, opcional): Nível de verbosidade. Padrão é 0 (nenhum log).
            download_path (str, opcional): Caminho para salvar os arquivos baixados. Padrão é None (usa temporário).
            sleep_time (float, opcional): Tempo de espera entre requisições. Padrão é 0.5 segundos.
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
        Define o diretório base para salvar os arquivos baixados.

        Args:
            path (str, opcional): Caminho para salvar os arquivos baixados. Padrão é None (usa temporário).
        """
        if path is None:
            path = tempfile.mkdtemp()
        self.download_path = path

    def set_method(self, method: Literal['html', 'api']):
        """Define o método para acesso aos dados do TJSP.

        Args:
            method: Literal['html', 'api']. Os métodos suportados são 'html' e 'api'.

        Raises:
            Exception: Se o método passado como parâmetro não for 'html' nem 'api'.
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
        Busca um processo na consulta de processos originários do primeiro grau.
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
        """Baixa um processo na consulta de processos originários do primeiro grau.

        Args:
            id_cnj: string com o CNJ do processo, ou lista de strings com vários CNJs.
            method: Literal['html', 'api']. Os métodos suportados são 'html' e 'api'. O padrão é 'html'.

        Raises:
            Exception: Se o método passado como parâmetro não for 'html' nem 'api'.
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
        Wrapper para parsing de arquivos baixados do CPOPG.
        """
        return cpopg_parse_manager(path)

    # cposg ------------------------------------------------------------------

    def cposg(self, id_cnj: str, method: Literal['html', 'api'] = 'html'):
        """
        Orquestra o download e parsing de processos do CPOSG.
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
        Baixa processos do CPOSG, via HTML ou API, utilizando funções modularizadas.
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
        Wrapper para parsing de arquivos baixados do CPOSG.
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
        Orquestra o download e parsing de processos do CJSG.
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
            paginas=paginas
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
        Baixa os arquivos HTML das páginas de resultados da
        Consulta de Julgados do Segundo Grau (CJSG).

        Args:
            pesquisa (str): Termo de busca.
            ementa (str, opcional): Filtro por texto da ementa.
            classe: Classe do processo.
            assunto: Assunto do processo.
            comarca: Comarca do processo.
            orgao_julgador: Orgão julgador do processo.
            data_inicio: Data de início do processo.
            data_fim: Data de fim do processo.
            baixar_sg (bool): Se True, baixa também do segundo grau.
            tipo_decisao (str): 'acordao' ou 'monocratica'.
            paginas (range, opcional): Intervalo de páginas a baixar.
        
        ATENÇÃO: range(0, n) baixa as páginas 1 até n (inclusive), seguindo
        a expectativa do usuário (exemplo: range(0,3) baixa as páginas 1, 2 e 3).
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
            get_n_pags_callback=cjsg_n_pags
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
        Realiza uma busca por jurisprudencia com base nos parametros fornecidos,
        baixa os resultados, os analisa e retorna os dados analisados.

        Args:
            pesquisa (str): A consulta para a jurisprudencia. Padrão "" (string vazia)
            classes (list[str], opcional): Lista de classes do processo. Padrao None.
            assuntos (list[str], opcional): Lista de assuntos do processo. Padrao None.
            varas (list[str], opcional): Lista de varas do processo. Padrao None.
            id_processo (str, opcional): O ID do processo. Padrao None.
            data_inicio (str, opcional): A data de inicio para a busca. Padrao None.
            data_fim (str, opcional): A data de fim para a busca. Padrao None.
            paginas (range, opcional): A faixa de paginas a serem buscadas. Padrao None.

        Retorna:
            pd.DataFrame: Os dados analisados da jurisprudencia baixada.
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
        Baixa os processos da jurisprudência do TJSP.

        Args:
            pesquisa (str): A consulta para a jurisprudência.
            classes (list[str], opcional): Lista de classes do processo. Padrão None.
            assuntos (list[str], opcional): Lista de assuntos do processo. Padrão None.
            varas (list[str], opcional): Lista de varas do processo. Padrão None.
            id_processo (str, opcional): ID do processo. Padrão None.
            data_inicio (str, opcional): Data inicial da busca. Padrão None.
            data_fim (str, opcional): Data final da busca. Padrão None.
            paginas (range, opcional): Páginas a baixar. Padrão None.
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
        Wrapper para parsing dos arquivos baixados da Cjpg.
        """
        return cjpg_parse_manager(path)

    def cjsg_parse(self, path: str):
        """
        Parseia os arquivos baixados da segunda instância (cjsg) e retorna um DataFrame com
        as informações dos processos.
        """
        return cjsg_parse_manager(path)
