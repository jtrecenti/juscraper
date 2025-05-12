from .base_scraper import BaseScraper
from .utils import clean_cnj, split_cnj, format_cnj
import requests
import tempfile
from bs4 import BeautifulSoup
import urllib3
import warnings
import os
import pandas as pd
from urllib.parse import parse_qs, urlparse
import glob
import re
from datetime import datetime
import shutil
from tqdm import tqdm
from typing import Union, List, Literal
import time
import unidecode
import json

warnings.filterwarnings('ignore', category=urllib3.exceptions.InsecureRequestWarning)

class comunicaCNJ_Scraper(BaseScraper):
    """Raspador para o site de Comunicações Processuais do Conselho Nacional de Justiça."""

    def __init__(self, verbose = 1, download_path = None, sleep_time = 2, **kwargs): # sleep_time = 0.5 causa aviso de "Too Many Requests"
        super().__init__("ComunicaCNJ")
        self.session = requests.Session()
        #self.u_base = 'https://comunica.pje.jus.br/'
        self.api_base = 'https://comunicaapi.pje.jus.br/api/v1/comunicacao'
        self.set_verbose(verbose)
        self.set_download_path(download_path)
        self.sleep_time = sleep_time
    
    def set_download_path(self, path: str | None = None):
        if path is None:
            path = tempfile.mkdtemp()
        self.download_path = path
    
    def cjpg(
        self,
        pesquisa: str,
        #classe: str | None = None,
        #assunto: str | None = None,
        #comarca: str | None = None,
        #id_processo: str | None = None,
        data_inicio: str | None = None,
        data_fim: str | None = None,
        paginas: range | None = None,
    ):
        """
        Realiza uma busca por jurisprudencia com base nos parametros fornecidos, baixa os resultados,
        os analisa e retorna os dados analisados.

        Args:
            pesquisa (str): A consulta para a jurisprudencia.
            classe (str, opcional): A classe do processo. Padrao None.
            assunto (str, opcional): O assunto do processo. Padrao None.
            comarca (str, opcional): A comarca do processo. Padrao None.
            id_processo (str, opcional): O ID do processo. Padrao None.
            data_inicio (str, opcional): A data de inicio para a busca. Padrao None.
            data_fim (str, opcional): A data de fim para a busca. Padrao None.
            paginas (range, opcional): A faixa de paginas a serem buscadas. Padrao None.

        Retorna:
            pd.DataFrame: Os dados analisados da jurisprudencia baixada.
        """
        print(self.sleep_time)
        path_result = self.cjpg_download(pesquisa, data_inicio, data_fim, paginas) # , classe, assunto, comarca, id_processo,
        data_parsed = self.cjpg_parse(path_result)
        shutil.rmtree(path_result)
        return data_parsed
    
    def cjpg_download(
        self, 
        pesquisa: str,
        #classe: str | None = None,
        #assunto: str | None = None,
        #comarca: str | None = None,
        #id_processo: str | None = None,
        data_inicio: str | None = '2021-01-10',
        data_fim: str | None = None,
        paginas: range | None = None,
    ):
        """
        Baixa os processos da jurisprud ncia do TJSP

        Args:
            pesquisa (str): A consulta para a jurisprud ncia.
            classe (str, opcional): A classe do processo. Padr o None.
            assunto (str, opcional): O assunto do processo. Padr o None.
            comarca (str, opcional): A comarca do processo. Padr o None.
            id_processo (str, opcional): O ID do processo. Padr o None.
            data_inicio (str, opcional): A data de in cio para a busca. Padr o None.
            data_fim (str, opcional): A data de fim para a busca. Padr o None.
            paginas (range, opcional): A faixa de p ginas a serem buscadas. Padr o None.

        Retorna:
            str: O caminho da pasta onde os processos foram baixados.
        """

        # query de busca
        query = {
                'itensPorPagina': 5,
                'texto': pesquisa,
                'dataDisponibilizacaoInicio': data_inicio
            }

        # fazendo a busca
        r0 = self.session.get(
            self.api_base,
            params=query
        )
        
        # calcula total de páginas
        n_pags = self._cjpg_n_pags(r0)
        
        # Se paginas for None, definir range para todas as páginas
        if paginas is None:
            paginas = range(1, n_pags + 1)
        else:
            start, stop, step = paginas.start, min(paginas.stop, n_pags + 1), paginas.step
            paginas = range(start, stop, step)

        if self.verbose:
            print(f"Total de páginas: {n_pags}")
            print(f"Paginas a serem baixadas: {list(paginas)}")

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        path = f"{self.download_path}/cjpg/{timestamp}"
        if not os.path.isdir(path):
            os.makedirs(path)

        for pag in tqdm(paginas, desc="Baixando documentos"):
            time.sleep(self.sleep_time)

            query = {
                'pagina': pag,
                'itensPorPagina': 5,
                'texto': pesquisa,
                'dataDisponibilizacaoInicio': data_inicio
            }
            if data_fim:
                query['dataDisponibilizacaoFim'] = data_fim

            r = self.session.get(self.api_base, params=query) # sending the parameters.

            file_name = f"{path}/cjpg_{pag:05d}.json"
            with open(file_name, 'w', encoding='utf-8') as f:
                f.write(r.text)
        
        return path
   
    def _cjpg_n_pags(self, r0):
        contagem = r0.json()['count']
        return contagem // 5 + 1
    
    def cjpg_parse(self, path: str):
        """
        Parseia os arquivos baixados com a função cjpg e retorna um DataFrame com
        as informações dos processos.

        Parameters
        ----------
        path : str
            Caminho do arquivo ou da pasta que contém os arquivos baixados.

        Returns
        -------
        result : pd.DataFrame
            Dataframe com as informações dos processos.
        """
        if os.path.isfile(path):
            result = [self._cjpg_parse_single(path)]
        else:
            result = []
            arquivos = glob.glob(f"{path}/**/*.json", recursive=True)
            arquivos = [f for f in arquivos if os.path.isfile(f)]
            for file in tqdm(arquivos, desc="Processando documentos"):
                try:
                    single_result = self._cjpg_parse_single(file)
                except Exception as e:
                    print(f"Error processing {file}: {e}")
                    single_result = None
                    continue
                if single_result is not None:
                    result.append(single_result)
        result = pd.concat(result, ignore_index=True)
        return result
    
    def _cjpg_parse_single(self, path: str):
        with open(path, 'r', encoding='utf-8') as f:
            dados = json.load(f)
        
        lista_infos = []

        infos_processos = dados['items']

        for processo in infos_processos:
            lista_infos.append(processo)

        return pd.DataFrame(lista_infos)
    
    def cpopg(self, id_cnj: Union[str, List[str]], method = 'html'):
        """Método não aplicável ao CNJ"""
        pass
    
    def cposg(self, id_cnj: str):
        """Método não aplicável ao CNJ"""
        pass

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
        """Método não aplicável ao CNJ"""
        pass
    
