"""
Module client.py: Orchestrates the flow for JUSBR (user entry point).
Contains the JusbrScraper class for interaction with the API
from Platforma Digital do Poder Judiciario (PDPJ).
"""
# Orchestrates the flow for JUSBR (user entry point)
# Will contain JusbrScraper class

import logging
import time
from typing import List, Optional, Union
import urllib
import browser_cookie3

import jwt
import pandas as pd
import requests
import numpy as np

from ...core.base import BaseScraper
from ...utils.cnj import clean_cnj
from .download import (
    fetch_process_list,
    fetch_process_details,
    fetch_document_text,
    fetch_document_binary,
    USER_AGENT
)
from .parse import (
    parse_process_list_response,
    parse_process_details_response,
    clean_document_text
)

logger = logging.getLogger(__name__)

class JusbrScraper(BaseScraper):
    """
    Raspador para o JusBR (consulta unificada da PDPJ-CNJ).
    Este scraper interage com a API da Plataforma Digital do Poder Judiciario (PDPJ).
    """
    BASE_API_URL_V2 = "https://portaldeservicos.pdpj.jus.br/api/v2/processos/"
    BASE_API_URL_V1_DOCS = (
        "https://api-processo.data-lake.pdpj.jus.br/processo-api/api/v1/processos/"
    )

    def __init__(
        self,
        verbose: int = 0,
        download_path: Optional[str] = None,
        sleep_time: float = 0.5,
        token: Optional[str] = None
    ):
        super().__init__("jusbr")
        self.set_verbose(verbose)
        self.set_download_path(download_path)
        self.sleep_time = sleep_time
        self.session = requests.Session()
        self.token = token
        if self.token:
            self.session.headers.update({'authorization': f'Bearer {self.token}'})
        self.session.headers.update({'user-agent': USER_AGENT})

    def auth(self, token: str) -> bool:
        """
        Define o token JWT para autenticacao e o decodifica para verificacao.
        """
        try:
            decoded = jwt.decode(token,
                                 options={"verify_signature": False, "verify_aud": False},
                                 algorithms=["RS256", "HS256", "ES256", "none"])
            self.token = token
            self.session.headers.update({'authorization': f'Bearer {self.token}'})
            if self.verbose > 0:
                logger.info("Token JWT definido e decodificado com sucesso!")
                if self.verbose > 1:
                    for k, v in decoded.items():
                        logger.debug("  Token claim %s: %s", k, v)
            return True
        except jwt.ExpiredSignatureError as exc:
            logger.error("Token JWT expirado.")
            raise ValueError("Token JWT expirado.") from exc
        except jwt.InvalidTokenError as exc:
            logger.error("Token JWT inválido: %s", exc)
            raise ValueError(f"Token JWT inválido: {exc}") from exc
        return False

    def auth_firefox(self):
        """
        Authentication via Firefox.
        """
        # url de autenticação
        u = (
            "https://sso.cloud.pje.jus.br/auth/realms/pje/protocol/"
            "openid-connect/auth?client_id=portalexterno-frontend"
            "&redirect_uri=https://portaldeservicos.pdpj.jus.br/home?state=meu_state"
            "&session_state=1234&state=1234&response_mode=fragment&response_type=code"
            "&scope=openid&nonce=1234&prompt=none"
        )

        # pega cookies do firefox
        cookies = browser_cookie3.firefox(domain_name="sso.cloud.pje.jus.br")
        session = requests.Session()
        session.cookies.update(cookies)

        # faz request para obter o token
        resp = session.get(u, allow_redirects=False)
        location_url = resp.headers.get("Location")
        fragment = urllib.parse.urlparse(location_url).fragment
        params = urllib.parse.parse_qs(fragment)
        code = params.get("code", [None])[0]
        token_url = "https://sso.cloud.pje.jus.br/auth/realms/pje/protocol/openid-connect/token"
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": "portalexterno-frontend",
            "redirect_uri": (
                "https://portaldeservicos.pdpj.jus.br/home?state=meu_state&session_state=1234"
            )
        }
        resp = session.post(token_url, data=data)
        token = resp.json()["access_token"]
        self.token = token
        self.session.headers.update({'authorization': f'Bearer {self.token}'})
        return True

    def cpopg(self, id_cnj: Union[str, List[str]]) -> pd.DataFrame:
        """
        Consulta processos pelo numero CNJ (ou lista de numeros CNJ) via API nacional.
        """
        if not self.token:
            raise RuntimeError("Autenticacao necessaria. Chame o metodo auth(token) primeiro.")

        id_cnj_list = [id_cnj] if isinstance(id_cnj, str) else id_cnj
        all_process_data = []

        for cnj_input in id_cnj_list:
            cnj_cleaned = clean_cnj(cnj_input)
            if not cnj_cleaned:
                logger.warning("CNJ inválido fornecido e não pôde ser limpo: %s", cnj_input)
                all_process_data.append({
                    'processo_pesquisado': cnj_input,
                    'status_consulta': 'CNJ Invalido'
                })
                continue

            logger.info("Consultando processo CNJ: %s", cnj_cleaned)

            raw_list_data = fetch_process_list(self.session, cnj_cleaned, self.BASE_API_URL_V2)
            processos_content = parse_process_list_response(raw_list_data)

            if not processos_content:
                logger.warning("Nenhum processo encontrado para o CNJ: %s", cnj_cleaned)
                all_process_data.append({
                    'processo_pesquisado': cnj_cleaned,
                    'status_consulta': 'Nao encontrado na lista inicial'
                })
                time.sleep(self.sleep_time)
                continue

            for processo_item in processos_content:
                numero_processo_oficial = processo_item.get('numeroProcesso')
                if not numero_processo_oficial:
                    logger.warning(
                        "Item de processo sem 'numeroProcesso' para CNJ %s. Item: %s",
                        cnj_cleaned, processo_item
                    )
                    continue

                raw_details_data = fetch_process_details(
                    self.session, numero_processo_oficial, self.BASE_API_URL_V2
                )
                parsed_details = parse_process_details_response(raw_details_data, cnj_cleaned)
                if parsed_details:
                    all_process_data.append(parsed_details)
                else:
                    all_process_data.append({
                        'processo_pesquisado': cnj_cleaned,
                        'numeroProcessoOficial': numero_processo_oficial,
                        'status_consulta': 'Erro ao obter ou parsear detalhes'
                    })
            time.sleep(self.sleep_time)

        if not all_process_data:
            return pd.DataFrame()
        df_resultados = pd.DataFrame(all_process_data)
        if 'processo_pesquisado' in df_resultados.columns:
            cols1 = [col for col in df_resultados.columns if col != 'processo_pesquisado']
            cols = ['processo_pesquisado'] + cols1
            df_resultados = df_resultados[cols]
        return df_resultados

    def download_documents(self,
                           base_df: pd.DataFrame,
                           max_docs_per_process: Optional[int] = None) -> pd.DataFrame:
        """
        Downloads document texts for processes in base_df.
        Iterates through processes in base_df, extracts document metadata from the
        'detalhes' column, fetches, and cleans document texts.
        Returns a DataFrame where each row is a document.
        """
        if not self.token:
            raise RuntimeError("Autenticação necessária. Chame o método auth(token) primeiro.")

        all_docs_data = []
        logger.info("Iniciando download de documentos para %d processos...", len(base_df))

        for index, row in base_df.iterrows():
            numero_processo_api = row.get('numeroProcesso') # Official CNJ for API calls
            cnj_original_pesquisa = row.get('processo') # User's search term

            if not numero_processo_api:
                logger.warning(
                    "Linha %d (CNJ: %s) sem 'numeroProcesso' para download de documentos",
                    index, cnj_original_pesquisa
                )
                continue

            detalhes = row.get('detalhes')
            if not isinstance(detalhes, dict):
                logger.warning(
                    "Campo 'detalhes' não é um dicionário para o"
                    "processo %s (linha %d). Tipo: %s. Pulando documentos.",
                    numero_processo_api, index, type(detalhes).__name__
                )
                continue

            document_metadata_list = []
            # Try common paths for document metadata list within 'detalhes'
            if 'dadosBasicos' in detalhes and isinstance(detalhes['dadosBasicos'], dict):
                document_metadata_list = detalhes['dadosBasicos'].get('documentos', [])

            if (not document_metadata_list and
                'documentos' in detalhes and
                isinstance(detalhes['documentos'], list)):
                document_metadata_list = detalhes['documentos']

            if (not document_metadata_list and
                'tramitacaoAtual' in detalhes and
                isinstance(detalhes['tramitacaoAtual'], dict)):
                document_metadata_list = detalhes['tramitacaoAtual'].get('documentos', [])
                if isinstance(document_metadata_list, np.ndarray):
                    document_metadata_list = document_metadata_list.tolist()

            # Ensure it's a list
            if not isinstance(document_metadata_list, list):
                logger.warning(
                    "Lista de metadados de documentos não encontrada ou não é uma lista "
                    "para o processo %s. Conteúdo de 'detalhes' (início): %s",
                    numero_processo_api, str(detalhes)[:200]
                )
                document_metadata_list = []

            logger.info(
                "Processo %s (pesquisado: %s): %d documentos encontrados na metadata.",
                numero_processo_api, cnj_original_pesquisa, len(document_metadata_list)
            )

            docs_processed_count = 0
            for doc_meta in document_metadata_list:
                if not isinstance(doc_meta, dict):
                    logger.warning(
                        "Item na lista de documentos não é um"
                        "dicionário para o processo %s. Item: %s",
                        numero_processo_api, str(doc_meta)[:100]
                    )
                    continue

                if (max_docs_per_process is not None and
                    docs_processed_count >= max_docs_per_process):
                    logger.info(
                        "Limite de %d documentos atingido para o processo %s.",
                        max_docs_per_process, numero_processo_api
                    )
                    break

                # Para o download correto, sempre usar o UUID extraído
                # de hrefTexto como identificador do documento na URL.
                href_texto = doc_meta.get('hrefTexto')
                id_doc_uuid = None
                if href_texto and isinstance(href_texto, str) and '/documentos/' in href_texto:
                    try:
                        id_doc_uuid = href_texto.split('/documentos/')[1].split('/')[0]
                    except IndexError:
                        logger.warning(
                            "Não foi possível extrair UUID do hrefTexto: %s"
                            " para processo %s", 
                            href_texto,
                            numero_processo_api
                        )
                href_binario = doc_meta.get('hrefBinario')
                id_doc_uuid_binario = None
                if href_binario and isinstance(href_binario, str) and '/documentos/' in href_binario:
                    try:
                        id_doc_uuid_binario = href_binario.split('/documentos/')[1].split('/')[0]
                    except IndexError:
                        logger.warning(
                            "Não foi possível extrair UUID do hrefBinario: %s"
                            " para processo %s", 
                            href_binario,
                            numero_processo_api
                        )
                if not id_doc_uuid:
                    logger.warning(
                        "Documento sem UUID extraível de 'hrefTexto'"
                        "para o processo %s. Metadados: %s",
                        numero_processo_api, str(doc_meta)[:200]
                    )
                    continue
                if not id_doc_uuid_binario:
                    logger.warning(
                        "Documento sem UUID extraível de 'hrefBinario'"
                        "para o processo %s. Metadados: %s",
                        numero_processo_api, str(doc_meta)[:200]
                    )
                    continue
                logger.debug(
                    "[JUSBR DEBUG] doc_meta para processo %s: %r", 
                    numero_processo_api, doc_meta
                )
                logger.debug(
                    "Tentando baixar texto do documento UUID %s para processo %s.",
                    id_doc_uuid, numero_processo_api
                )
                # Usa CNJ limpo para a API de documentos
                numero_processo_api_clean = clean_cnj(numero_processo_api)
                raw_text = fetch_document_text(
                    self.session,
                    numero_processo_api_clean,
                    str(id_doc_uuid),
                    self.BASE_API_URL_V1_DOCS
                )
                cleaned_text = clean_document_text(raw_text)
                raw_binary = fetch_document_binary(
                    self.session,
                    numero_processo_api_clean,
                    str(id_doc_uuid_binario),
                    self.BASE_API_URL_V2
                )

                if cleaned_text:
                    logger.debug(
                        "Sucesso ao baixar e limpar texto do doc UUID %s"
                        "(processo %s), tamanho limpo: %d",
                        id_doc_uuid,
                        numero_processo_api,
                        len(cleaned_text)
                    )
                elif raw_text:
                    logger.debug(
                        "Texto baixado para doc UUID %s"
                        "(processo %s) mas resultou em None/vazio"
                        "após limpeza. Raw tamanho: %d",
                        id_doc_uuid,
                        numero_processo_api,
                        len(raw_text)
                    )
                else:
                    logger.warning(
                        "Falha ao baixar texto do doc UUID %s"
                        "(processo %s), ou texto vazio.",
                        id_doc_uuid,
                        numero_processo_api
                    )

                doc_data_row = {
                    'numero_processo': numero_processo_api,
                    'texto': cleaned_text,
                    '_raw_text_api': raw_text,
                    '_raw_binary_api': raw_binary
                }
                doc_data_row.update(doc_meta)  # Add all metadata from the document item
                all_docs_data.append(doc_data_row)
                docs_processed_count += 1
                time.sleep(self.sleep_time)

        if not all_docs_data:
            logger.info("Nenhum documento foi baixado ou processado.")
            return pd.DataFrame()

        df_docs = pd.DataFrame(all_docs_data)

        # Define preferred columns based on original and common JusBR fields
        # 'nome' from original might map to 'descricao' in API meta
        preferred_columns = [
            'numero_processo', 'idDocumento', 'idCodex', 'sequencia', 'descricao', 'nome',
            'tipoDocumento', 'tipo', 'dataHoraJuntada', 'dataJuntada', 'nivelSigilo',
            'hrefTexto', 'hrefBinario', 'texto', '_raw_text_api', '_raw_binary_api'
        ]
        # Ensure preferred columns are present and in order, add others at the end
        final_cols = []
        existing_cols_set = set(df_docs.columns)
        for col in preferred_columns:
            if col in existing_cols_set:
                final_cols.append(col)
                existing_cols_set.remove(col)  # Avoid duplication
        final_cols.extend(sorted(list(existing_cols_set)))  # Add remaining columns alphabetically

        df_docs = df_docs[final_cols]
        # Fill with None if some preferred columns were entirely missing from all docs
        for col_pref in preferred_columns:
            if col_pref not in df_docs.columns:
                df_docs[col_pref] = None

        logger.info(
            "Download de documentos finalizado. Total de linhas de documentos: %d.",
            len(df_docs)
        )
        return df_docs
