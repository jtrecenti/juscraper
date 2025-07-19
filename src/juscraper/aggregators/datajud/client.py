"""
Orchestrates the flow for DATAJUD (user entry point) - API BASED
"""
import os
import tempfile
from typing import Optional, Dict, List, Union, Any
from collections import defaultdict
import logging
import time
import requests
import pandas as pd
from tqdm.auto import tqdm

from ...core.base import BaseScraper
from ...utils.cnj import clean_cnj # Assuming this utility exists and is relevant
# Import mappings for tribunal and justice aliases.
from .mappings import ID_JUSTICA_TRIBUNAL_TO_ALIAS, TRIBUNAL_TO_ALIAS

from .download import call_datajud_api # To be created for API calls
from .parse import parse_datajud_api_response # To be created for API response parsing

logger = logging.getLogger(__name__)

class DatajudScraper(BaseScraper):
    """Scraper for CNJ's Datajud API."""
    DEFAULT_API_KEY = "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="
    BASE_API_URL = "https://api-publica.datajud.cnj.jus.br"

    def __init__(
        self,
        api_key: Optional[str] = None,
        verbose: int = 1,
        download_path: Optional[str] = None, # For temporary files if needed
        sleep_time: float = 0.5,
    ):
        super().__init__("DatajudAPI")
        self.set_verbose(verbose)
        # download_path for API responses if saved temporarily, or can be ignored if
        # data is processed in memory
        self.download_path = download_path or tempfile.mkdtemp(prefix="datajud_api_")
        if not os.path.exists(self.download_path):
            os.makedirs(self.download_path)
        self.session = requests.Session()
        self.api_key = api_key or self.DEFAULT_API_KEY
        self.sleep_time = sleep_time
        logger.info(
            "DatajudScraper initialized. API Key: "
            "{'Provided' if api_key else 'Default'}. Temp path: %s",
            self.download_path
        )

    def listar_processos(
        self,
        numero_processo: Optional[Union[str, List[str]]] = None,
        tribunal: Optional[str] = None, # Sigla, e.g., TJSP, TRF1
        # justica: Optional[str] = "8", # This was in original, but tribunal alias seems more direct
        ano_ajuizamento: Optional[int] = None,
        classe: Optional[str] = None, # Codigo da classe
        assuntos: Optional[List[str]] = None, # Lista de códigos de assuntos
        mostrar_movs: bool = False,
        paginas: Optional[range] = None, # For specific page range, else fetch all
        tamanho_pagina: int = 1000 # Max allowed by API is often 1000 or 10000
    ) -> pd.DataFrame:
        """
        Lists processes from Datajud via API, with support for multiple filters and pagination.
        """
        all_dfs = []
        # Determine target aliases
        target_aliases = []
        if tribunal:
            alias = TRIBUNAL_TO_ALIAS.get(tribunal.upper())
            if alias:
                target_aliases.append(alias)
            else:
                logger.error("Tribunal %s não encontrado nos mappings.", tribunal)
                return pd.DataFrame()
        elif numero_processo:
            # Group by alias if multiple CNJs from different tribunals are provided
            processos_por_alias = defaultdict(list)
            if isinstance(numero_processo, str):
                cnjs_to_query = [numero_processo]
            else:
                cnjs_to_query = numero_processo
            for num_cnj in cnjs_to_query:
                num_limpo = clean_cnj(num_cnj)
                if len(num_limpo) == 20:
                    id_justica_cnj = num_limpo[13]
                    id_tribunal_cnj = num_limpo[14:16]
                    alias = ID_JUSTICA_TRIBUNAL_TO_ALIAS.get((id_justica_cnj, id_tribunal_cnj))
                    if alias:
                        processos_por_alias[alias].append(num_cnj)
                    else:
                        logger.warning("Não foi possível determinar alias para CNJ: %s", num_cnj)
                else:
                    logger.warning("CNJ inválido: %s", num_cnj)
            if not processos_por_alias:
                logger.error("Nenhum CNJ válido para determinar tribunal/alias.")
                return pd.DataFrame()
            target_aliases = list(processos_por_alias.keys())
        else:
            # Potentially iterate all known aliases if no tribunal/CNJ specified - very broad!
            # For now, require tribunal or numero_processo if not querying all.
            # Or, could default to a list of all aliases from TRIBUNAL_TO_ALIAS.values()
            logger.error("É necessário especificar 'tribunal' ou 'numero_processo'.")
            return pd.DataFrame()

        for alias_idx, alias_name in enumerate(target_aliases):
            logger.info("Consultando: %s (%d/%d)", alias_name, alias_idx+1, len(target_aliases))
            # If CNJs were grouped, use only the CNJs for this specific alias
            if numero_processo and not tribunal:
                current_cnjs_for_alias = processos_por_alias[alias_name]
            else:
                current_cnjs_for_alias = numero_processo
            df_alias = self._listar_processos_por_alias(
                alias=alias_name,
                numero_processo=current_cnjs_for_alias,
                ano_ajuizamento=ano_ajuizamento,
                classe=classe,
                assuntos=assuntos,
                mostrar_movs=mostrar_movs,
                paginas_range=paginas,
                tamanho_pagina=tamanho_pagina
            )
            if not df_alias.empty:
                all_dfs.append(df_alias)

        if not all_dfs:
            return pd.DataFrame()
        return pd.concat(all_dfs, ignore_index=True)

    def _listar_processos_por_alias(
        self,
        alias: str,
        numero_processo: Optional[Union[str, List[str]]],
        ano_ajuizamento: Optional[int],
        classe: Optional[str],
        assuntos: Optional[List[str]],
        mostrar_movs: bool,
        paginas_range: Optional[range],
        tamanho_pagina: int,
    ) -> pd.DataFrame:
        """Helper to fetch and parse data for a single alias with pagination."""
        dfs_alias = []
        current_page = paginas_range.start if paginas_range else 1
        end_page = paginas_range.stop if paginas_range else float('inf')
        search_after_params = None # For deep pagination
        sort_field = "id.keyword" # Use .keyword for sorting text fields

        # Initialize tqdm progress bar
        if paginas_range:
            total_pages_to_fetch = paginas_range.stop - paginas_range.start
            # Disable pbar if no pages are to be fetched based on range
            pbar_disabled = total_pages_to_fetch <= 0
            pbar = tqdm(
                total=total_pages_to_fetch,
                desc=f"Paginando {alias}",
                unit=" página",
                disable=pbar_disabled
            )
        else:
            # If paginas_range is None, total is unknown
            pbar = tqdm(desc=f"Paginando {alias}", unit=" página")

        try:
            while current_page < end_page:
                logger.info("Fetching page %d for alias %s...", current_page, alias)
                # Construct query payload (Elasticsearch DSL)
                must_conditions = []
                if numero_processo:
                    if isinstance(numero_processo, str):
                        nproc = [numero_processo]
                    else:
                        nproc = numero_processo
                    must_conditions.append({
                        "terms": {
                            "numeroProcesso": nproc
                        }
                    })
                if ano_ajuizamento:
                    must_conditions.append({
                        "range": {
                            "dataAjuizamento": {
                                "gte": f"{ano_ajuizamento}-01-01", 
                                "lte": f"{ano_ajuizamento}-12-31"
                            }
                        }
                    })
                if classe:
                    must_conditions.append({
                        "match": {
                            "classe.codigo": str(classe)
                        }
                    })
                if assuntos:
                    must_conditions.append({
                        "terms": {
                            "assuntos.codigo": assuntos
                        }
                    })

                if must_conditions:
                    query_values = {"bool": {"must": must_conditions}}
                else:
                    query_values = {"match_all": {}}

                query_payload: Dict[str, Any] = {
                    "query": query_values,
                    "size": tamanho_pagina
                }

                # Handle pagination: search_after is preferred for deep pagination
                # The original _download_datajud used 'from', which is inefficient for deep pages
                # DataJud API supports search_after. Requires a sort field.
                query_payload["sort"] = [{sort_field: "asc"}] # Example sort
                if search_after_params:
                    query_payload["search_after"] = search_after_params
                else:
                    # For the first page if not using search_after from the start,
                    # or if API doesn't fully support it
                    # query_payload["from"] = (current_page - 1) * tamanho_pagina
                    # However, if we commit to search_after, 'from' is not used.
                    pass # First page, no search_after yet unless seeded

                if not mostrar_movs:
                    query_payload["_source"] = {"excludes": ["movimentacoes", "movimentos"]}
                else:
                    query_payload["_source"] = True
                api_response_json = call_datajud_api(
                    base_url=self.BASE_API_URL,
                    alias=alias,
                    api_key=self.api_key,
                    session=self.session,
                    query_payload=query_payload,
                    verbose=self.verbose > 1 # Pass verbose flag for more detailed logging
                )

                if api_response_json is None:
                    logger.error(
                        "Failed to get API response for alias %s, page %d."
                        "Stopping.", 
                        alias,
                        current_page
                    )
                    break

                df_page = parse_datajud_api_response(api_response_json, mostrar_movs)
                if df_page.empty:
                    logger.info(
                        "No more results for alias %s on page %d (or parsing failed).", 
                        alias,
                        current_page
                    )
                    break
                dfs_alias.append(df_page)
                pbar.update(1) # Update progress bar

                # For search_after pagination: extract the sort values of the last hit
                # This part depends on the exact structure of api_response_json
                # Assuming api_response_json is a dict parsed from the JSON string
                hits = api_response_json.get("hits", {}).get("hits", [])
                if not hits or len(hits) < tamanho_pagina:
                    logger.info(
                        "Last page reached for alias %s (less than %d results or no hits).",
                        alias,
                        tamanho_pagina
                    )
                    break
                last_hit = hits[-1]
                search_after_params = last_hit.get("sort")
                if search_after_params is None:
                    logger.warning(
                        "Sort parameters for 'search_after' not found in last hit."
                        "Cannot continue deep pagination."
                    )
                    break # Fallback or stop if search_after cannot be determined

                if paginas_range is None: # if fetching all, continue
                    current_page += 1
                elif current_page < paginas_range.stop -1: # if in specified range, continue
                    current_page +=1
                else: # reached end of specified range
                    break
                time.sleep(self.sleep_time) # Respect sleep time
        finally:
            pbar.close() # Ensure progress bar is closed

        if not dfs_alias:
            return pd.DataFrame()
        return pd.concat(dfs_alias, ignore_index=True)
