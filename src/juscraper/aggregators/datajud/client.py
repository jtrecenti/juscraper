"""
Orchestrates the flow for DATAJUD (user entry point) - API BASED
"""
import functools
import logging
import time
from collections import defaultdict
from collections.abc import Callable, Iterator, Mapping
from typing import Any, ClassVar

import pandas as pd
import requests
from pydantic import ValidationError
from tqdm.auto import tqdm

from ...core.avisos import avisar
from ...core.exceptions import ColetaParcialError, RetryExhaustedError
from ...core.failures import (
    FALHAS_DE_TRANSPORTE,
    anotar_falhas_anteriores,
    e_token_invalido,
    exemplos_do_aviso,
    motivo_falha,
)
from ...core.http import HTTPScraper, RequestPolicy, timeout_valido
from ...utils.cnj import clean_cnj  # Assuming this utility exists and is relevant
from ...utils.pagination import Paginas, maior_pagina, pagina_pedida, paginas_unicas
from ...utils.params import normalize_paginas, pop_deprecated_alias, raise_on_extra_kwargs
from .download import (
    STATUS_REPETIVEIS,
    build_contar_processos_payload,
    build_listar_processos_payload,
    call_datajud_api,
)

# Import mappings for tribunal and justice aliases.
from .mappings import ID_JUSTICA_TRIBUNAL_TO_ALIAS, TIPOS_MOVIMENTACAO, TRIBUNAL_TO_ALIAS
from .paginacao import (
    _descrever_resposta_parcial,
    _falha_pagina,
    _FimPagina,
    _hits_da_pagina,
    _mensagem_falha_parcial,
    _next_search_after,
    _size_do_pedaco,
    _teto_apos_busca,
    _total_primeira_pagina,
    _verificar_data_frame_vazio,
    _verificar_fim_pagina,
    _verificar_pagina_vazia,
    _verificar_resposta_parcial,
)
from .parse import contagem_da_resposta, parse_datajud_api_response
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


def _e_timeout_de_leitura(exc: Exception) -> bool:
    """``Timeout`` que não é de conexão: ``ConnectTimeout`` também herda de ``ConnectionError``."""
    return isinstance(exc, requests.Timeout) and not isinstance(exc, requests.ConnectionError)


def _descrever_causa(exc: Exception) -> str:
    """Resume a falha de transporte para a mensagem do erro, com o status HTTP quando houver."""
    if isinstance(exc, RetryExhaustedError):
        return f"HTTP {exc.status_code} em todas as {exc.attempts} tentativas"
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if isinstance(exc, requests.HTTPError) and status is not None:
        return f"HTTP {status}"
    if _e_timeout_de_leitura(exc):
        return "timeout"
    return f"{type(exc).__name__}: {exc}"


def _timeout_com_prazo(timeout: object) -> bool:
    """:func:`timeout_valido` sem ``None``, que desligaria o prazo de uma consulta pesada."""
    return timeout_valido(timeout, aceita_none=False)


def _relancar_se_token_invalido(exc: Exception, linhas: list[dict[str, Any]]) -> None:
    """Relança o 401 de :meth:`DatajudScraper.contar_processos`, com as falhas de ``linhas`` numa nota.

    Raises:
        requests.HTTPError: O próprio ``exc``, quando é o 401 da chave inválida.
    """
    if e_token_invalido(exc):
        anteriores = [f"{linha['alias']}: {linha['error']}" for linha in linhas if linha["error"] is not None]
        anotar_falhas_anteriores(exc, anteriores, "contagem(ns) de tribunal")
        raise exc


def _aliases_nao_consultados(restantes: list[AliasSelection]) -> str:
    """Diagnóstico dos aliases que :meth:`DatajudScraper.listar_processos` deixa de consultar depois do 401."""
    nomes = ", ".join(exemplos_do_aviso([repr(alias) for alias, _ in restantes]))
    return f"HTTP 401 (chave da API recusada): alias(es) não consultado(s): {nomes}"


def _linha_de_falha(tribunal: str, alias: str, exc: Exception) -> dict[str, Any]:
    """Linha do tribunal cuja contagem falhou; ``error`` no vocabulário de ``motivo_falha`` ou ``"<Classe>: <msg>"``."""
    logger.warning("DataJud: contagem do alias %s falhou: %s", alias, exc)
    try:
        motivo = motivo_falha(exc)
    except TypeError:
        motivo = f"{type(exc).__name__}: {exc}"
    return {"tribunal": tribunal, "alias": alias, "count": None, "relation": None, "error": motivo}


DICA_TIMEOUT = (
    " Reduza o recorte (por exemplo, com data_ajuizamento_inicio/_fim) ou aumente "
    "o timeout com politica={'busca': {'timeout': ...}}."
)


def _sufixo_causa(exc: Exception) -> str:
    """Fecha a mensagem da falha de transporte com a causa e, no timeout, o que ajustar."""
    dica = DICA_TIMEOUT if _e_timeout_de_leitura(exc) else ""
    return f" Causa: {_descrever_causa(exc)}.{dica}"


def _parse_pagina(
    api_response: dict[str, Any],
    *,
    mostrar_movs: bool,
    diagnostico: str,
) -> pd.DataFrame:
    """Converte uma página; a falha sobe como coleta parcial, com a resposta parcial da página, se houver."""
    try:
        return parse_datajud_api_response(api_response, mostrar_movs)
    except Exception as exc:
        partes = (diagnostico, _descrever_resposta_parcial(api_response), "Erro ao parsear a resposta.")
        raise ColetaParcialError(
            " ".join(filter(None, partes)),
            resultado=pd.DataFrame(),
            falhas=[(None, None, exc)],
        ) from exc


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

    # Schema pydantic da API publica (``extra="forbid"``) de ``listar_processos``.
    INPUT_LISTAR_PROCESSOS = InputListarProcessosDataJud

    PREFIXO_DIRETORIO_TEMPORARIO = "datajud_api_"

    # Um perfil só, para ``listar_processos`` e ``contar_processos``. Os status
    # repetíveis e o retry em timeout ficam fixos: com o 504 entre os status, o
    # fallback de ``size`` descrito no Note da classe não agiria, e o retry em
    # timeout o adiaria. ``__init__`` recusa ajuste deles em vez de ignorá-lo e
    # valida os campos aceitos, cada um com a regra e a dica de
    # ``VALIDADORES_POLITICA``.
    perfis_http: ClassVar[Mapping[str, RequestPolicy]] = {
        "busca": RequestPolicy(timeout=60, retryable_statuses=STATUS_REPETIVEIS),
    }
    VALIDADORES_POLITICA: ClassVar[Mapping[str, tuple[Callable[[Any], bool], str]]] = {
        "timeout": (
            _timeout_com_prazo,
            "Use um número positivo e finito de segundos ou o par (conexão, leitura).",
        ),
    }
    # Os campos além do ``timeout`` são validados pela ``RequestPolicy``.
    CAMPOS_POLITICA_SUPORTADOS: ClassVar[frozenset[str]] = frozenset(
        {"timeout", "max_retries", "base_backoff", "max_backoff", "max_retry_after"}
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
            sleep_time: Pausa, em segundos, entre páginas e, em
                :meth:`contar_processos`, entre tribunais.
            politica: Ajuste do perfil HTTP ``"busca"``, usado por
                :meth:`listar_processos` e :meth:`contar_processos`, como em
                ``politica={"busca": {"timeout": 180, "max_retries": 5}}``.
                Aceita cinco campos. ``timeout`` (default 60 s) é um número
                positivo e finito de segundos ou o par ``(conexão, leitura)``;
                ``None``, que esperaria indefinidamente, é recusado. Consultas
                grandes podem passar de 60 s já na primeira página.
                ``max_retries`` (default 3, contando a primeira),
                ``base_backoff`` (default 2, espera de ``base_backoff **
                tentativa`` segundos, ou o ``Retry-After`` numérico),
                ``max_backoff`` (default 300, teto em segundos dessa espera
                exponencial) e ``max_retry_after`` (default 300, teto em
                segundos do ``Retry-After``) regem as novas tentativas em HTTP
                429, 502 e 503, como o 429 que o DataJud devolve quando a fila
                de busca enche.

        Raises:
            ValueError: Quando ``politica`` cita perfil desconhecido, campo
                fora dos cinco aceitos ou valor inválido.
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
                    "Os demais ficam fixos: com o 504 entre os status repetíveis, o fallback "
                    "de size não agiria, e o retry em timeout o adiaria."
                )
            for campo, (valido, dica) in cls.VALIDADORES_POLITICA.items():
                if campo in ajuste and not valido(ajuste[campo]):
                    raise ValueError(
                        f"{campo} inválido em politica={{{nome!r}: ...}}: {ajuste[campo]!r}. {dica}"
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
                :class:`InputContarProcessosDataJud`, os mesmos de
                :meth:`listar_processos`, onde está a semântica de cada um:

                * ``numero_processo`` (str | list[str] | None): CNJ ou lista
                  de CNJs; sem ``tribunal``, o índice vem dos dígitos do CNJ.
                * ``tribunal`` (str | None): Sigla do tribunal (``"TJSP"``).
                * ``ano_ajuizamento`` (int | None): Ano de ajuizamento.
                * ``classe`` (str | None): Código da classe processual CNJ.
                * ``assunto`` (list[str | int] | None): Códigos de assuntos
                  CNJ. ``assuntos`` (plural) é aceito como alias deprecado.
                * ``data_ajuizamento_inicio`` / ``data_ajuizamento_fim``
                  (str | None): Intervalo de ajuizamento em ``YYYY-MM-DD``.
                * ``tipos_movimentacao`` (list[str] | None): Categorias de
                  movimentação (``"decisao"``, ``"sentenca"``...).
                * ``movimentos_codigo`` (list[int | str] | None): Códigos TPU
                  de movimentos.
                * ``orgao_julgador`` (str | None): Nome do órgão julgador.
                * ``query`` (dict[str, Any] | None): Query Elasticsearch que
                  substitui todos os filtros acima.

        Returns:
            Uma linha por tribunal consultado, com colunas
                ``tribunal`` (sigla), ``alias`` (índice ES), ``count``
                (inteiro anulável ``Int64``) e ``relation`` (``"eq"`` exato ou
                ``"gte"`` truncado pelo cap interno do Elasticsearch). Quando a
                chamada falha para um tribunal, ``count`` é ``<NA>`` e a coluna
                ``error`` traz o motivo no vocabulário de
                ``juscraper.core.failures.motivo_falha`` (``"http_500"``,
                ``"retry_esgotado_429"``, ``"timeout"``, ``"conexao"``,
                ``"json_invalido"``), ou ``"<Classe>: <mensagem>"`` fora dele. A resposta
                200 sem a contagem em ``hits.total`` (uma lista, por exemplo) sai
                ``"json_invalido"``. A resposta 200 parcial do Elasticsearch
                (``_shards.failed > 0`` ou ``timed_out: true``), cuja contagem pode
                sair menor, sai ``"RuntimeError: Resposta parcial do
                Elasticsearch: ..."``, com os motivos dos shards.

        Raises:
            requests.HTTPError: No 401 (chave inválida), que interrompe a
                contagem; as falhas anteriores vão numa nota do erro.
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

        See Also:
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
        for indice, (alias, cnjs) in enumerate(target_aliases):
            # Pausa entre tribunais, também depois de um que falhou; nenhuma
            # depois do último, como entre as páginas de ``listar_processos``.
            if indice:
                time.sleep(self.sleep_time)
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
                _relancar_se_token_invalido(exc, rows)
                rows.append(_linha_de_falha(tribunal_sigla, alias, exc))
                continue
            # Antes do formato: resposta parcial é a causa, mesmo se ``hits.total`` vier faltando.
            parcial = _descrever_resposta_parcial(api_response, "a contagem pode estar incompleta")
            if parcial:  # Contagem menor que a real, como a página parcial de ``listar_processos``
                rows.append(_linha_de_falha(tribunal_sigla, alias, RuntimeError(parcial)))
                continue
            try:
                count, relation = contagem_da_resposta(api_response)
            except TypeError as exc:  # JSON na forma errada: ``json_invalido``, como no JusBR e na PDPJ
                rows.append(_linha_de_falha(tribunal_sigla, alias, exc) | {"error": "json_invalido"})
                continue
            rows.append({
                "tribunal": tribunal_sigla,
                "alias": alias,
                "count": count,
                "relation": relation,
                "error": None,
            })
        colunas = ["tribunal", "alias", "count", "relation", "error"]  # Int64: com None de falha, viraria float
        return pd.DataFrame(rows, columns=colunas).astype({"count": "Int64"})

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
        paginas: int | list | range | None = None,
        **kwargs,
    ) -> pd.DataFrame:
        """Lista processos do DataJud via API publica do CNJ.

        Filtros sao validados pelo schema :class:`InputListarProcessosDataJud`
        (``extra="forbid"``); kwargs desconhecidos viram ``TypeError`` com a
        mensagem ``DatajudScraper.listar_processos() got unexpected keyword
        argument(s): '<nome>'`` em vez de serem silenciosamente ignorados.

        Args:
            paginas: Páginas 1-based. Aceita as 4 formas do contrato
                único (refs #118): ``int`` (``3`` -> ``range(1, 4)``),
                ``list`` (``[3, 5]`` devolve só as páginas 3 e 5), ``range``
                (respeita ``start``/``stop``/``step``) e ``None`` (default,
                todas). Como o cursor ``search_after`` só avança, a coleta
                percorre as páginas de 1 até a maior pedida e descarta as que
                não foram pedidas; o resultado vem na ordem do cursor.
            **kwargs: Filtros aceitos pelo schema
                :class:`InputListarProcessosDataJud`. Listados abaixo (todos
                opcionais; ``None`` = sem filtro):

                * ``numero_processo`` (str | list[str] | None): CNJ formatado ou
                  lista de CNJs. Quando informado sem ``tribunal``, o alias-
                  indice e inferido pelos digitos ``id_justica`` (pos. 14) +
                  ``id_tribunal`` (pos. 15-16). CNJs invalidos ou nao
                  mapeados emitem ``UserWarning`` e sao ignorados.
                * ``tribunal`` (str | None): Sigla do tribunal (ex.: ``"TJSP"``,
                  ``"TRT2"``, ``"TRE-SP"``). Mutuamente exclusivo com
                  inferencia via ``numero_processo``.
                * ``ano_ajuizamento`` (int | None): Filtra por ano de ajuizamento.
                  Backend recebe ``range`` dual em ``dataAjuizamento`` (ISO
                  ``YYYY-01-01`` + compacto ``YYYYMMDDhhmmss``). Mutuamente
                  exclusivo com ``data_ajuizamento_inicio``/``_fim``.
                * ``data_ajuizamento_inicio`` / ``data_ajuizamento_fim`` (str | None):
                  Range de data de ajuizamento, formato ``YYYY-MM-DD`` (ISO
                  8601). Backend recebe ``bool.should`` com 2 ``range`` em
                  ``dataAjuizamento`` (ISO + compacto), mesmo padrao dual-
                  format do ``ano_ajuizamento`` (refs #51). Pode informar
                  apenas inicio, apenas fim, ou ambos. **Nao** ha alias
                  ``data_inicio``/``data_fim`` aqui (a convencao generica
                  do projeto mapeia esses para ``data_julgamento_*``, e o
                  DataJud filtra por ajuizamento, nao julgamento).
                * ``classe`` (str | None): Codigo da classe processual CNJ.
                * ``assunto`` (list[str | int] | None): Lista de codigos de
                  assuntos CNJ (TPU). Aceita int e str — int e a forma
                  natural (codigos TPU sao inteiros); str e aceita por
                  compatibilidade. O schema normaliza para str antes do
                  payload, ja que o Elasticsearch coage int -> str em
                  campos ``keyword``. Backend: ``terms`` em
                  ``assuntos.codigo``. ``assuntos`` (plural) e aceito como
                  alias deprecado. Refs #232.
                * ``tipos_movimentacao`` (list[str] | None): Nomes amigaveis de
                  categorias de movimentacao (ex.: ``["decisao", "sentenca"]``).
                  Resolvidos via ``TIPOS_MOVIMENTACAO`` para uma lista plana
                  de codigos TPU CNJ. Para nomes nao mapeados, usar
                  ``movimentos_codigo`` direto. Categorias atuais:
                  ``decisao``, ``sentenca``, ``julgamento``, ``tutela``,
                  ``transito_julgado``.
                * ``movimentos_codigo`` (list[int | str] | None): Codigos TPU
                  CNJ diretos. Aceita int e str — int e a forma natural;
                  str e aceita por conveniencia (ex.: vinda de planilha/
                  CSV) e normalizada para int antes do payload.
                  Concatenado com a lista resolvida de
                  ``tipos_movimentacao`` (uniao). Backend: ``terms`` em
                  ``movimentos.codigo``.
                * ``orgao_julgador`` (str | None): Nome do orgao julgador (ex.:
                  ``"Vara Civel de Brasilia"``). Backend: ``match`` em
                  ``orgaoJulgador.nome``.
                * ``query`` (dict[str, Any] | None): **Override total** da query Elasticsearch.
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
                * ``tamanho_pagina`` (int): Hits por requisicao (default
                  5000, range 10-10000 conforme cap da API publica). Em
                  caso de ``HTTP 504``/``Timeout``, o client refaz a
                  chamada com ``size // 4`` automaticamente (1 retry,
                  ``UserWarning``) e passa a buscar cada pagina em pedacos
                  desse tamanho; ``paginas`` continua contando paginas de
                  ``tamanho_pagina``. Ainda assim, valores proximos de
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
                ``.status_code``), ``requests.Timeout``, erro de conexão ou
                ``requests.JSONDecodeError`` (resposta 200 que não é JSON).
                O 401 (chave inválida) interrompe a coleta no alias em que
                ocorre: os aliases seguintes não são consultados, e a mensagem
                os lista.
                Resposta 200 parcial do Elasticsearch (``_shards.failed > 0``
                ou ``timed_out: true``) também levanta, com os motivos dos
                shards na mensagem e os hits válidos da página em
                ``erro.resultado``. Na página 1, ``hits.total`` fora do
                formato que :meth:`contar_processos` exige (objeto com
                ``value`` inteiro e ``relation`` ``"eq"``/``"gte"``) também.

        Returns:
            Um DataFrame com uma linha por processo. ``extra``
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

        See Also:
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
        aliases = self._resolve_aliases(
            tribunal=inp.tribunal,
            numero_processo=inp.numero_processo,
        )
        return self._listar_aliases(aliases, inp, _resolve_movimentos_codigo(inp), inp.paginas_normalizadas)

    def _listar_aliases(
        self,
        aliases: list[AliasSelection],
        inp: InputListarProcessosDataJud,
        movimentos_codigo: list[int] | None,
        paginas: Paginas | None,
    ) -> pd.DataFrame:
        """Coleta cada alias; as falhas saem juntas num ``ColetaParcialError``, e o 401 encerra a coleta."""
        frames = []
        falhas = []
        diagnosticos = []
        token_recusado: Exception | None = None
        for alias, cnjs in aliases:
            try:
                frame = self._listar_processos_por_alias(
                    alias=alias,
                    numero_processo=cnjs,
                    inp=inp,
                    movimentos_codigo=movimentos_codigo,
                    paginas=paginas,
                )
            except ColetaParcialError as exc:
                frame = exc.resultado
                falhas.extend(exc.falhas)
                diagnosticos.append(str(exc))
                token_recusado = next((causa for *_, causa in exc.falhas if e_token_invalido(causa)), None)
            frames.append(frame)
            if token_recusado is not None:  # A chave inválida recusa todos os aliases.
                break
        if nao_consultados := aliases[len(frames):]:
            diagnosticos.append(_aliases_nao_consultados(nao_consultados))

        non_empty = [frame for frame in frames if not frame.empty]
        resultado = pd.concat(non_empty, ignore_index=True) if non_empty else pd.DataFrame()
        if falhas:
            mensagem = "DataJud: coleta parcial. " + "; ".join(diagnosticos)
            raise ColetaParcialError(mensagem, resultado=resultado, falhas=falhas) from token_recusado or falhas[0][2]
        return resultado

    def _listar_processos_por_alias(
        self,
        *,
        alias: str,
        numero_processo: str | list[str] | None,
        inp: InputListarProcessosDataJud,
        movimentos_codigo: list[int] | None,
        paginas: Paginas | None,
    ) -> pd.DataFrame:
        """Percorre o cursor físico e agrega somente as páginas solicitadas."""
        frames: list[pd.DataFrame] = []
        total = None if paginas is None else len(paginas_unicas(paginas))
        pbar = tqdm(
            total=total,
            desc=f"Paginando {alias}",
            unit=" página",
            disable=total == 0,
        )
        ultima_pagina_contada = 0
        try:
            # ``total_info`` e ``recebidos`` vêm do iterador: o total já validado na
            # página 1, que alimenta o diagnóstico mesmo com ``paginas`` que a pula,
            # e os hits das páginas pedidas antes desta, a mesma contagem das
            # mensagens de falha do próprio iterador.
            for current_page, api_response, total_info, recebidos in self._iter_process_pages(
                alias=alias,
                numero_processo=numero_processo,
                inp=inp,
                movimentos_codigo=movimentos_codigo,
                paginas=paginas,
            ):
                if not pagina_pedida(paginas, current_page):
                    continue
                frame = _parse_pagina(
                    api_response,
                    mostrar_movs=inp.mostrar_movs,
                    diagnostico=_mensagem_falha_parcial(
                        alias, current_page, recebidos, total_info,
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
                # Depois do fallback, a página chega em pedaços: a barra avança no primeiro.
                pbar.update(int(current_page != ultima_pagina_contada))
                ultima_pagina_contada = current_page
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
        paginas: Paginas | None,
    ) -> Iterator[tuple[int, dict[str, Any], dict[str, Any] | None, int]]:
        """Percorre o cursor físico até a última página necessária.

        Entrega cada busca com o número da página de ``tamanho_pagina`` a que
        ela pertence, o ``hits.total`` da página 1 já validado e quantos hits
        das páginas pedidas vieram antes desta busca (depois do fallback,
        inclusive os pedaços anteriores da mesma página). Depois do
        fallback de 504/timeout, uma página chega em vários pedaços do
        ``size`` reduzido, cortados na fronteira dela, para que ``paginas``
        continue contando páginas do tamanho pedido (#513).
        """
        current_page = 1
        tamanho_pagina = inp.tamanho_pagina
        # Teto de cada busca: começa em ``tamanho_pagina`` e só cai com o fallback.
        size_maximo = tamanho_pagina
        search_after: list[Any] | None = None
        last_page = None if paginas is None else maior_pagina(paginas)
        # Alimentam o diagnóstico do ColetaParcialError: quanto já veio das páginas pedidas e
        # quanto a consulta encontrou (``hits.total`` da página 1).
        recebidos = 0
        percorridos = 0
        total_info: dict[str, Any] | None = None
        while last_page is None or current_page <= last_page:
            logger.info("Fetching page %d for alias %s...", current_page, alias)
            size_pedido = _size_do_pedaco(size_maximo, tamanho_pagina - percorridos % tamanho_pagina)
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
                tamanho_pagina=size_pedido,
                search_after=search_after,
            )
            try:
                api_response = self._buscar(alias, query_payload)
            except FALHAS_DE_TRANSPORTE as exc:
                mensagem = _mensagem_falha_parcial(alias, current_page, recebidos, total_info)
                _falha_pagina(mensagem + _sufixo_causa(exc), exc)
            hits = _hits_da_pagina(api_response, alias, current_page, recebidos, total_info)
            if total_info is None:  # primeira busca; depois do fallback, a página 1 vem em pedaços
                total_info = _total_primeira_pagina(api_response, alias, current_page)
            effective_size = query_payload["size"]
            size_maximo = _teto_apos_busca(size_maximo, size_pedido, effective_size)
            percorridos += len(hits)
            next_search_after = _next_search_after(
                api_response,
                alias=alias,
                effective_size=effective_size,
            )
            recebidos_antes = recebidos
            if pagina_pedida(paginas, current_page):
                recebidos += len(hits)
            proxima_pagina = percorridos // tamanho_pagina + 1
            contexto = _FimPagina(alias, current_page, recebidos, last_page, proxima_pagina)
            _verificar_pagina_vazia(api_response, effective_size, total_info, percorridos, contexto)
            yield current_page, api_response, total_info, recebidos_antes
            # Depois do ``yield``: o consumidor já guardou os hits válidos da página.
            _verificar_resposta_parcial(api_response, total_info, contexto)
            if next_search_after is None:
                _verificar_fim_pagina(hits, effective_size, total_info, percorridos, contexto)
                return
            search_after = next_search_after
            current_page = proxima_pagina
            if last_page is None or current_page <= last_page:
                time.sleep(self.sleep_time)
