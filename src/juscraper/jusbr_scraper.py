"""Scraper para o Tribunal de Justiça do Brasil (genérico)."""
from typing import List, Union
import logging
import time
import jwt
import pandas as pd
import requests
from .base_scraper import BaseScraper
from .utils import clean_cnj

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0"
)

class JusbrScraper(BaseScraper):
    """Raspador para o Tribunal de Justiça do Brasil (genérico)."""

    def __init__(self, verbose=1, download_path=None, sleep_time=0.5):
        super().__init__("JUSBR")
        self.verbose = verbose
        self.download_path = download_path
        self.sleep_time = sleep_time
        self.session = requests.Session()
        self.token = None

    def auth(self, token: str, verbose=0):
        """
        Recebe o JWT token (access_token) já obtido manualmente pelo usuário.
        Decodifica o token e imprime as informações se verbose=1.
        Caso o token seja inválido, exibe tutorial para obtenção manual.
        """
        try:
            # PyJWT: decode sem verificação de assinatura
            decoded = jwt.decode(token,
                                 options={
                                     "verify_signature": False,
                                     "verify_aud": False
                                 },
                                 algorithms=["RS256", "HS256", "none"])
            self.token = token
            if verbose == 1:
                print(
                    "Token JWT decodificado com sucesso! Informações do token:"
                )
                for k, v in decoded.items():
                    print(f"  {k}: {v}")
            else:
                print("Token JWT decodificado com sucesso!")
        except jwt.DecodeError as e:
            raise ValueError("""
                Token JWT inválido ou biblioteca errada. 
                Siga o tutorial acima e use o pacote PyJWT.
                """) from e

    def cpopg(self, id_cnj: Union[str, List[str]]):
        """
        Consulta processos pelo número CNJ (ou lista de números CNJ) via API nacional.
        Retorna um DataFrame do pandas com metadados e detalhes de cada processo.
        Inclui a coluna 'processo' (primeira coluna), 
        com o número pesquisado (sempre limpo, só números).
        """
        if isinstance(id_cnj, str):
            id_cnj = [id_cnj]
        resultados = []
        headers = {
            'accept': 'application/json, text/plain, */*',
            'authorization': f'Bearer {self.token}',
            'user-agent': USER_AGENT,
            'referer': 'https://portaldeservicos.pdpj.jus.br/consulta',
        }
        for cnj in id_cnj:
            cnj_limpo = clean_cnj(cnj)
            url1 = (
                "https://portaldeservicos.pdpj.jus.br/api/v2/processos/"
                f"?numeroProcesso={cnj_limpo}"
            )
            try:
                r1 = self.session.get(url1, headers=headers)
                r1.raise_for_status()
            except requests.RequestException as e:
                raise RuntimeError(
                    f"Erro ao buscar processo {cnj}: {e}") from e
            dados1 = r1.json()
            processos = dados1.get('content', [])
            for processo in processos:
                numero_processo = processo.get('numeroProcesso', cnj)
                url2 = f'https://portaldeservicos.pdpj.jus.br/api/v2/processos/{cnj}'
                try:
                    r2 = self.session.get(url2, headers=headers)
                    r2.raise_for_status()
                except requests.RequestException as e:
                    raise RuntimeError(
                        f"Erro ao buscar detalhes do processo {cnj}: {e}"
                    ) from e
                detalhes_proc = r2.json()
                row = {
                    'processo': cnj_limpo,
                    'numeroProcesso': numero_processo,
                    'idCodexTribunal': processo.get('idCodexTribunal'),
                    'detalhes': detalhes_proc
                }
                resultados.append(row)
                time.sleep(self.sleep_time)
        df = pd.DataFrame(resultados)
        # Garante a ordem da coluna 'processo' como primeira
        cols = ['processo'] + [c for c in df.columns if c != 'processo']
        return df[cols]

    def download_documents(self,
                           base,
                           sleep_time=None,
                           verbose=0,
                           log_path=None):
        """
        Baixa todos os autos/documentos em hrefTexto para cada processo 
        da base (DataFrame do cpopg). Retorna um DataFrame onde cada linha 
        é um documento com texto e metadados principais.
        Se log_path for fornecido, salva o log detalhado das tentativas.
        """
        session = self.session
        token = self.token
        if sleep_time is None:
            sleep_time = self.sleep_time
        # Configuração de logging
        doc_logger = logging.getLogger("jusbr_download_documents")
        doc_logger.handlers = []  # Remove handlers antigos
        doc_logger.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
        if log_path:
            fh = logging.FileHandler(log_path, mode='w', encoding='utf-8')
            fh.setFormatter(formatter)
            doc_logger.addHandler(fh)
        sh = logging.StreamHandler()
        sh.setFormatter(formatter)
        if verbose:
            sh.setLevel(logging.INFO)
            doc_logger.addHandler(sh)
        documentos = []
        headers = {
            'accept': '*/*',
            'authorization': f'Bearer {token}',
            'user-agent': USER_AGENT,
            'referer': 'https://portaldeservicos.pdpj.jus.br/consulta',
        }
        if verbose:
            doc_logger.info(
                "Iniciando download de documentos para %d processos...",
                len(base))
        for processo in base.iterrows():
            numero_processo = processo[1].get("numeroProcesso", "")
            if not numero_processo:
                continue
            detalhes = processo[1]['detalhes']
            docs = []
            # Correção: buscar documentos dentro de tramitacaoAtual
            if isinstance(detalhes, list):
                for item in detalhes:
                    ta = item.get('tramitacaoAtual', {})
                    docs.extend(ta.get('documentos', []))
            elif isinstance(detalhes, dict):
                ta = detalhes.get('tramitacaoAtual', {})
                docs = ta.get('documentos', [])
            else:
                if verbose:
                    doc_logger.warning(
                        "Formato inesperado em detalhes para processo %s: %s",
                        numero_processo, type(detalhes))
            if verbose:
                doc_logger.info("Processo %s: %d documentos encontrados.",
                                numero_processo, len(docs))
            for doc in docs:
                href = doc.get('hrefTexto')
                texto = None
                # Extrai o id do documento do hrefTexto
                id_href = None
                if href and '/documentos/' in href:
                    try:
                        id_href = href.split('/documentos/')[1].split('/')[0]
                    except (KeyError, ValueError, TypeError) as e:
                        doc_logger.warning("Erro ao processar documento: %s",
                                           e)
                # Novo endpoint alternativo para texto
                if id_href:
                    alt_url = (
                        f"https://api-processo.data-lake.pdpj.jus.br/processo-api/api/v1/processos/"
                        f"{numero_processo}/documentos/{id_href}/texto"
                        f"?numeroProcesso={numero_processo}&idDocumento={id_href}"
                    )
                    if verbose:
                        doc_logger.info(
                            "Tentando baixar texto do documento via endpoint alternativo: %s",
                            alt_url)
                    try:
                        r = session.get(alt_url, headers=headers, timeout=15)
                        if r.status_code == 200:
                            try:
                                texto = r.content.decode('utf-8')
                            except UnicodeDecodeError:
                                texto = r.text  # fallback
                            # Limpa caracteres de controle e normaliza quebras de linha
                            texto = (texto.replace('\r', '').replace(
                                '\x00', '').replace('\x1a', '').replace(
                                    '\xa0',
                                    ' ').replace('\u2028',
                                                 '\n').replace('\u2029', '\n'))
                            if verbose:
                                doc_logger.info(
                                    "Sucesso ao baixar texto do doc %s (tamanho=%d)",
                                    alt_url, len(texto))
                        else:
                            if verbose:
                                doc_logger.warning(
                                    "Falha ao baixar texto do doc %s: %s %s",
                                    alt_url, r.status_code, r.text[:200])
                    except requests.RequestException as e:
                        if verbose:
                            doc_logger.warning(
                                "Erro ao baixar texto do documento via endpoint alternativo: %s",
                                e)
                    time.sleep(sleep_time)
                else:
                    if verbose:
                        doc_logger.warning(
                            "Documento sem id_href extraído de hrefTexto: %s",
                            doc)
                linha = {
                    **{
                        k: doc.get(k)
                        for k in doc
                    }, 'numero_processo': numero_processo,
                    'texto': texto
                }
                documentos.append(linha)
        colunas = [
            'numero_processo', 'sequencia', 'dataHoraJuntada', 'idCodex',
            'idOrigem', 'nome', 'nivelSigilo', 'tipo', 'hrefBinario',
            'hrefTexto', 'arquivo', 'texto'
        ]
        df_docs = pd.DataFrame(documentos)
        for col in colunas:
            if col not in df_docs.columns:
                df_docs[col] = None
        if verbose:
            doc_logger.info("Download finalizado. Total de documentos: %d.",
                            len(df_docs))
        return df_docs[colunas]

    def cposg(self, id_cnj: Union[str, List[str]]):
        pass

    def cjsg(self, query: str):
        pass
