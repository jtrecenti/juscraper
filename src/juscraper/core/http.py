# pylint: disable=unused-import
# astroid injeta IntEnum/StrEnum/namedtuple via brain_http.py para o stdlib `http`;
# pylint aplica o stub a este modulo por causa do nome (falso positivo).
"""HTTPScraper — base com session compartilhada e retry exponencial.

Camada inserida entre :class:`BaseScraper` e os scrapers concretos. Centraliza:

* Criação de ``requests.Session`` com User-Agent padrão.
* Hook ``_configure_session(session)`` (mesmo nome/contrato de
  ``courts/_esaj/base.py``).
* ``_request_with_retry`` com backoff exponencial ``base_backoff ** attempt``
  para 429/5xx e respeito a ``Retry-After`` numérico.
* Validação ``isinstance(session, requests.Session)`` no override por chamada
  (resolve #185 — ``session`` fica fora do schema pydantic por design).
* :class:`RequestPolicy` — timeout, tentativas, backoff, status retentáveis e
  retry opcional em timeout/erro de conexão, agrupados em perfis nomeados que
  cada scraper declara em ``perfis_http`` e o usuário ajusta com ``politica=``.

Não exportado em ``juscraper.__init__`` — uso interno (ainda em rollout pelas
Fases 1-4 do refactor #194).
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, replace
from typing import Any, ClassVar, TypeAlias

import requests

from juscraper import __version__
from juscraper.core.base import BaseScraper
from juscraper.core.exceptions import InvalidJSONResponseError, RetryExhaustedError

logger = logging.getLogger("juscraper.core.http")

RETRYABLE_STATUSES: frozenset[int] = frozenset({403, 429, 500, 502, 503, 504})
"""Status codes que disparam retry com backoff exponencial.

``403`` foi incluído por causa do TJSP eSAJ (#233): o WAF do eSAJ retorna 403
intermitente em raspagens longas, mesmo sem o cliente bater em rate limit
clássico (que daria 429). Como o 403 é produzido pelo WAF e não por
autenticação/autorização do recurso, retentar com backoff resolve a maioria
dos casos transitórios. 403 ``permanente`` (ex.: credenciais inválidas) ainda
acaba caindo em ``RetryExhaustedError`` após ``max_retries`` tentativas, o que
é o sintoma certo — o WAF não distingue os dois casos pelo status code.

A decisão aplica-se globalmente: todos os scrapers que delegam ao
``_request_with_retry`` herdam o comportamento. Consumidores que distinguem
403-de-auth de 403-de-WAF (ex.: PDPJ, onde 403 nega o recurso) declaram
perfis de :class:`RequestPolicy` com ``retryable_statuses`` sem o 403, como
``PdpjScraper.perfis_http``."""


@dataclass(frozen=True)
class RequestPolicy:
    """Política de requisição usada por ``HTTPScraper._request_with_retry``.

    Os defaults reproduzem o comportamento anterior à política: sem ``timeout``
    injetado, 3 tentativas, backoff ``2.0 ** tentativa``, :data:`RETRYABLE_STATUSES`
    e nenhuma nova tentativa em timeout ou erro de conexão.

    Os nomes dos campos são os mesmos dos kwargs aceitos por chamada
    (``timeout=``, ``max_retries=``, ``base_backoff=``), e o kwarg explícito
    vence o campo da política.

    Attributes:
        timeout: Repassado a ``session.request`` quando a chamada não traz
            ``timeout=``. ``None`` não injeta nada.
        max_retries: Número máximo de tentativas, inclusive a primeira.
        base_backoff: Base do backoff exponencial entre tentativas.
        retryable_statuses: Status HTTP que disparam nova tentativa.
        retry_on_timeout: Retenta ``requests.Timeout`` de leitura.
        retry_on_connection_error: Retenta ``requests.ConnectionError``. Inclui
            ``requests.ConnectTimeout``, que herda das duas classes e é tratado
            como falha de conexão: estourar o prazo de conexão indica host
            inalcançável, não resposta lenta.
    """

    timeout: float | tuple[float, float] | None = None
    max_retries: int = 3
    base_backoff: float = 2.0
    retryable_statuses: frozenset[int] = RETRYABLE_STATUSES
    retry_on_timeout: bool = False
    retry_on_connection_error: bool = False

    def __post_init__(self) -> None:
        """Valida ``max_retries`` e congela ``retryable_statuses`` e ``timeout``."""
        if self.max_retries < 1:
            raise ValueError(f"max_retries deve ser >= 1, recebido {self.max_retries}")
        # ``politica=`` vinda de JSON traz lista; ``requests`` só aceita tupla (connect, read).
        timeout: Any = self.timeout  # a anotação não cobre a lista que chega em runtime
        if isinstance(timeout, list):
            object.__setattr__(self, "timeout", tuple(timeout))
        # Aceita set/list vindos de ``politica=`` sem deixar a política mutável.
        object.__setattr__(self, "retryable_statuses", frozenset(self.retryable_statuses))

    def retries_network_error(self, exc: requests.RequestException) -> bool:
        """Diz se ``exc`` (timeout ou erro de conexão) merece nova tentativa.

        ``ConnectionError`` é testado antes de ``Timeout`` porque
        ``ConnectTimeout`` herda dos dois e deve seguir a opção de conexão, na
        mesma regra de ``juscraper.core.failures.motivo_falha``.
        """
        if isinstance(exc, requests.ConnectionError):
            return self.retry_on_connection_error
        return self.retry_on_timeout


DEFAULT_POLICY = RequestPolicy()
"""Política das chamadas sem ``perfil=``; idêntica ao comportamento anterior."""

_POLICY_FIELDS: frozenset[str] = frozenset(f.name for f in fields(RequestPolicy))

RequestFn: TypeAlias = Callable[..., requests.Response]
"""Tipo do callable bound do ``HTTPScraper._request_with_retry``.

Repassado a ``courts/<xx>/download.py::cjsg_download_manager`` (Fase 1 do
refactor #194) para centralizar retry + ``raise_for_status`` sem expor a
``session`` do client. Contrato esperado em runtime:

* ``method`` (1o positional) — verbo HTTP (``"GET"``, ``"POST"``, ...).
* ``url`` (2o positional) — URL alvo.
* kwargs livres — encaminhados a ``requests.Session.request`` (``json=``,
  ``data=``, ``headers=``, ``timeout=``, ...). ``max_retries``,
  ``base_backoff`` e ``expect_json`` tambem sao aceitos para sobrepor o default.
* ``perfil=`` — nome de um perfil de :class:`RequestPolicy` declarado pelo
  scraper em ``perfis_http``. Consumido antes de ``session.request``.

A response retornada e garantida com ``status_code < 400`` (4xx ja foi
via ``raise_for_status``; 5xx/429 ja esgotou ``max_retries`` ->
``RetryExhaustedError``). O caller pode chamar ``.json()`` / ler ``.text``
sem se preocupar com retry de transitorios.

Com ``expect_json=True``, a response retornada tem ainda corpo JSON valido
garantido: 200 com corpo vazio/nao-JSON e tratado como transitorio (retry com
backoff) e, persistindo, levanta ``InvalidJSONResponseError`` em vez do
``json.JSONDecodeError`` opaco. Ver #275.

Implementado como ``Callable[..., Response]`` (e nao ``Protocol``) por
compatibilidade com mypy: o ``__call__`` do bound method tem keyword
args nomeados (``session``/``max_retries``/``base_backoff``) que nao
casam estritamente com ``**kwargs: Any`` em ``Protocol`` matching."""


class HTTPScraper(BaseScraper):
    """Base para scrapers que fazem requisições HTTP.

    Subclasses declaram perfis de requisição em ``perfis_http`` (por exemplo,
    ``{"listagem": RequestPolicy(...), "documento": RequestPolicy(...)}``) e
    escolhem o perfil por chamada com ``_request_with_retry(..., perfil=...)``.
    O usuário ajusta campos de um perfil no construtor com ``politica=``.
    """

    perfis_http: ClassVar[Mapping[str, RequestPolicy]] = {}

    def __init__(
        self,
        tribunal_name: str = "",
        *,
        verbose: int = 0,
        download_path: str | None = None,
        sleep_time: float = 1.0,
        politica: Mapping[str, Mapping[str, Any]] | None = None,
        **kwargs: Any,
    ):
        super().__init__(tribunal_name or type(self).__name__)
        self._perfis_http = self._merge_politica(politica)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": f"juscraper/{__version__} (https://github.com/jtrecenti/juscraper)",
        })
        self._configure_session(self.session)
        self.set_verbose(verbose)
        self.set_download_path(download_path)
        self.sleep_time = sleep_time
        self.args = kwargs

    @classmethod
    def _merge_politica(
        cls, politica: Mapping[str, Mapping[str, Any]] | None
    ) -> dict[str, RequestPolicy]:
        """Aplica os ajustes de ``politica=`` sobre os perfis declarados.

        A mescla é por campo: um perfil ajustado mantém tudo o que o scraper
        declarou e não foi passado. Substituir o perfil inteiro devolveria, em
        silêncio, os defaults do core (403 retentável, sem retry em timeout)
        ao scraper que os tinha mudado.

        Raises:
            ValueError: Se o scraper não declara perfis, se um perfil ou campo
                é desconhecido. Sem perfis declarados, o scraper ainda passa
                ``timeout=`` literal na chamada, que venceria o ajuste; o erro
                evita que ``politica=`` seja ignorada sem aviso.
        """
        perfis = dict(cls.perfis_http)
        if politica is None:
            return perfis
        if not perfis:
            raise ValueError(f"{cls.__name__} não declara perfis HTTP; politica= não se aplica.")
        for nome, ajuste in politica.items():
            if nome not in perfis:
                raise ValueError(
                    f"Perfil HTTP desconhecido em {cls.__name__}: {nome!r}. Perfis declarados: {sorted(perfis)}."
                )
            if not isinstance(ajuste, Mapping):
                raise ValueError(
                    f"Ajuste do perfil {nome!r} deve ser um dict de campos, recebido {type(ajuste).__name__}."
                )
            desconhecidos = set(ajuste) - _POLICY_FIELDS
            if desconhecidos:
                raise ValueError(
                    f"Campo(s) de política desconhecido(s) no perfil {nome!r}: {sorted(desconhecidos)}. "
                    f"Campos aceitos: {sorted(_POLICY_FIELDS)}."
                )
            perfis[nome] = replace(perfis[nome], **ajuste)
        return perfis

    def _resolve_policy(
        self, perfil: str | None, max_retries: int | None, base_backoff: float | None
    ) -> RequestPolicy:
        """Política efetiva da chamada: perfil (ou default) com os kwargs explícitos por cima."""
        if perfil is None:
            policy = DEFAULT_POLICY
        elif perfil in self._perfis_http:
            policy = self._perfis_http[perfil]
        else:
            raise ValueError(
                f"Perfil HTTP desconhecido em {type(self).__name__}: {perfil!r}. "
                f"Perfis declarados: {sorted(self._perfis_http)}."
            )
        if max_retries is not None:
            policy = replace(policy, max_retries=max_retries)
        if base_backoff is not None:
            policy = replace(policy, base_backoff=base_backoff)
        return policy

    @staticmethod
    def _send_once(
        sess: requests.Session,
        method: str,
        url: str,
        policy: RequestPolicy,
        attempt: int,
        kwargs: dict[str, Any],
    ) -> requests.Response | None:
        """Faz uma tentativa; devolve ``None`` quando um erro de rede será retentado.

        O ``timeout`` da política entra só quando a chamada não traz
        ``timeout=``: o argumento explícito vence.

        Timeout e erro de conexão retentáveis gastam uma tentativa do mesmo
        ``max_retries`` dos status. Na última tentativa a exceção original é
        relançada, e não trocada por ``RetryExhaustedError``: o motivo de falha
        continua sendo ``timeout`` ou ``conexao``, que não têm status HTTP.
        """
        if policy.timeout is not None and "timeout" not in kwargs:
            kwargs = {**kwargs, "timeout": policy.timeout}
        try:
            return sess.request(method, url, **kwargs)
        except (requests.ConnectionError, requests.Timeout) as exc:
            if not policy.retries_network_error(exc) or attempt == policy.max_retries:
                raise
            wait = max(0.0, policy.base_backoff ** attempt)
            logger.warning(
                "%s em %s %s (tentativa %d/%d). Aguardando %.2fs.",
                type(exc).__name__, method, url, attempt, policy.max_retries, wait,
            )
            time.sleep(wait)
            return None

    def _configure_session(self, session: requests.Session) -> None:
        """Hook para subclasses montarem adapters customizados (TLS, cookies, etc.).

        Default: no-op. Mesma assinatura/semântica de ``EsajSearchScraper._configure_session``
        em ``courts/_esaj/base.py`` — quando a Fase 2 (#203) trocar a herança,
        o override existente do TJCE continua funcionando sem mudança.
        """

    def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        session: requests.Session | None = None,
        perfil: str | None = None,
        max_retries: int | None = None,
        base_backoff: float | None = None,
        expect_json: bool = False,
        on_response: Callable[[requests.Response], None] | None = None,
        **kwargs: Any,
    ) -> requests.Response:
        """Executa ``method`` em ``url`` com retry exponencial.

        Args:
            method: Verbo HTTP (``"GET"``, ``"POST"``, ...).
            url: URL alvo.
            session: ``requests.Session`` para sobrepor ``self.session`` nesta
                chamada. Default ``None``.
            perfil: Nome de um perfil declarado em ``perfis_http``. ``None``
                usa :data:`DEFAULT_POLICY`. O perfil fornece ``timeout`` (só
                quando a chamada não traz ``timeout=``), tentativas, backoff,
                status retentáveis e retry em timeout/erro de conexão.
            max_retries: Número máximo de tentativas (inclusive a primeira).
                ``None`` usa o valor da política; valor explícito vence.
            base_backoff: Base do backoff exponencial (``base_backoff ** attempt``
                segundos entre tentativas). ``None`` usa o valor da política.
            expect_json: Se ``True``, valida que o corpo de uma resposta com
                status < 400 é JSON. Corpo vazio/não-JSON é tratado como
                transitório (retry com backoff); persistindo, levanta
                ``InvalidJSONResponseError``. Default ``False`` — o caller chama
                ``.json()`` por conta própria e um corpo inválido propaga
                ``json.JSONDecodeError`` na primeira ocorrência (#275).
            on_response: Callback opcional invocado em cada resposta crua, antes
                de qualquer decisão de retry/``raise_for_status``. Use para
                inspeção que precisa curto-circuitar o retry — se o callback
                levantar, a exceção propaga imediatamente, sem novas tentativas.
                Caso de uso: detectar o 403 de bot-challenge (Akamai) e levantar
                ``BotChallengeBlockedError`` em vez de retentar um bloqueio
                session-wide (403 está em ``RETRYABLE_STATUSES``). Default
                ``None`` — sem inspeção, comportamento idêntico ao anterior.
            **kwargs: Encaminhados para ``session.request``.

        Returns:
            ``requests.Response`` na primeira resposta com status < 400 (e, se
            ``expect_json=True``, com corpo JSON válido).

        Raises:
            TypeError: Se ``session`` não for ``None`` nem ``requests.Session``.
            ValueError: Se ``max_retries`` for menor que 1 ou ``perfil`` não
                estiver declarado.
            RetryExhaustedError: Quando esgota ``max_retries`` em status retryable.
            requests.Timeout, requests.ConnectionError: Na primeira ocorrência,
                ou na última tentativa quando a política retenta esse erro.
            InvalidJSONResponseError: Quando ``expect_json=True`` e o corpo permanece
                vazio/não-JSON após ``max_retries``.
            requests.HTTPError: Para 4xx não-retryable (via ``raise_for_status``).
        """
        if session is not None and not isinstance(session, requests.Session):
            raise TypeError(
                f"session deve ser requests.Session, recebido {type(session).__name__}"
            )
        policy = self._resolve_policy(perfil, max_retries, base_backoff)
        max_retries = policy.max_retries
        base_backoff = policy.base_backoff

        sess = session if session is not None else self.session

        for attempt in range(1, max_retries + 1):
            resp = self._send_once(sess, method, url, policy, attempt, kwargs)
            if resp is None:
                continue
            if on_response is not None:
                on_response(resp)
            if resp.status_code < 400:
                if expect_json and not self._response_is_json(resp):
                    if attempt == max_retries:
                        raise InvalidJSONResponseError(
                            url,
                            resp.status_code,
                            attempt,
                            resp.headers.get("Content-Type"),
                            resp.text[:200],
                        )
                    backoff_wait = max(0.0, base_backoff ** attempt)
                    logger.warning(
                        "Corpo nao-JSON em HTTP %s %s %s (tentativa %d/%d). Aguardando %.2fs.",
                        resp.status_code, method, url, attempt, max_retries, backoff_wait,
                    )
                    time.sleep(backoff_wait)
                    continue
                return resp

            if resp.status_code in policy.retryable_statuses:
                if attempt == max_retries:
                    raise RetryExhaustedError(resp.status_code, attempt)
                wait = self._status_wait(resp, attempt, base_backoff)
                logger.warning(
                    "HTTP %s em %s %s (tentativa %d/%d). Aguardando %.2fs.",
                    resp.status_code, method, url, attempt, max_retries, wait,
                )
                time.sleep(wait)
                continue

            resp.raise_for_status()

        # Inalcançável: o loop sai sempre via return, RetryExhaustedError ou raise_for_status.
        raise RuntimeError("loop de retry terminou sem decisão")  # pragma: no cover

    @staticmethod
    def _response_is_json(resp: requests.Response) -> bool:
        """Retorna ``True`` se o corpo da resposta for JSON válido.

        Usado por ``_request_with_retry(expect_json=True)`` para distinguir um
        200 legítimo de um 200 com corpo vazio/não-JSON (transitório do backend).

        O caller chama ``resp.json()`` de novo após esta validação; isso é
        intencional e barato: ``resp.content`` fica em cache no objeto
        ``Response``, então não há requisição extra, apenas um reparse do corpo
        já em memória.
        """
        try:
            resp.json()
        except ValueError:  # json.JSONDecodeError é subclasse de ValueError
            return False
        return True

    @classmethod
    def _status_wait(cls, resp: requests.Response, attempt: int, base_backoff: float) -> float:
        """Espera antes de retentar um status: ``Retry-After`` numérico ou backoff exponencial.

        O clamp em 0 tolera ``Retry-After`` negativo de servidores mal-comportados.
        """
        wait = cls._parse_retry_after(resp.headers.get("Retry-After"))
        if wait is None:
            wait = base_backoff ** attempt
        return max(0.0, wait)

    @staticmethod
    def _parse_retry_after(header: str | None) -> float | None:
        """Parseia ``Retry-After`` apenas como segundos numéricos.

        Decisão da issue #201: backends brasileiros não usam HTTP-date; suporte
        a esse formato fica fora do escopo. Header inválido/ausente → ``None``
        (caller cai no backoff exponencial).
        """
        if header is None:
            return None
        try:
            return float(header)
        except (TypeError, ValueError):
            return None
