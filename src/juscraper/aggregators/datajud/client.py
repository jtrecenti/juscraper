"""
Orchestrates the flow for DATAJUD (user entry point) - API BASED
"""
import logging
import os
import tempfile
import time
import warnings
from collections import defaultdict
from typing import Any, List, Optional, Union

import pandas as pd
import requests
from pydantic import ValidationError
from tqdm.auto import tqdm

from ...core.base import BaseScraper
from ...utils.cnj import clean_cnj  # Assuming this utility exists and is relevant
from ...utils.params import normalize_paginas, raise_on_extra_kwargs
from .download import (
    build_contar_processos_payload,
    build_listar_processos_payload,
    call_datajud_api,
)

# Import mappings for tribunal and justice aliases.
from .mappings import ID_JUSTICA_TRIBUNAL_TO_ALIAS, TRIBUNAL_TO_ALIAS
from .parse import parse_datajud_api_response  # To be created for API response parsing
from .schemas import InputContarProcessosDataJud, InputListarProcessosDataJud

# Mapping inverso pra rotular o DataFrame devolvido por ``contar_processos``
# com a sigla do tribunal (não só o alias-índice do Elasticsearch).
ALIAS_TO_TRIBUNAL = {alias: sigla for sigla, alias in TRIBUNAL_TO_ALIAS.items()}

logger = logging.getLogger(__name__)


class DatajudScraper(BaseScraper):
    """Scraper for CNJ's Datajud API."""

    DEFAULT_API_KEY = "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="
    BASE_API_URL = "https://api-publica.datajud.cnj.jus.br"

    # Schema pydantic detectado por ``tests/schemas/test_signature_parity._is_wired``.
    INPUT_LISTAR_PROCESSOS = InputListarProcessosDataJud

    def __init__(
        self,
        api_key: Optional[str] = None,
        verbose: int = 1,
        download_path: Optional[str] = None,  # For temporary files if needed
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

    def contar_processos(self, **kwargs) -> pd.DataFrame:
        """Conta processos no DataJud sem baixar nenhum documento.

        Útil para análise de viabilidade — antes de uma raspagem grande,
        descobrir o volume estimado por tribunal. Usa ``track_total_hits=True``
        com ``size=0`` (cap do Elasticsearch é 10000 quando ``track_total_hits``
        é ``True`` apenas via flag boolean — aqui exigimos a contagem exata,
        então o backend devolve ``relation="eq"`` quando o total é conhecido).

        Aceita o **mesmo conjunto de filtros** de :meth:`listar_processos`
        (``tribunal``, ``numero_processo``, ``ano_ajuizamento``, ``classe``,
        ``assuntos``), excluindo apenas os parâmetros de paginação
        (``paginas``, ``tamanho_pagina``, ``mostrar_movs``) — não há
        paginação numa contagem.

        ``ano_ajuizamento`` aceita ``int`` (1 ano), ``tuple[int, int]``
        (range inclusivo, ex.: ``(2020, 2024)``) ou ``list[int]`` (anos
        discretos, ex.: ``[2020, 2022, 2024]``). ``classe`` aceita
        ``str`` (1 código) ou ``list[str]`` (vários códigos OR-ed).

        Args:
            **kwargs: Filtros aceitos pelo schema
                :class:`InputContarProcessosDataJud`.

        Returns:
            pd.DataFrame: Uma linha por tribunal consultado, com colunas
            ``tribunal`` (sigla), ``alias`` (índice ES), ``count`` (int) e
            ``relation`` (``"eq"`` exato ou ``"gte"`` truncado pelo cap
            interno do Elasticsearch). Quando a chamada falha para um
            tribunal, ``count`` é ``None`` e a coluna ``error`` traz o
            motivo.

        Raises:
            TypeError: Quando um kwarg desconhecido é passado.
            ValidationError: Quando um filtro tem formato inválido.
            ValueError: Quando nem ``tribunal`` nem ``numero_processo``
                são informados, ou quando a sigla não tem alias mapeado.

        Exemplo:
            >>> import juscraper as jus
            >>> dj = jus.scraper("datajud")
            >>> dj.contar_processos(tribunal="TJSP", ano_ajuizamento=2023, classe="436")
              tribunal             alias  count relation error
            0     TJSP  api_publica_tjsp  12345       eq   None

            >>> # Range de anos + lista de classes (estudo plurianual):
            >>> dj.contar_processos(
            ...     tribunal="TJSP",
            ...     ano_ajuizamento=(2020, 2024),
            ...     classe=["7", "436"],
            ...     assuntos=["7780"],
            ... )

        See also:
            :meth:`listar_processos` — usa o mesmo conjunto de filtros mas
            baixa os processos.
        """
        try:
            inp = InputContarProcessosDataJud(**kwargs)
        except ValidationError as exc:
            raise_on_extra_kwargs(exc, "DatajudScraper.contar_processos()")
            raise

        target_aliases = self._resolve_aliases(
            tribunal=inp.tribunal,
            numero_processo=inp.numero_processo,
        )
        # ``_resolve_aliases`` devolve uma list[(alias, cnjs_pra_esse_alias)]
        # — segue o mesmo padrão do ``listar_processos`` para que ``numero_processo``
        # cruzando vários tribunais funcione (cada tribunal recebe só os seus CNJs).
        rows: List[Dict[str, Any]] = []
        for alias, cnjs in target_aliases:
            payload = build_contar_processos_payload(
                numero_processo=cnjs,
                ano_ajuizamento=inp.ano_ajuizamento,
                classe=inp.classe,
                assuntos=inp.assuntos,
            )
            api_response = call_datajud_api(
                base_url=self.BASE_API_URL,
                alias=alias,
                api_key=self.api_key,
                session=self.session,
                query_payload=payload,
                verbose=self.verbose > 1,
            )
            tribunal_sigla = ALIAS_TO_TRIBUNAL.get(alias, "")
            if api_response is None:
                rows.append({
                    "tribunal": tribunal_sigla,
                    "alias": alias,
                    "count": None,
                    "relation": None,
                    "error": "API call failed (see logs)",
                })
                continue
            total = api_response.get("hits", {}).get("total", {}) or {}
            rows.append({
                "tribunal": tribunal_sigla,
                "alias": alias,
                "count": int(total.get("value") or 0),
                "relation": total.get("relation", "eq"),
                "error": None,
            })
            time.sleep(self.sleep_time)
        return pd.DataFrame(rows)

    def _resolve_aliases(
        self,
        *,
        tribunal: Optional[str],
        numero_processo: Optional[Union[str, List[str]]],
    ) -> List[tuple]:
        """Determina lista de ``(alias, cnjs_para_esse_alias)``.

        Mesma lógica usada por :meth:`listar_processos` — extraída pra ser
        reutilizada por :meth:`contar_processos` sem duplicar código.
        """
        if tribunal:
            alias = TRIBUNAL_TO_ALIAS.get(tribunal.upper())
            if not alias:
                raise ValueError(
                    f"Tribunal {tribunal!r} não encontrado nos mappings do DataJud. "
                    f"Verifique a sigla (ex: TJSP, TRT2, TRE-SP)."
                )
            cnjs: Optional[Union[str, List[str]]] = numero_processo
            return [(alias, cnjs)]
        if numero_processo:
            processos_por_alias = defaultdict(list)
            cnjs_to_query = (
                [numero_processo] if isinstance(numero_processo, str) else numero_processo
            )
            for num_cnj in cnjs_to_query:
                num_limpo = clean_cnj(num_cnj)
                if len(num_limpo) == 20:
                    id_justica = num_limpo[13]
                    id_tribunal = num_limpo[14:16]
                    alias = ID_JUSTICA_TRIBUNAL_TO_ALIAS.get((id_justica, id_tribunal))
                    if alias:
                        processos_por_alias[alias].append(num_limpo)
                    else:
                        warnings.warn(
                            f"CNJ {num_cnj!r}: tribunal não mapeado no DataJud "
                            f"(id_justica={id_justica}, id_tribunal={id_tribunal}). "
                            f"Processo será ignorado.",
                            UserWarning,
                            stacklevel=2,
                        )
                else:
                    warnings.warn(
                        f"CNJ inválido: {num_cnj!r} (após limpeza tem {len(num_limpo)} "
                        f"dígitos, deveria ter 20). Processo será ignorado.",
                        UserWarning,
                        stacklevel=2,
                    )
            if not processos_por_alias:
                return []
            return [(alias, cnjs) for alias, cnjs in processos_por_alias.items()]
        raise ValueError(
            "É necessário especificar 'tribunal' (sigla) ou 'numero_processo' (CNJ)."
        )

    def listar_processos(
        self,
        paginas: Optional[Union[int, List[int], range]] = None,
        **kwargs,
    ) -> pd.DataFrame:
        """Lista processos do DataJud via API publica do CNJ.

        Filtros sao validados pelo schema :class:`InputListarProcessosDataJud`
        (``extra="forbid"``); kwargs desconhecidos viram ``TypeError`` com a
        mensagem ``DatajudScraper.listar_processos() got unexpected keyword
        argument(s): '<nome>'`` em vez de serem silenciosamente ignorados.

        Args:
            **kwargs: Filtros aceitos pelo schema
                :class:`InputListarProcessosDataJud`. Listados abaixo (todos
                opcionais; ``None`` = sem filtro):

                * ``numero_processo`` (str | list[str]): CNJ formatado ou
                  lista de CNJs. Quando informado sem ``tribunal``, o alias-
                  indice e inferido pelos digitos ``id_justica`` (pos. 14) +
                  ``id_tribunal`` (pos. 15-16). CNJs invalidos ou nao
                  mapeados emitem ``UserWarning`` e sao ignorados.
                * ``tribunal`` (str): Sigla do tribunal (ex.: ``"TJSP"``,
                  ``"TRT2"``, ``"TRE-SP"``). Mutuamente exclusivo com
                  inferencia via ``numero_processo``.
                * ``ano_ajuizamento`` (int | tuple[int, int] | list[int]):
                  Filtra por ano de ajuizamento. ``int`` = 1 ano. ``tuple``
                  = range inclusivo (ex.: ``(2020, 2024)``). ``list`` =
                  anos discretos (ex.: ``[2020, 2022]``). Backend recebe
                  ``range`` dual em ``dataAjuizamento`` (ISO + compacto)
                  por ano, OR-eds via ``should``.
                * ``classe`` (str | list[str]): Codigo da classe CNJ.
                  ``str`` vira ``match``, ``list`` vira ``terms``
                  (varios codigos OR-ed).
                * ``assuntos`` (list[str]): Lista de codigos de assuntos CNJ.
                * ``mostrar_movs`` (bool): Se ``True``, inclui
                  ``movimentos``/``movimentacoes`` no ``_source``. Default
                  ``False`` (paginacao mais leve).
                * ``paginas`` (int | list[int] | range): Intervalo 1-based.
                  Aceita as 4 formas do contrato unico (refs #118):
                  ``int`` (``3`` -> ``range(1, 4)``), ``list``
                  (``[3, 5]`` -> ``range(3, 6)``, baixa 3-5 contiguamente
                  porque o cursor ``search_after`` e forwards-only),
                  ``range`` (passthrough), ``None`` (default, todas).
                * ``tamanho_pagina`` (int): Hits por requisicao (default
                  5000, range 10-10000 conforme cap da API publica). Em
                  caso de ``HTTP 504``/``Timeout``, o client refaz a
                  chamada com ``size // 4`` automaticamente (1 retry,
                  ``UserWarning``); ainda assim, valores proximos de
                  10000 sao instaveis na pratica.

        Aliases deprecados:
            Sem aliases nesta API — DataJud nao tem ``pesquisa`` nem
            filtros de data baseados em ``DD/MM/AAAA``, entao o
            pipeline canonico ``normalize_pesquisa``/``normalize_datas``
            nao se aplica. Todos os filtros aceitam apenas o nome
            canonico listado acima.

        Raises:
            TypeError: Quando um kwarg desconhecido e passado (traduzido de
                ``ValidationError`` por ``raise_on_extra_kwargs``).
            ValidationError: Quando um filtro tem formato invalido (ex.:
                ``ano_ajuizamento`` nao-int).
            ValueError: Quando nem ``tribunal`` nem ``numero_processo`` sao
                informados, ou quando a sigla nao tem alias mapeado.

        Returns:
            pd.DataFrame: Um DataFrame com uma linha por processo. ``extra``
            do parser e passthrough do ``_source`` Elasticsearch — colunas
            seguem nomenclatura camelCase do CNJ.

        Exemplo:
            >>> import juscraper as jus
            >>> dj = jus.scraper("datajud")
            >>> df = dj.listar_processos(tribunal="TJSP", ano_ajuizamento=2023,
            ...                          classe="436", assuntos=["1127"],
            ...                          paginas=range(1, 3))

        See also:
            :class:`InputListarProcessosDataJud` — fonte da verdade dos
            filtros aceitos.
        """
        # ``paginas`` e int|list|range|None na API publica (contrato de
        # PaginasMixin). O cursor ``search_after`` da API DataJud e
        # forwards-only e o client interno consome ``.start``/``.stop``,
        # entao convertemos ``int``/``list`` para ``range`` contiguo aqui:
        # ``[3, 5]`` -> ``range(3, 6)`` baixa as paginas 3, 4 e 5.
        paginas_norm = normalize_paginas(paginas)
        if isinstance(paginas_norm, list):
            paginas_norm = (
                range(min(paginas_norm), max(paginas_norm) + 1)
                if paginas_norm
                else None
            )

        try:
            inp = InputListarProcessosDataJud(paginas=paginas_norm, **kwargs)
        except ValidationError as exc:
            raise_on_extra_kwargs(exc, "DatajudScraper.listar_processos()")
            raise

        numero_processo = inp.numero_processo
        tribunal = inp.tribunal
        ano_ajuizamento = inp.ano_ajuizamento
        classe = inp.classe
        assuntos = inp.assuntos
        mostrar_movs = inp.mostrar_movs
        tamanho_pagina = inp.tamanho_pagina

        all_dfs = []
        # Determine target aliases
        target_aliases = []
        if tribunal:
            alias = TRIBUNAL_TO_ALIAS.get(tribunal.upper())
            if alias:
                target_aliases.append(alias)
            else:
                raise ValueError(
                    f"Tribunal {tribunal!r} não encontrado nos mappings do DataJud. "
                    f"Verifique a sigla (ex: TJSP, TRT2, TRE-SP)."
                )
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
                        processos_por_alias[alias].append(num_limpo)
                    else:
                        warnings.warn(
                            f"CNJ {num_cnj!r}: tribunal não mapeado no DataJud "
                            f"(id_justica={id_justica_cnj}, id_tribunal={id_tribunal_cnj}). "
                            f"Processo será ignorado.",
                            UserWarning,
                            stacklevel=2,
                        )
                        logger.warning("Não foi possível determinar alias para CNJ: %s", num_cnj)
                else:
                    warnings.warn(
                        f"CNJ inválido: {num_cnj!r} (após limpeza tem {len(num_limpo)} "
                        f"dígitos, deveria ter 20). Processo será ignorado.",
                        UserWarning,
                        stacklevel=2,
                    )
                    logger.warning("CNJ inválido: %s", num_cnj)
            if not processos_por_alias:
                # Os warnings por CNJ (CNJ inválido / tribunal não mapeado) já
                # comunicam o problema. O `logger.error` mantém o registro de
                # que nenhum alias foi determinado sem duplicar o warning.
                logger.error("Nenhum CNJ válido para determinar tribunal/alias.")
                return pd.DataFrame()
            target_aliases = list(processos_por_alias.keys())
        else:
            raise ValueError(
                "É necessário especificar 'tribunal' (sigla) ou 'numero_processo' (CNJ)."
            )

        for alias_idx, alias_name in enumerate(target_aliases):
            logger.info("Consultando: %s (%d/%d)", alias_name, alias_idx+1, len(target_aliases))
            # If CNJs were grouped, use only the CNJs for this specific alias
            current_cnjs_for_alias: Optional[Union[str, List[str]]]
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
                paginas_range=paginas_norm,
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
        search_after_params: Optional[List[Any]] = None  # For deep pagination

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
                query_payload = build_listar_processos_payload(
                    numero_processo=numero_processo,
                    ano_ajuizamento=ano_ajuizamento,
                    classe=classe,
                    assuntos=assuntos,
                    mostrar_movs=mostrar_movs,
                    tamanho_pagina=tamanho_pagina,
                    search_after=search_after_params,
                )
                api_response_json = call_datajud_api(
                    base_url=self.BASE_API_URL,
                    alias=alias,
                    api_key=self.api_key,
                    session=self.session,
                    query_payload=query_payload,
                    verbose=self.verbose > 1  # Pass verbose flag for more detailed logging
                )

                if api_response_json is None:
                    warnings.warn(
                        f"DataJud: falha ao consultar alias {alias!r} na página "
                        f"{current_page}. Resultados parciais retornados.",
                        UserWarning,
                        stacklevel=3,
                    )
                    logger.error(
                        "Failed to get API response for alias %s, page %d."
                        "Stopping.",
                        alias,
                        current_page
                    )
                    break

                if current_page == (paginas_range.start if paginas_range else 1):
                    total_info = api_response_json.get("hits", {}).get("total", {})
                    total_value = total_info.get("value", "?")
                    total_relation = total_info.get("relation", "eq")
                    logger.info("Total de processos encontrados para %s: %s (%s)", alias, total_value, total_relation)

                df_page = parse_datajud_api_response(api_response_json, mostrar_movs)
                if df_page.empty:
                    logger.info(
                        "No more results for alias %s on page %d (or parsing failed).",
                        alias,
                        current_page
                    )
                    break
                dfs_alias.append(df_page)
                pbar.update(1)  # Update progress bar

                # For search_after pagination: extract the sort values of the last hit
                # This part depends on the exact structure of api_response_json
                # Assuming api_response_json is a dict parsed from the JSON string
                hits = api_response_json.get("hits", {}).get("hits", [])
                # Quando ``call_datajud_api`` aciona o fallback de 504/timeout,
                # ele muta ``query_payload["size"]`` em place. Propagamos o
                # size efetivo para ``tamanho_pagina`` para que paginas
                # subsequentes ja partam do size reduzido — em gateway
                # saturado consistentemente, isso evita pagar ~60s a cada
                # pagina antes de cair no fallback de novo.
                effective_size = query_payload.get("size", tamanho_pagina)
                if effective_size < tamanho_pagina:
                    tamanho_pagina = effective_size
                if not hits or len(hits) < effective_size:
                    logger.info(
                        "Last page reached for alias %s (less than %d results or no hits).",
                        alias,
                        effective_size,
                    )
                    break
                last_hit = hits[-1]
                search_after_params = last_hit.get("sort")
                if search_after_params is None:
                    logger.warning(
                        "Sort parameters for 'search_after' not found in last hit."
                        "Cannot continue deep pagination."
                    )
                    break  # Fallback or stop if search_after cannot be determined

                if paginas_range is None:  # if fetching all, continue
                    current_page += 1
                elif current_page < paginas_range.stop - 1:  # if in specified range, continue
                    current_page += 1
                else:  # reached end of specified range
                    break
                time.sleep(self.sleep_time)  # Respect sleep time
        finally:
            pbar.close()  # Ensure progress bar is closed

        if not dfs_alias:
            return pd.DataFrame()
        return pd.concat(dfs_alias, ignore_index=True)
