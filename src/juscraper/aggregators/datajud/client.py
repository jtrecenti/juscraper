"""
Orchestrates the flow for DATAJUD (user entry point) - API BASED
"""
import logging
import tempfile
import time
import warnings
from collections import defaultdict
from collections.abc import Iterator
from typing import Any, cast

import pandas as pd
from pydantic import ValidationError
from tqdm.auto import tqdm

from ...core.http import HTTPScraper
from ...utils.cnj import clean_cnj  # Assuming this utility exists and is relevant
from ...utils.params import normalize_paginas, pop_deprecated_alias, raise_on_extra_kwargs
from .download import build_contar_processos_payload, build_listar_processos_payload, call_datajud_api

# Import mappings for tribunal and justice aliases.
from .mappings import ID_JUSTICA_TRIBUNAL_TO_ALIAS, TIPOS_MOVIMENTACAO, TRIBUNAL_TO_ALIAS
from .parse import parse_datajud_api_response  # To be created for API response parsing
from .schemas import InputContarProcessosDataJud, InputListarProcessosDataJud

# Mapping inverso pra rotular o DataFrame devolvido por ``contar_processos``
# com a sigla do tribunal (não só o alias-índice do Elasticsearch).
ALIAS_TO_TRIBUNAL = {alias: sigla for sigla, alias in TRIBUNAL_TO_ALIAS.items()}

logger = logging.getLogger(__name__)

DatajudFilterInput = InputListarProcessosDataJud | InputContarProcessosDataJud
AliasSelection = tuple[str, str | list[str] | None]


def _pop_plural_aliases(kwargs: dict) -> None:
    """Popa aliases plurais deprecados antes de instanciar o schema.

    Refs #232 — singular canonico (``assunto``); ``assuntos`` (plural) emite
    :class:`DeprecationWarning` e segue funcionando. Passar plural + singular
    juntos -> :class:`ValueError` (uso conflitante).
    """
    if "assuntos" not in kwargs:
        return
    if kwargs.get("assunto") is not None:
        kwargs.pop("assuntos")
        raise ValueError(
            "Nao e possivel passar 'assunto' e 'assuntos' simultaneamente."
        )
    kwargs["assunto"] = pop_deprecated_alias(kwargs, "assuntos", "assunto")


def _resolve_movimentos_codigo(inp: DatajudFilterInput) -> list[int] | None:
    """Combina categorias amigáveis e códigos TPU preservando a ordem."""
    if not inp.tipos_movimentacao and not inp.movimentos_codigo:
        return None
    codigos = [
        codigo
        for tipo in inp.tipos_movimentacao or []
        for codigo in TIPOS_MOVIMENTACAO[tipo]
    ]
    codigos.extend(inp.movimentos_codigo or [])
    return list(dict.fromkeys(codigos))


def _resolve_cnj_alias(numero_processo: str) -> tuple[str, str] | None:
    """Resolve um CNJ para ``(alias, numero_limpo)`` ou emite o warning público."""
    numero_limpo = clean_cnj(numero_processo)
    if len(numero_limpo) != 20:
        warnings.warn(
            f"CNJ inválido: {numero_processo!r} (após limpeza tem {len(numero_limpo)} "
            "dígitos, deveria ter 20). Processo será ignorado.",
            UserWarning,
            stacklevel=3,
        )
        return None
    id_justica = numero_limpo[13]
    id_tribunal = numero_limpo[14:16]
    alias = ID_JUSTICA_TRIBUNAL_TO_ALIAS.get((id_justica, id_tribunal))
    if alias is not None:
        return alias, numero_limpo
    warnings.warn(
        f"CNJ {numero_processo!r}: tribunal não mapeado no DataJud "
        f"(id_justica={id_justica}, id_tribunal={id_tribunal}). Processo será ignorado.",
        UserWarning,
        stacklevel=3,
    )
    return None


def _group_cnjs_by_alias(numero_processo: str | list[str]) -> list[AliasSelection]:
    """Agrupa CNJs válidos pelo índice Elasticsearch correspondente."""
    processos_por_alias: dict[str, list[str]] = defaultdict(list)
    numeros = [numero_processo] if isinstance(numero_processo, str) else numero_processo
    for numero in numeros:
        resolved = _resolve_cnj_alias(numero)
        if resolved is None:
            continue
        alias, numero_limpo = resolved
        processos_por_alias[alias].append(numero_limpo)
    return list(processos_por_alias.items())


def _next_search_after(
    api_response: dict[str, Any],
    *,
    alias: str,
    effective_size: int,
) -> list[Any] | None:
    hits = api_response.get("hits", {}).get("hits", [])
    if not hits or len(hits) < effective_size:
        logger.info(
            "Last page reached for alias %s (less than %d results or no hits).",
            alias,
            effective_size,
        )
        return None
    search_after = hits[-1].get("sort")
    if not isinstance(search_after, list):
        logger.warning(
            "Sort parameters for 'search_after' not found in last hit. "
            "Cannot continue deep pagination."
        )
        return None
    return search_after


class DatajudScraper(HTTPScraper):
    """Scraper for CNJ's Datajud API.

    Note:
        Diferente de outros agregadores migrados em #204, o DataJud nao usa
        ``self._request_with_retry`` no caminho quente: a funcao
        :func:`download.call_datajud_api` aplica um retry especializado
        (504/Timeout -> refaz **1 vez** com ``size`` reduzido por
        ``FALLBACK_DIVISOR``), incompativel com o backoff exponencial do
        ``HTTPScraper``. A heranca aqui garante session/headers
        compartilhados e o cumprimento de #185, mas o transporte segue via
        :func:`call_datajud_api`.
    """

    # Chave pública oficial da API Pública do Datajud (CNJ): documentada e
    # idêntica para todos os usuários — não é um segredo vazado.
    DEFAULT_API_KEY = "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="
    BASE_API_URL = "https://api-publica.datajud.cnj.jus.br"

    # Schema pydantic detectado por ``tests/schemas/test_signature_parity._is_wired``.
    INPUT_LISTAR_PROCESSOS = InputListarProcessosDataJud

    def __init__(
        self,
        api_key: str | None = None,
        verbose: int = 1,
        download_path: str | None = None,  # For temporary files if needed
        sleep_time: float = 0.5,
    ):
        # Preserva o prefix historico ``datajud_api_`` para download_path
        # default. ``set_download_path`` (em ``BaseScraper``) usa
        # ``tempfile.mkdtemp()`` sem prefix, entao resolvemos aqui antes
        # de delegar ao ``HTTPScraper``.
        resolved_path = download_path or tempfile.mkdtemp(prefix="datajud_api_")
        super().__init__(
            "DatajudAPI",
            verbose=verbose,
            download_path=resolved_path,
            sleep_time=sleep_time,
        )
        self.api_key = api_key or self.DEFAULT_API_KEY
        logger.info(
            "DatajudScraper initialized. API Key: %s. Temp path: %s",
            "Provided" if api_key else "Default",
            self.download_path,
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
        ``assunto``, ``data_ajuizamento_inicio``/``_fim``,
        ``tipos_movimentacao``, ``movimentos_codigo``, ``orgao_julgador``,
        ``query``), excluindo apenas os parametros de paginacao
        (``paginas``, ``tamanho_pagina``, ``mostrar_movs``) — nao ha
        paginacao numa contagem. Veja a docstring de
        :meth:`listar_processos` para a semantica de cada filtro
        (formato dual ISO+compacto em ``dataAjuizamento``, mapping
        amigavel de ``tipos_movimentacao``, escape-hatch ``query``).

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
            ValidationError: Quando um filtro tem formato inválido (ex.:
                ``data_ajuizamento_*`` fora de ISO 8601), quando
                ``ano_ajuizamento`` coexiste com ``data_ajuizamento_*``,
                quando ``query`` coexiste com filtros amigaveis, ou
                quando um nome em ``tipos_movimentacao`` nao esta mapeado.
            ValueError: Quando nem ``tribunal`` nem ``numero_processo``
                são informados, ou quando a sigla não tem alias mapeado.

        Exemplo:
            >>> import juscraper as jus
            >>> dj = jus.scraper("datajud")
            >>> dj.contar_processos(tribunal="TJSP", ano_ajuizamento=2023, classe="436")
              tribunal             alias  count relation error
            0     TJSP  api_publica_tjsp  12345       eq   None

            >>> # Range de data ajuizamento + categoria de movimentacao
            >>> dj.contar_processos(
            ...     tribunal="TRF1",
            ...     data_ajuizamento_inicio="2024-01-01",
            ...     data_ajuizamento_fim="2024-03-31",
            ...     tipos_movimentacao=["decisao"],
            ... )

        See also:
            :meth:`listar_processos` — usa o mesmo conjunto de filtros mas
            baixa os processos.
        """
        _pop_plural_aliases(kwargs)
        try:
            inp = InputContarProcessosDataJud(**kwargs)
        except ValidationError as exc:
            raise_on_extra_kwargs(exc, "DatajudScraper.contar_processos()")
            raise

        target_aliases = self._resolve_aliases(
            tribunal=inp.tribunal,
            numero_processo=inp.numero_processo,
        )

        movimentos_codigo = _resolve_movimentos_codigo(inp)

        # ``_resolve_aliases`` devolve uma list[(alias, cnjs_pra_esse_alias)]
        # — segue o mesmo padrão do ``listar_processos`` para que ``numero_processo``
        # cruzando vários tribunais funcione (cada tribunal recebe só os seus CNJs).
        rows: list[dict[str, Any]] = []
        for alias, cnjs in target_aliases:
            payload = build_contar_processos_payload(
                numero_processo=cnjs,
                ano_ajuizamento=inp.ano_ajuizamento,
                classe=inp.classe,
                assunto=inp.assunto,
                data_ajuizamento_inicio=inp.data_ajuizamento_inicio,
                data_ajuizamento_fim=inp.data_ajuizamento_fim,
                movimentos_codigo=movimentos_codigo,
                orgao_julgador=inp.orgao_julgador,
                query=inp.query,
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
        tribunal: str | None,
        numero_processo: str | list[str] | None,
    ) -> list[AliasSelection]:
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
            return [(alias, numero_processo)]
        if numero_processo:
            return _group_cnjs_by_alias(numero_processo)
        raise ValueError(
            "É necessário especificar 'tribunal' (sigla) ou 'numero_processo' (CNJ)."
        )

    def listar_processos(
        self,
        paginas: int | list[int] | range | None = None,
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
                * ``ano_ajuizamento`` (int): Filtra por ano de ajuizamento.
                  Backend recebe ``range`` dual em ``dataAjuizamento`` (ISO
                  ``YYYY-01-01`` + compacto ``YYYYMMDDhhmmss``). Mutuamente
                  exclusivo com ``data_ajuizamento_inicio``/``_fim``.
                * ``data_ajuizamento_inicio`` / ``data_ajuizamento_fim`` (str):
                  Range de data de ajuizamento, formato ``YYYY-MM-DD`` (ISO
                  8601). Backend recebe ``bool.should`` com 2 ``range`` em
                  ``dataAjuizamento`` (ISO + compacto), mesmo padrao dual-
                  format do ``ano_ajuizamento`` (refs #51). Pode informar
                  apenas inicio, apenas fim, ou ambos. **Nao** ha alias
                  ``data_inicio``/``data_fim`` aqui (a convencao generica
                  do projeto mapeia esses para ``data_julgamento_*``, e o
                  DataJud filtra por ajuizamento, nao julgamento).
                * ``classe`` (str): Codigo da classe processual CNJ.
                * ``assunto`` (list[str | int]): Lista de codigos de
                  assuntos CNJ (TPU). Aceita int e str — int e a forma
                  natural (codigos TPU sao inteiros); str e aceita por
                  compatibilidade. O schema normaliza para str antes do
                  payload, ja que o Elasticsearch coage int -> str em
                  campos ``keyword``. Backend: ``terms`` em
                  ``assuntos.codigo``. ``assuntos`` (plural) e aceito como
                  alias deprecado. Refs #232.
                * ``tipos_movimentacao`` (list[str]): Nomes amigaveis de
                  categorias de movimentacao (ex.: ``["decisao", "sentenca"]``).
                  Resolvidos via ``TIPOS_MOVIMENTACAO`` para uma lista plana
                  de codigos TPU CNJ. Para nomes nao mapeados, usar
                  ``movimentos_codigo`` direto. Categorias atuais:
                  ``decisao``, ``sentenca``, ``julgamento``, ``tutela``,
                  ``transito_julgado``.
                * ``movimentos_codigo`` (list[int | str]): Codigos TPU
                  CNJ diretos. Aceita int e str — int e a forma natural;
                  str e aceita por conveniencia (ex.: vinda de planilha/
                  CSV) e normalizada para int antes do payload.
                  Concatenado com a lista resolvida de
                  ``tipos_movimentacao`` (uniao). Backend: ``terms`` em
                  ``movimentos.codigo``.
                * ``orgao_julgador`` (str): Nome do orgao julgador (ex.:
                  ``"Vara Civel de Brasilia"``). Backend: ``match`` em
                  ``orgaoJulgador.nome``.
                * ``query`` (dict): **Override total** da query Elasticsearch.
                  Quando fornecido, vira a chave ``query`` do payload
                  literalmente. Mutuamente exclusivo com TODOS os filtros
                  amigaveis acima (``numero_processo``, ``ano_ajuizamento``,
                  ``classe``, ``assunto``, ``data_ajuizamento_*``,
                  ``tipos_movimentacao``, ``movimentos_codigo``,
                  ``orgao_julgador``). Exige ``tribunal`` explicito (sem
                  inferencia via CNJ). Em troca, oferece paridade com
                  requisicao direta a ``/<alias>/_search`` —
                  ``must_not``, ``should`` com ``minimum_should_match``,
                  ``range`` em campos arbitrarios, ``wildcard``, ``nested``,
                  etc. ``size``/``sort``/``_source``/``search_after`` (paginacao)
                  continuam sendo controlados pela biblioteca. Shape oficial
                  documentado em https://datajud-wiki.cnj.jus.br/api-publica/.
                * ``mostrar_movs`` (bool): Se ``True``, inclui
                  ``movimentos``/``movimentacoes`` no ``_source``. Default
                  ``False`` (paginacao mais leve).
                * ``paginas`` (int | list[int] | range): Intervalo 1-based.
                  Aceita as 4 formas do contrato unico (refs #118):
                  ``int`` (``3`` -> ``range(1, 4)``), ``list``
                  (``[3, 5]`` -> ``range(3, 6)``, baixa 3-5 contiguamente
                  porque o cursor ``search_after`` e forwards-only),
                  ``range`` (respeita ``start``/``stop``/``step``) e ``None``
                  (default, todas). Como o cursor e sequencial, ranges que
                  comecam depois de 1 percorrem e descartam as paginas
                  anteriores antes de devolver apenas as solicitadas.
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
                ``ano_ajuizamento`` nao-int, ``data_ajuizamento_*`` fora de
                ISO 8601), quando ``ano_ajuizamento`` coexiste com
                ``data_ajuizamento_*``, quando ``query`` coexiste com
                filtros amigaveis, ou quando um nome em ``tipos_movimentacao``
                nao esta mapeado.
            ValueError: Quando nem ``tribunal`` nem ``numero_processo`` sao
                informados, ou quando a sigla nao tem alias mapeado.

        Returns:
            pd.DataFrame: Um DataFrame com uma linha por processo. ``extra``
            do parser e passthrough do ``_source`` Elasticsearch — colunas
            seguem nomenclatura camelCase do CNJ.

        Exemplo:
            >>> import juscraper as jus
            >>> dj = jus.scraper("datajud")
            >>> # Caminho amigavel: range de data + categoria de movimentacao
            >>> df = dj.listar_processos(
            ...     tribunal="TRF1",
            ...     data_ajuizamento_inicio="2024-01-01",
            ...     data_ajuizamento_fim="2024-03-31",
            ...     tipos_movimentacao=["decisao", "sentenca"],
            ...     paginas=range(1, 3),
            ... )
            >>> # Caminho query-override: paridade com requisicao direta
            >>> df = dj.listar_processos(
            ...     tribunal="TRF1",
            ...     query={
            ...         "bool": {
            ...             "must_not": [{"exists": {"field": "orgaoJulgador.nome"}}],
            ...             "should": [{"match": {"classe.nome": "tutela"}}],
            ...             "minimum_should_match": 1,
            ...         }
            ...     },
            ...     paginas=1,
            ... )

        See also:
            :class:`InputListarProcessosDataJud` — fonte da verdade dos
            filtros aceitos.
        """
        paginas_norm = normalize_paginas(paginas)
        _pop_plural_aliases(kwargs)
        try:
            inp = InputListarProcessosDataJud(paginas=paginas_norm, **kwargs)
        except ValidationError as exc:
            raise_on_extra_kwargs(exc, "DatajudScraper.listar_processos()")
            raise
        # ``normalize_paginas`` acima garante que ``int`` ja virou ``range``;
        # o cast registra essa invariante sem repetir a normalizacao. Listas
        # continuam virando o intervalo contiguo exigido pelo cursor forwards-only.
        paginas_datajud = cast(list[int] | range | None, inp.paginas)
        if isinstance(paginas_datajud, list):
            paginas_datajud = range(min(paginas_datajud), max(paginas_datajud) + 1)

        aliases = self._resolve_aliases(
            tribunal=inp.tribunal,
            numero_processo=inp.numero_processo,
        )
        movimentos_codigo = _resolve_movimentos_codigo(inp)
        frames = [
            self._listar_processos_por_alias(
                alias=alias,
                numero_processo=cnjs,
                inp=inp,
                movimentos_codigo=movimentos_codigo,
                paginas=paginas_datajud,
            )
            for alias, cnjs in aliases
        ]
        non_empty = [frame for frame in frames if not frame.empty]
        return pd.concat(non_empty, ignore_index=True) if non_empty else pd.DataFrame()

    def _listar_processos_por_alias(
        self,
        *,
        alias: str,
        numero_processo: str | list[str] | None,
        inp: InputListarProcessosDataJud,
        movimentos_codigo: list[int] | None,
        paginas: range | None,
    ) -> pd.DataFrame:
        """Percorre o cursor físico e agrega somente as páginas solicitadas."""
        frames: list[pd.DataFrame] = []
        total = None if paginas is None else len(paginas)
        pbar = tqdm(
            total=total,
            desc=f"Paginando {alias}",
            unit=" página",
            disable=total == 0,
        )
        try:
            for current_page, api_response in self._iter_process_pages(
                alias=alias,
                numero_processo=numero_processo,
                inp=inp,
                movimentos_codigo=movimentos_codigo,
                paginas=paginas,
            ):
                if paginas is not None and current_page not in paginas:
                    continue
                frame = parse_datajud_api_response(api_response, inp.mostrar_movs)
                if frame.empty:
                    logger.info(
                        "No more results for alias %s on page %d (or parsing failed).",
                        alias,
                        current_page,
                    )
                    break
                frames.append(frame)
                pbar.update(1)
        finally:
            pbar.close()

        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def _iter_process_pages(
        self,
        *,
        alias: str,
        numero_processo: str | list[str] | None,
        inp: InputListarProcessosDataJud,
        movimentos_codigo: list[int] | None,
        paginas: range | None,
    ) -> Iterator[tuple[int, dict[str, Any]]]:
        """Percorre o cursor físico até a última página necessária."""
        current_page = 1
        tamanho_pagina = inp.tamanho_pagina
        search_after: list[Any] | None = None
        last_page = None if paginas is None else paginas[-1]
        while last_page is None or current_page <= last_page:
            logger.info("Fetching page %d for alias %s...", current_page, alias)
            query_payload = build_listar_processos_payload(
                numero_processo=numero_processo,
                ano_ajuizamento=inp.ano_ajuizamento,
                classe=inp.classe,
                assunto=inp.assunto,
                data_ajuizamento_inicio=inp.data_ajuizamento_inicio,
                data_ajuizamento_fim=inp.data_ajuizamento_fim,
                movimentos_codigo=movimentos_codigo,
                orgao_julgador=inp.orgao_julgador,
                query=inp.query,
                mostrar_movs=inp.mostrar_movs,
                tamanho_pagina=tamanho_pagina,
                search_after=search_after,
            )
            api_response = call_datajud_api(
                base_url=self.BASE_API_URL,
                alias=alias,
                api_key=self.api_key,
                session=self.session,
                query_payload=query_payload,
                verbose=self.verbose > 1,
            )
            if api_response is None:
                warnings.warn(
                    f"DataJud: falha ao consultar alias {alias!r} na página "
                    f"{current_page}. Resultados parciais retornados.",
                    UserWarning,
                    stacklevel=3,
                )
                logger.error(
                    "Failed to get API response for alias %s, page %d. Stopping.",
                    alias,
                    current_page,
                )
                return
            if current_page == 1:
                total_info = api_response.get("hits", {}).get("total", {})
                logger.info(
                    "Total de processos encontrados para %s: %s (%s)",
                    alias,
                    total_info.get("value", "?"),
                    total_info.get("relation", "eq"),
                )
            effective_size = min(
                tamanho_pagina,
                query_payload.get("size", tamanho_pagina),
            )
            next_search_after = _next_search_after(
                api_response,
                alias=alias,
                effective_size=effective_size,
            )
            yield current_page, api_response
            if next_search_after is None:
                return
            search_after = next_search_after
            tamanho_pagina = effective_size
            current_page += 1
            if last_page is None or current_page <= last_page:
                time.sleep(self.sleep_time)
