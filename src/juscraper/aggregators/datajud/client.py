"""
Orchestrates the flow for DATAJUD (user entry point) - API BASED
"""
import functools
import logging
import math
import time
from collections import defaultdict
from collections.abc import Iterator, Mapping
from typing import Any, ClassVar, NamedTuple, NoReturn, cast

import pandas as pd
import requests
from pydantic import ValidationError
from tqdm.auto import tqdm

from ...core.avisos import avisar
from ...core.exceptions import ColetaParcialError, RetryExhaustedError
from ...core.http import HTTPScraper, RequestPolicy
from ...utils.cnj import clean_cnj  # Assuming this utility exists and is relevant
from ...utils.params import normalize_paginas, pop_deprecated_alias, raise_on_extra_kwargs
from .download import (
    STATUS_REPETIVEIS,
    build_contar_processos_payload,
    build_listar_processos_payload,
    call_datajud_api,
)

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


class _FimPagina(NamedTuple):
    """Contexto mínimo para diagnosticar o término de uma página."""

    alias: str
    pagina: int
    recebidos: int
    last_page: int | None


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
        avisar(
            f"CNJ inválido: {numero_processo!r} (após limpeza tem {len(numero_limpo)} "
            "dígitos, deveria ter 20). Processo será ignorado.",
            UserWarning,
        )
        return None
    id_justica = numero_limpo[13]
    id_tribunal = numero_limpo[14:16]
    alias = ID_JUSTICA_TRIBUNAL_TO_ALIAS.get((id_justica, id_tribunal))
    if alias is not None:
        return alias, numero_limpo
    avisar(
        f"CNJ {numero_processo!r}: tribunal não mapeado no DataJud "
        f"(id_justica={id_justica}, id_tribunal={id_tribunal}). Processo será ignorado.",
        UserWarning,
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


def _numero_positivo(valor: Any) -> bool:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return False
    # ``isfinite`` barra ``inf``, que passaria em ``> 0`` e faria o ``requests``
    # levantar ``OverflowError`` só na hora da requisição. O próprio
    # ``isfinite`` levanta ``OverflowError`` para inteiro que não cabe em
    # ``float``, e esse valor é recusado do mesmo jeito.
    try:
        return math.isfinite(valor) and valor > 0
    except OverflowError:
        return False


def _timeout_valido(timeout: Any) -> bool:
    """Número positivo e finito, ou par ``(conexão, leitura)`` deles, como o ``requests`` aceita.

    ``None`` fica de fora: no ``requests`` ele desliga o limite, e uma consulta
    pesada ao DataJud ficaria esperando indefinidamente.
    """
    if isinstance(timeout, (list, tuple)):
        return len(timeout) == 2 and all(_numero_positivo(v) for v in timeout)
    return _numero_positivo(timeout)


def _mensagem_falha_parcial(
    alias: str,
    pagina: int,
    recebidos: int,
    total_info: dict[str, Any] | None,
) -> str:
    """Diagnóstico da paginação interrompida, com quanto veio e quanto faltou.

    Vira a mensagem do ``ColetaParcialError``; os registros recebidos ficam
    em ``erro.resultado``.

    ``total_info`` é o ``hits.total`` da página 1, que a consulta já traz
    (``track_total_hits``); é ``None`` quando a falha foi na própria página 1.
    ``relation == "gte"`` indica total truncado pelo Elasticsearch, então o
    texto diz "pelo menos".
    """
    inicio = f"DataJud: falha ao consultar alias {alias!r} na página {pagina}."
    if total_info is None:
        return (
            f"{inicio} Resultados parciais em erro.resultado: nenhum registro recebido. "
            "Se a falha foi timeout, reduza o recorte (por exemplo, com "
            "data_ajuizamento_inicio/_fim) ou aumente o timeout com "
            "politica={'busca': {'timeout': ...}}."
        )
    recebidos_txt = f"{inicio} Resultados parciais em erro.resultado: {recebidos} registro(s) recebido(s)"
    total = total_info.get("value")
    if not isinstance(total, int):
        return f"{recebidos_txt}; a consulta não informou o total encontrado."
    total_txt = str(total) if total_info.get("relation", "eq") == "eq" else f"pelo menos {total}"
    return f"{recebidos_txt} de {total_txt} encontrado(s) pela consulta."


FALHAS_DE_TRANSPORTE: tuple[type[Exception], ...] = (requests.RequestException, RetryExhaustedError)
"""Exceções de :func:`call_datajud_api` que viram falha da consulta, e não erro de programação."""


def _descrever_causa(exc: Exception) -> str:
    """Resume a falha de transporte para a mensagem do erro, com o status HTTP quando houver."""
    if isinstance(exc, RetryExhaustedError):
        return f"HTTP {exc.status_code} em todas as {exc.attempts} tentativas"
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if isinstance(exc, requests.HTTPError) and status is not None:
        return f"HTTP {status}"
    if isinstance(exc, requests.Timeout):
        return "timeout"
    return f"{type(exc).__name__}: {exc}"


def _falha_pagina(mensagem: str, causa: Exception) -> NoReturn:
    """Propaga falha de página com a causa original preservada."""
    raise ColetaParcialError(
        mensagem,
        resultado=pd.DataFrame(),
        falhas=[(None, None, causa)],
    ) from causa


def _total_primeira_pagina(api_response: dict[str, Any], alias: str, pagina: int) -> dict[str, Any]:
    """Valida o total informado pela primeira página."""
    total_info = api_response.get("hits", {}).get("total")
    if total_info is not None and not isinstance(total_info, dict):
        causa = ValueError("Campo 'hits.total' da resposta DataJud deve ser um objeto.")
        mensagem = (
            f"{_mensagem_falha_parcial(alias, pagina, 0, None)} "
            "Resposta inválida: campo 'hits.total' deve ser um objeto."
        )
        _falha_pagina(mensagem, causa)
    total_info = total_info or {}
    logger.info(
        "Total de processos encontrados para %s: %s (%s)",
        alias,
        total_info.get("value", "?"),
        total_info.get("relation", "eq"),
    )
    return total_info


def _hits_da_pagina(
    api_response: dict[str, Any],
    alias: str,
    pagina: int,
    recebidos: int,
    total_info: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Valida a estrutura dos resultados antes do uso do cursor."""
    diagnostico = _mensagem_falha_parcial(alias, pagina, recebidos, total_info)
    hits_obj = api_response.get("hits")
    if not isinstance(hits_obj, dict):
        causa: Exception = TypeError("Campo 'hits' da resposta DataJud deve ser um objeto.")
        _falha_pagina(f"{diagnostico} Resposta inválida: campo 'hits' deve ser um objeto.", causa)
    if "hits" not in hits_obj:
        causa = ValueError("Campo obrigatório 'hits.hits' ausente na resposta DataJud.")
        _falha_pagina(f"{diagnostico} Resposta inválida: campo 'hits.hits' ausente.", causa)
    hits = hits_obj["hits"]
    if not isinstance(hits, list):
        causa = ValueError("Campo 'hits.hits' da resposta DataJud deve ser uma lista.")
        _falha_pagina(f"{diagnostico} Resposta inválida: campo 'hits.hits' deve ser uma lista.", causa)
    if any(not isinstance(hit, dict) for hit in hits):
        causa = TypeError("Cada elemento de 'hits.hits' da resposta DataJud deve ser um objeto.")
        _falha_pagina(f"{diagnostico} Resposta inválida: cada hit deve ser um objeto.", causa)
    return hits


def _verificar_termino_prematuro(
    hits: list[dict[str, Any]],
    effective_size: int,
    total_info: dict[str, Any] | None,
    percorridos: int,
    contexto: _FimPagina,
) -> None:
    """Sinaliza página vazia ou curta antes do total exato.

    Vale com e sem ``paginas``: ``percorridos`` conta todas as páginas
    percorridas pelo cursor, inclusive as que ``paginas`` descarta, então
    uma página curta antes do total é falha mesmo quando a última página
    pedida ainda não chegou.
    """
    total_exato = _total_exato(total_info)
    if total_exato is None or percorridos >= total_exato:
        return
    if not hits:
        causa = RuntimeError("Página vazia antes de alcançar o total exato da consulta.")
    elif len(hits) < effective_size:
        causa = RuntimeError("Página curta antes de alcançar o total exato da consulta.")
    else:
        return
    diagnostico = _mensagem_falha_parcial(contexto.alias, contexto.pagina, contexto.recebidos, total_info)
    _falha_pagina(f"{diagnostico} Paginação encerrada prematuramente: {causa}", causa)


def _total_exato(total_info: dict[str, Any] | None) -> int | None:
    """Total informado pela consulta quando exato (``relation == "eq"``); ``None`` nos outros casos."""
    if not total_info or total_info.get("relation", "eq") != "eq":
        return None
    total = total_info.get("value")
    return total if isinstance(total, int) and not isinstance(total, bool) else None


def _verificar_fim_pagina(
    hits: list[dict[str, Any]],
    effective_size: int,
    total_info: dict[str, Any] | None,
    percorridos: int,
    contexto: _FimPagina,
) -> None:
    """Verifica cursor pendente e término prematuro após consumir a página."""
    total_exato = _total_exato(total_info)
    cursor_ausente = len(hits) >= effective_size and not isinstance(hits[-1].get("sort"), list)
    pagina_pendente = contexto.last_page is None or contexto.pagina < contexto.last_page
    total_esgotado = total_exato is not None and percorridos >= total_exato
    if cursor_ausente and pagina_pendente and not total_esgotado:
        mensagem = (
            f"DataJud: cursor search_after ausente no alias {contexto.alias!r} "
            f"após a página {contexto.pagina}; não foi possível consultar a próxima página."
        )
        _falha_pagina(mensagem, RuntimeError(mensagem))
    _verificar_termino_prematuro(hits, effective_size, total_info, percorridos, contexto)


def _verificar_pagina_vazia(
    hits: list[dict[str, Any]],
    effective_size: int,
    total_info: dict[str, Any] | None,
    percorridos: int,
    contexto: _FimPagina,
) -> None:
    """Detecta página vazia inconsistente antes de entregá-la ao consumidor."""
    if not hits:
        _verificar_termino_prematuro(hits, effective_size, total_info, percorridos, contexto)


def _parse_pagina(
    api_response: dict[str, Any],
    *,
    mostrar_movs: bool,
    diagnostico: str,
) -> pd.DataFrame:
    """Converte uma página; a falha sobe como coleta parcial."""
    try:
        return parse_datajud_api_response(api_response, mostrar_movs)
    except Exception as exc:
        raise ColetaParcialError(
            f"{diagnostico} Erro ao parsear a resposta.",
            resultado=pd.DataFrame(),
            falhas=[(None, None, exc)],
        ) from exc


def _verificar_data_frame_vazio(
    api_response: dict[str, Any],
    alias: str,
    pagina: int,
    recebidos: int,
    total_info: dict[str, Any] | None,
) -> None:
    """Distingue fim vazio legítimo de hits que não geraram dados úteis."""
    if not api_response["hits"]["hits"]:
        return
    causa = ValueError("A página contém hits, mas não produziu dados utilizáveis no DataFrame.")
    mensagem = (
        f"{_mensagem_falha_parcial(alias, pagina, recebidos, total_info)} "
        "A resposta continha hits, mas o parsing não produziu dados utilizáveis."
    )
    _falha_pagina(mensagem, causa)


def _total_para_diagnostico(
    api_response: dict[str, Any],
    pagina: int,
    total_info: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Guarda o total da primeira página para diagnosticar falhas posteriores."""
    if pagina != 1:
        return total_info
    hits = api_response.get("hits")
    if isinstance(hits, dict) and isinstance(hits.get("total"), dict):
        return cast(dict[str, Any], hits["total"])
    return total_info


class DatajudScraper(HTTPScraper):
    """Scraper for CNJ's Datajud API.

    Note:
        Cada busca passa pelo ``self._request_with_retry`` com o perfil
        ``"busca"``, que repete 429, 502 e 503 com espera. Por cima dele,
        :func:`download.call_datajud_api` trata 504 e timeout refazendo a
        busca **uma vez** com ``size`` reduzido por ``FALLBACK_DIVISOR``.
    """

    # Chave pública oficial da API Pública do Datajud (CNJ): documentada e
    # idêntica para todos os usuários — não é um segredo vazado.
    DEFAULT_API_KEY = "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="
    BASE_API_URL = "https://api-publica.datajud.cnj.jus.br"

    # Schema pydantic detectado por ``tests/schemas/test_signature_parity._is_wired``.
    INPUT_LISTAR_PROCESSOS = InputListarProcessosDataJud

    PREFIXO_DIRETORIO_TEMPORARIO = "datajud_api_"

    # Um perfil só, para ``listar_processos`` e ``contar_processos``. Cada busca
    # passa pelo ``_request_with_retry`` do core, que repete os
    # ``STATUS_REPETIVEIS`` com espera; o 504 e o timeout chegam ao
    # ``call_datajud_api``, que refaz a busca uma vez com ``size`` menor. Os
    # status repetíveis e o retry em timeout ficam fixos, porque mudá-los
    # desligaria esse fallback; ``__init__`` recusa ajuste deles em vez de
    # ignorá-lo.
    perfis_http: ClassVar[Mapping[str, RequestPolicy]] = {
        "busca": RequestPolicy(timeout=60, retryable_statuses=STATUS_REPETIVEIS),
    }
    CAMPOS_POLITICA_SUPORTADOS: ClassVar[frozenset[str]] = frozenset(
        {"timeout", "max_retries", "base_backoff"}
    )

    def __init__(
        self,
        api_key: str | None = None,
        verbose: int = 1,
        download_path: str | None = None,  # For temporary files if needed
        sleep_time: float = 0.5,
        politica: Mapping[str, Mapping[str, Any]] | None = None,
    ):
        """Cria o raspador do DataJud.

        Args:
            api_key: Chave da API pública. Default: a chave pública do CNJ.
            verbose: Nível de log; acima de 1, loga cada requisição.
            download_path: Diretório temporário. Default: ``mkdtemp``, criado
                só se ``download_path`` for lido; o DataJud não grava nele.
            sleep_time: Pausa, em segundos, entre páginas.
            politica: Ajuste do perfil HTTP ``"busca"``, usado por
                :meth:`listar_processos` e :meth:`contar_processos`, como em
                ``politica={"busca": {"timeout": 180, "max_retries": 5}}``.
                Aceita três campos. ``timeout`` (default 60 s) é um número
                positivo e finito de segundos ou o par ``(conexão, leitura)``;
                ``None``, que esperaria indefinidamente, é recusado. Consultas
                grandes podem passar de 60 s já na primeira página.
                ``max_retries`` (default 3, contando a primeira) e
                ``base_backoff`` (default 2, espera de ``base_backoff **
                tentativa`` segundos, ou o ``Retry-After`` numérico) regem as
                novas tentativas em HTTP 429, 502 e 503, como o 429 que o
                DataJud devolve quando a fila de busca enche.

        Raises:
            ValueError: Quando ``politica`` cita perfil desconhecido, campo
                fora dos três aceitos ou valor inválido.
        """
        # Valida antes do core: campo sem efeito no DataJud não chega a ser
        # validado (com outra mensagem, ou outro tipo de erro) pela
        # ``RequestPolicy``.
        self._validar_politica(politica)
        super().__init__(
            "DatajudAPI",
            verbose=verbose,
            download_path=download_path,
            sleep_time=sleep_time,
            politica=politica,
        )
        self.api_key = api_key or self.DEFAULT_API_KEY
        # Sem o caminho temporário no log: ler ``download_path`` criaria o
        # diretório, que o DataJud não usa.
        logger.info(
            "DatajudScraper initialized. API Key: %s.",
            "Provided" if api_key else "Default",
        )

    @classmethod
    def _validar_politica(cls, politica: Mapping[str, Any] | None) -> None:
        """Recusa em ``politica=`` o que o transporte do DataJud não usa ou não aceita.

        Roda antes do ``HTTPScraper.__init__`` para que ``retryable_statuses`` e afins
        recebam a explicação do DataJud. Perfil desconhecido e ajuste que não
        é dict são pulados e ficam com a mensagem do core, que os valida em
        seguida. O perfil desconhecido é pulado mesmo com campo recusado: a
        mensagem de campo citaria um perfil que o raspador não declara.
        """
        for nome, ajuste in (politica or {}).items():
            if nome not in cls.perfis_http or not isinstance(ajuste, Mapping):
                continue
            nao_suportados = set(ajuste) - cls.CAMPOS_POLITICA_SUPORTADOS
            if nao_suportados:
                raise ValueError(
                    f"DatajudScraper só aceita {sorted(cls.CAMPOS_POLITICA_SUPORTADOS)} "
                    f"em politica={{{nome!r}: ...}}; recebido {sorted(nao_suportados)}. "
                    "Os demais ficam fixos para não desligar o fallback de size em 504 e timeout."
                )
            if "timeout" in ajuste and not _timeout_valido(ajuste["timeout"]):
                raise ValueError(
                    f"timeout inválido em politica={{{nome!r}: ...}}: {ajuste['timeout']!r}. "
                    "Use um número positivo e finito de segundos ou o par (conexão, leitura)."
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
            motivo, com o status HTTP quando houver (``"HTTP 401"``).

        Raises:
            TypeError: Quando um kwarg desconhecido é passado.
            ValidationError: Quando um filtro tem formato inválido (ex.:
                ``data_ajuizamento_*`` fora de ISO 8601), quando
                ``ano_ajuizamento`` coexiste com ``data_ajuizamento_*``,
                quando ``query`` coexiste com filtros amigaveis, ou
                quando um nome em ``tipos_movimentacao`` nao esta mapeado.
            ValueError: Quando nem ``tribunal`` nem ``numero_processo``
                são informados, ou quando a sigla não tem alias mapeado.

        Examples: Exemplo
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
            tribunal_sigla = ALIAS_TO_TRIBUNAL.get(alias, "")
            try:
                api_response = self._buscar(alias, payload)
            except FALHAS_DE_TRANSPORTE as exc:
                logger.warning("DataJud: contagem do alias %s falhou: %s", alias, exc)
                rows.append({
                    "tribunal": tribunal_sigla,
                    "alias": alias,
                    "count": None,
                    "relation": None,
                    "error": _descrever_causa(exc),
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

    def _buscar(self, alias: str, query_payload: dict[str, Any]) -> dict[str, Any]:
        """Busca no alias pelo perfil ``"busca"``; falhas sobem como em :func:`call_datajud_api`."""
        return call_datajud_api(
            base_url=self.BASE_API_URL,
            alias=alias,
            api_key=self.api_key,
            requisitar=functools.partial(self._request_with_retry, perfil="busca"),
            query_payload=query_payload,
            verbose=self.verbose > 1,
        )

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
            ColetaParcialError: Se uma falha HTTP, de parsing ou de paginação
                impedir a conclusão da coleta. ``erro.resultado`` contém os
                registros preservados e ``erro.falhas`` contém as causas. Na
                falha HTTP, a causa é a exceção original: ``requests.HTTPError``
                (status em ``.response.status_code``), ``RetryExhaustedError``
                (429, 502 ou 503 em todas as tentativas, status em
                ``.status_code``), ``requests.Timeout`` ou erro de conexão.

        Returns:
            pd.DataFrame: Um DataFrame com uma linha por processo. ``extra``
            do parser e passthrough do ``_source`` Elasticsearch — colunas
            seguem nomenclatura camelCase do CNJ.

        Examples: Exemplo
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
        frames = []
        falhas = []
        diagnosticos = []
        for alias, cnjs in aliases:
            try:
                frame = self._listar_processos_por_alias(
                    alias=alias,
                    numero_processo=cnjs,
                    inp=inp,
                    movimentos_codigo=movimentos_codigo,
                    paginas=paginas_datajud,
                )
            except ColetaParcialError as exc:
                frame = exc.resultado
                falhas.extend(exc.falhas)
                diagnosticos.append(str(exc))
            frames.append(frame)

        non_empty = [frame for frame in frames if not frame.empty]
        resultado = pd.concat(non_empty, ignore_index=True) if non_empty else pd.DataFrame()
        if falhas:
            mensagem = "DataJud: coleta parcial. " + "; ".join(diagnosticos)
            raise ColetaParcialError(mensagem, resultado=resultado, falhas=falhas) from falhas[0][2]
        return resultado

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
        total_info = None
        recebidos = 0
        try:
            for current_page, api_response in self._iter_process_pages(
                alias=alias,
                numero_processo=numero_processo,
                inp=inp,
                movimentos_codigo=movimentos_codigo,
                paginas=paginas,
            ):
                # Antes do ``continue``: com ``paginas`` que pula a página 1, o
                # total dela ainda alimenta o diagnóstico de falha posterior.
                total_info = _total_para_diagnostico(api_response, current_page, total_info)
                if paginas is not None and current_page not in paginas:
                    continue
                frame = _parse_pagina(
                    api_response,
                    mostrar_movs=inp.mostrar_movs,
                    diagnostico=_mensagem_falha_parcial(
                        alias, current_page, recebidos, total_info or {},
                    ),
                )
                if frame.empty:
                    _verificar_data_frame_vazio(
                        api_response, alias, current_page, recebidos, total_info,
                    )
                    logger.info(
                        "No more results for alias %s on page %d.",
                        alias,
                        current_page,
                    )
                    break
                frames.append(frame)
                recebidos += len(frame)
                pbar.update(1)
        except ColetaParcialError as exc:
            exc.resultado = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
            raise
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
        # Alimentam o diagnóstico do ColetaParcialError: quanto já veio das páginas pedidas e
        # quanto a consulta encontrou (``hits.total`` da página 1).
        recebidos = 0
        percorridos = 0
        total_info: dict[str, Any] | None = None
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
            try:
                api_response = self._buscar(alias, query_payload)
            except FALHAS_DE_TRANSPORTE as exc:
                mensagem = _mensagem_falha_parcial(alias, current_page, recebidos, total_info)
                _falha_pagina(f"{mensagem} Causa: {_descrever_causa(exc)}.", exc)
            hits = _hits_da_pagina(api_response, alias, current_page, recebidos, total_info)
            if current_page == 1:
                total_info = _total_primeira_pagina(api_response, alias, current_page)
            effective_size = min(
                tamanho_pagina,
                query_payload.get("size", tamanho_pagina),
            )
            percorridos += len(hits)
            next_search_after = _next_search_after(
                api_response,
                alias=alias,
                effective_size=effective_size,
            )
            if paginas is None or current_page in paginas:
                recebidos += len(hits)
            contexto = _FimPagina(alias, current_page, recebidos, last_page)
            _verificar_pagina_vazia(hits, effective_size, total_info, percorridos, contexto)
            yield current_page, api_response
            if next_search_after is None:
                _verificar_fim_pagina(hits, effective_size, total_info, percorridos, contexto)
                return
            search_after = next_search_after
            tamanho_pagina = effective_size
            current_page += 1
            if last_page is None or current_page <= last_page:
                time.sleep(self.sleep_time)
