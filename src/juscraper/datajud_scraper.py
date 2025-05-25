"""
Raspador para a API Pública do Datajud, com paginação automática, tratamento de erros e logging.
"""
import os
import tempfile
import logging
import json
from collections import defaultdict
from typing import List, Optional, Union
import requests
import pandas as pd
from .base_scraper import BaseScraper
from .utils import clean_cnj, ID_JUSTICA_TRIBUNAL_TO_ALIAS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

class DatajudScraper(BaseScraper):
    """
    Raspador para a API Pública do Datajud.
    """
    def cpopg(self, id_cnj: Union[str, List[str]]):
        """
        Busca um processo na consulta de processos originários do 
        primeiro grau (não suportado pelo DatajudScraper).
        """
        raise NotImplementedError("DatajudScraper não implementa cpopg. Use listar_processos.")

    def cposg(self, id_cnj: Union[str, List[str]]):
        """
        Busca um processo na consulta de processos originários 
        do segundo grau (não suportado pelo DatajudScraper).
        """
        raise NotImplementedError("DatajudScraper não implementa cposg. Use listar_processos.")

    def cjsg(self, query: str):
        """
        Busca jurisprudência na consulta de julgados do segundo grau 
        (não suportado pelo DatajudScraper).
        """
        raise NotImplementedError("DatajudScraper não implementa cjsg. Use listar_processos.")
    DEFAULT_API_KEY = "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="

    def __init__(
        self,
        api_key: Optional[str] = None,
        verbose: int = 1,
        download_path: Optional[str] = None,
        sleep_time: float = 0.5,
    ):
        """
        Inicializa o DatajudScraper.
        Parâmetros:
            api_key: chave de acesso para a API pública do Datajud (Authorization: APIKey ...). 
              Se não informado, usa a chave pública padrão.
            verbose: nível de verbosidade
            download_path: caminho para salvar arquivos temporários
            sleep_time: tempo de espera entre requisições
        """
        super().__init__("DATAJUD")
        self.session = requests.Session()
        self.api_key = api_key or self.DEFAULT_API_KEY
        self.verbose = verbose
        self.sleep_time = sleep_time
        self.set_download_path(download_path)

    def set_download_path(self, path: Optional[str] = None):
        if path is None:
            path = tempfile.mkdtemp()
        self.download_path = path

    def listar_processos(
        self,
        numero_processo: Optional[Union[str, List[str]]] = None,
        tribunal: Optional[str] = None,
        justica: Optional[str] = "8",
        ano_ajuizamento: Optional[int] = None,
        classe: Optional[str] = None,
        assuntos: Optional[List[str]] = None,
        mostrar_movs: bool = False,
        paginas: Optional[range] = None,
    ) -> pd.DataFrame:
        """
        Lista processos do Datajud, com suporte a múltiplos filtros e paginação automática.
        Parâmetros:
            numero_processo: número CNJ ou lista
            tribunal: sigla, id ou nome (opcional)
            justica: código da justiça (ex: "8" para estadual, padrão)
        """
        dfs = []
        tamanho_pagina = 1000
        # Detecta tribunal/justica pelo número do processo se fornecido
        if numero_processo:
            if isinstance(numero_processo, list):
                # Agrupa cada processo pelo alias correto
                processos_por_alias = defaultdict(list)
                for num in numero_processo:
                    num_limpo = clean_cnj(num)
                    if len(num_limpo) == 20:
                        id_justica = num_limpo[13]
                        id_tribunal = num_limpo[14:16]
                        alias = ID_JUSTICA_TRIBUNAL_TO_ALIAS.get((id_justica, id_tribunal))
                        if alias:
                            processos_por_alias[alias].append(num)
                        else:
                            logger.warning(
                                "Não foi possível mapear tribunal para justiça %s e tribunal %s.",
                                id_justica, id_tribunal)
                    else:
                        logger.warning(
                "Número de processo inválido para extração de justiça/tribunal: %s", num
            )
                for alias, processos in processos_por_alias.items():
                    logger.info("Buscando dados no endpoint %s", alias)
                    df = self._listar_processos_tribunal(
                        alias,
                        numero_processo=processos,
                        ano_ajuizamento=ano_ajuizamento,
                        classe=classe,
                        assuntos=assuntos,
                        mostrar_movs=mostrar_movs,
                        paginas=paginas,
                        tamanho_pagina=tamanho_pagina,
                    )
                    dfs.append(df)
                if dfs:
                    return pd.concat(dfs, ignore_index=True)
                return pd.DataFrame([])
            else:
                num = clean_cnj(numero_processo)
                if len(num) == 20:
                    id_justica = num[13]
                    id_tribunal = num[14:16]
                    alias = ID_JUSTICA_TRIBUNAL_TO_ALIAS.get((id_justica, id_tribunal))
                    if alias:
                        logger.info("Buscando dados no endpoint %s", alias)
                        df = self._listar_processos_tribunal(
                            alias,
                            numero_processo=[numero_processo],
                            ano_ajuizamento=ano_ajuizamento,
                            classe=classe,
                            assuntos=assuntos,
                            mostrar_movs=mostrar_movs,
                            paginas=paginas,
                            tamanho_pagina=tamanho_pagina,
                        )
                        return df
                    else:
                        logger.warning(
                            "Não foi possível mapear tribunal para justiça %s e tribunal %s.",
                            id_justica, id_tribunal)
                        return pd.DataFrame([])
                else:
                    logger.warning("Número de processo inválido para extração de justiça/tribunal.")
                    return pd.DataFrame([])
        elif tribunal:
            # Se tribunal for string, buscar alias direto
            if tribunal in self.TRIBUNAL_ALIASES:
                alias = self.TRIBUNAL_ALIASES[tribunal]
                logger.info("Buscando dados no endpoint %s", alias)
                df = self._listar_processos_tribunal(
                    alias,
                    numero_processo=numero_processo,
                    ano_ajuizamento=ano_ajuizamento,
                    classe=classe,
                    assuntos=assuntos,
                    mostrar_movs=mostrar_movs,
                    paginas=paginas,
                    tamanho_pagina=tamanho_pagina,
                )
                return df
            else:
                # Procurar por id_tribunal ou sigla (expandir depois)
                logger.warning("Tribunal não encontrado: %s", tribunal)
                return pd.DataFrame([])
        else:
            # Busca em todos os tribunais da justiça escolhida
            tribunais_alvo = []
            for (j, _), alias in ID_JUSTICA_TRIBUNAL_TO_ALIAS.items():
                if justica is None or j == justica:
                    tribunais_alvo.append(alias)
            for alias in tribunais_alvo:
                logger.info("Buscando dados no endpoint %s", alias)
                df = self._listar_processos_tribunal(
                    alias,
                    numero_processo=numero_processo,
                    ano_ajuizamento=ano_ajuizamento,
                    classe=classe,
                    assuntos=assuntos,
                    mostrar_movs=mostrar_movs,
                    paginas=paginas,
                    tamanho_pagina=tamanho_pagina,
                )
                dfs.append(df)
            if dfs:
                return pd.concat(dfs, ignore_index=True)
            return pd.DataFrame([])

    def _listar_processos_tribunal(
        self,
        alias: str,
        numero_processo: Optional[Union[str, List[str]]] = None,
        ano_ajuizamento: Optional[int] = None,
        classe: Optional[str] = None,
        assuntos: Optional[List[str]] = None,
        mostrar_movs: bool = False,
        paginas: Optional[range] = None,
        tamanho_pagina: int = 1000,
    ) -> pd.DataFrame:
        """
        Executa a busca para um tribunal (endpoint alias), com suporte a 
        múltiplos filtros e paginação automática.
        - tamanho_pagina sempre 1000
        - paginas=None: busca todas as páginas até acabar
        - paginas=range(...): busca apenas as páginas especificadas
        - mostrar_movs=True e paginas=None: exibe warning
        Para logs amigáveis: nome_tribunal = 
        next((k for k, v in self.TRIBUNAL_ALIASES.items() if v == alias), alias)
        """
        logger.info("Consultando endpoint %s", alias)
        dfs = []
        tamanho_pagina = 1000
        if mostrar_movs and paginas is None:
            logger.warning(
                "Você está baixando todas as páginas com mostrar_movs=True. "
                "O resultado pode ser muito pesado! Considere limitar o número de páginas."
            )
        if paginas is None:
            pagina = 1
            search_after = None
            sort_field = "@timestamp"
            total = None
            n_pags = None
            pbar = None
            while True:
                path = self._download_datajud(
                    alias,
                    numero_processo,
                    ano_ajuizamento,
                    classe,
                    assuntos,
                    mostrar_movs,
                    pagina,
                    tamanho_pagina,
                    search_after=search_after,
                    sort_field=sort_field,
                )
                # Pega o total de resultados da primeira página
                if total is None:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    total = data.get("hits", {}).get("total", {}).get("value", None)
                    if total is not None:
                        n_pags = (total + tamanho_pagina - 1) // tamanho_pagina
                        if tqdm:
                            pbar = tqdm(total=n_pags, desc="Baixando páginas", unit="página")
                df = self._parse_datajud(path, mostrar_movs=mostrar_movs)
                if df.empty:
                    break
                dfs.append(df)
                if pbar is not None:
                    pbar.update(1)
                if len(df) < tamanho_pagina:
                    break
                # Atualiza search_after para o próximo lote
                if sort_field in df.columns and not df.empty:
                    search_after = [df[sort_field].iloc[-1]]
                else:
                    logger.warning(
                        "Campo de ordenação '%s' não encontrado nos resultados. "
                        "Interrompendo paginação.",
                        sort_field
                    )
                    break
                pagina += 1
            if pbar is not None:
                pbar.close()
        else:
            iterator = paginas
            if tqdm:
                iterator = tqdm(paginas, desc="Baixando páginas", unit="página")
            search_after = None
            sort_field = "@timestamp"
            for pagina in iterator:
                path = self._download_datajud(
                    alias,
                    numero_processo,
                    ano_ajuizamento,
                    classe,
                    assuntos,
                    mostrar_movs,
                    pagina + 1,
                    tamanho_pagina,
                    search_after=search_after,
                    sort_field=sort_field,
                )
                df = self._parse_datajud(path, mostrar_movs=mostrar_movs)
                dfs.append(df)
                # Atualize search_after se for usar nas próximas páginas
                if sort_field in df.columns and not df.empty:
                    search_after = [df[sort_field].iloc[-1]]
        if dfs:
            return pd.concat(dfs, ignore_index=True)
        return pd.DataFrame([])

    # Dicionário de aliases dos tribunais para os endpoints oficiais
    TRIBUNAL_ALIASES = {
        # Tribunais Superiores
        "TST": "api_publica_tst",
        "TSE": "api_publica_tse",
        "STJ": "api_publica_stj",
        "STM": "api_publica_stm",

        # Justiça Federal
        "TRF1": "api_publica_trf1",
        "TRF2": "api_publica_trf2",
        "TRF3": "api_publica_trf3",
        "TRF4": "api_publica_trf4",
        "TRF5": "api_publica_trf5",
        "TRF6": "api_publica_trf6",

        # Justiça Estadual
        "TJAC": "api_publica_tjac",
        "TJAL": "api_publica_tjal",
        "TJAM": "api_publica_tjam",
        "TJAP": "api_publica_tjap",
        "TJBA": "api_publica_tjba",
        "TJCE": "api_publica_tjce",
        "TJDFT": "api_publica_tjdft",
        "TJES": "api_publica_tjes",
        "TJGO": "api_publica_tjgo",
        "TJMA": "api_publica_tjma",
        "TJMG": "api_publica_tjmg",
        "TJMS": "api_publica_tjms",
        "TJMT": "api_publica_tjmt",
        "TJPA": "api_publica_tjpa",
        "TJPB": "api_publica_tjpb",
        "TJPE": "api_publica_tjpe",
        "TJPI": "api_publica_tjpi",
        "TJPR": "api_publica_tjpr",
        "TJRJ": "api_publica_tjrj",
        "TJRN": "api_publica_tjrn",
        "TJRO": "api_publica_tjro",
        "TJRR": "api_publica_tjrr",
        "TJRS": "api_publica_tjrs",
        "TJSC": "api_publica_tjsc",
        "TJSE": "api_publica_tjse",
        "TJSP": "api_publica_tjsp",
        "TJTO": "api_publica_tjto",

        # Justiça do Trabalho
        "TRT1": "api_publica_trt1",
        "TRT2": "api_publica_trt2",
        "TRT3": "api_publica_trt3",
        "TRT4": "api_publica_trt4",
        "TRT5": "api_publica_trt5",
        "TRT6": "api_publica_trt6",
        "TRT7": "api_publica_trt7",
        "TRT8": "api_publica_trt8",
        "TRT9": "api_publica_trt9",
        "TRT10": "api_publica_trt10",
        "TRT11": "api_publica_trt11",
        "TRT12": "api_publica_trt12",
        "TRT13": "api_publica_trt13",
        "TRT14": "api_publica_trt14",
        "TRT15": "api_publica_trt15",
        "TRT16": "api_publica_trt16",
        "TRT17": "api_publica_trt17",
        "TRT18": "api_publica_trt18",
        "TRT19": "api_publica_trt19",
        "TRT20": "api_publica_trt20",
        "TRT21": "api_publica_trt21",
        "TRT22": "api_publica_trt22",
        "TRT23": "api_publica_trt23",
        "TRT24": "api_publica_trt24",

        # Justiça Eleitoral
        "TRE-AC": "api_publica_tre-ac",
        "TRE-AL": "api_publica_tre-al",
        "TRE-AM": "api_publica_tre-am",
        "TRE-AP": "api_publica_tre-ap",
        "TRE-BA": "api_publica_tre-ba",
        "TRE-CE": "api_publica_tre-ce",
        "TRE-DFT": "api_publica_tre-dft",
        "TRE-ES": "api_publica_tre-es",
        "TRE-GO": "api_publica_tre-go",
        "TRE-MA": "api_publica_tre-ma",
        "TRE-MG": "api_publica_tre-mg",
        "TRE-MS": "api_publica_tre-ms",
        "TRE-MT": "api_publica_tre-mt",
        "TRE-PA": "api_publica_tre-pa",
        "TRE-PB": "api_publica_tre-pb",
        "TRE-PE": "api_publica_tre-pe",
        "TRE-PI": "api_publica_tre-pi",
        "TRE-PR": "api_publica_tre-pr",
        "TRE-RJ": "api_publica_tre-rj",
        "TRE-RN": "api_publica_tre-rn",
        "TRE-RO": "api_publica_tre-ro",
        "TRE-RR": "api_publica_tre-rr",
        "TRE-RS": "api_publica_tre-rs",
        "TRE-SC": "api_publica_tre-sc",
        "TRE-SE": "api_publica_tre-se",
        "TRE-SP": "api_publica_tre-sp",
        "TRE-TO": "api_publica_tre-to",

        # Justiça Militar Estadual
        "TJMMG": "api_publica_tjmmg",
        "TJMRS": "api_publica_tjmrs",
        "TJMSP": "api_publica_tjmsp",
    }

    def _download_datajud(
        self,
        alias: str,
        numero_processo: Optional[Union[str, List[str]]],
        ano_ajuizamento: Optional[int],
        classe: Optional[str],
        assuntos: Optional[List[str]],
        mostrar_movs: bool,
        pagina: int,
        tamanho_pagina: int,
        search_after: list = None,
        sort_field: str = None,
    ) -> str:
        """
        Monta a query e faz o request para a API pública do Datajud.
        Salva o resultado bruto em arquivo temporário e retorna o caminho.
        É obrigatório fornecer uma API key válida (Authorization: APIKey ...).
        """
        # Usa alias diretamente
        url = f"https://api-publica.datajud.cnj.jus.br/{alias}/_search"
        headers = {"Authorization": f"APIKey {self.api_key}"}

        # Monta a query ElasticSearch
        must = []
        if numero_processo:
            if isinstance(numero_processo, list):
                must.append({"terms": {"numeroProcesso": numero_processo}})
            else:
                must.append({"match": {"numeroProcesso": numero_processo}})
        if ano_ajuizamento:
            must.append({
                "range": {
                    "dataAjuizamento": {
                        "gte": f"{ano_ajuizamento}-01-01",
                        "lte": f"{ano_ajuizamento}-12-31"
                    }
                }
            })
        if classe:
            must.append({"match": {"classe.codigo": str(classe)}})
        if assuntos:
            must.append({"terms": {"assuntos.codigo": assuntos}})

        query = {
            "query": {"bool": {"must": must}} if must else {"match_all": {}},
            "size": tamanho_pagina
        }
        # Paginação: search_after/sort vs from
        if search_after is not None and sort_field is not None:
            query["sort"] = [{sort_field: "asc"}]
            query["search_after"] = search_after
        elif sort_field is not None:
            query["sort"] = [{sort_field: "asc"}]
        else:
            query["from"] = (pagina - 1) * tamanho_pagina

        if mostrar_movs:
            query["_source"] = True  # Traz todos os campos, incluindo movimentações
        else:
            query["_source"] = {"excludes": ["movimentacoes", "movimentos"]}

        if self.verbose:
            logger.info("Enviando requisição para %s com query: %s", url, query)
        resp = self.session.post(url, json=query, headers=headers, timeout=15)
        if resp.status_code >= 400:
            logger.error(
                "[Datajud] Erro %d ao consultar %s", resp.status_code, url
            )
            logger.error("Query enviada: %s", query)
            logger.error("Resposta: %s", resp.text)
            resp.raise_for_status()
        # Salva resultado em arquivo temporário
        fd, filepath = tempfile.mkstemp(suffix="_datajud.json", dir=self.download_path)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(resp.text)
        return filepath

    def _parse_datajud(self, filepath: str, mostrar_movs: bool = True) -> pd.DataFrame:
        """
        Lê o arquivo JSON baixado e retorna DataFrame de processos (e movimentações, se solicitado).
        """
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        hits = data.get("hits", {}).get("hits", [])
        processos = []
        for h in hits:
            src = h.get("_source", {})
            if not mostrar_movs and "movimentacoes" in src:
                src = {k: v for k, v in src.items() if k != "movimentacoes"}
            processos.append(src)
        df = pd.DataFrame(processos)
        return df
