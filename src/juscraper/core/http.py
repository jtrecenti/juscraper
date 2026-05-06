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

Não exportado em ``juscraper.__init__`` — uso interno (ainda em rollout pelas
Fases 1-4 do refactor #194).
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

from juscraper import __version__
from juscraper.core.base import BaseScraper
from juscraper.core.exceptions import RetryExhaustedError

logger = logging.getLogger("juscraper.core.http")

RETRYABLE_STATUSES: frozenset[int] = frozenset({429, 500, 502, 503, 504})


class HTTPScraper(BaseScraper):
    """Base para scrapers que fazem requisições HTTP."""

    def __init__(
        self,
        tribunal_name: str = "",
        *,
        verbose: int = 0,
        download_path: str | None = None,
        sleep_time: float = 1.0,
        **kwargs: Any,
    ):
        super().__init__(tribunal_name or type(self).__name__)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": f"juscraper/{__version__} (https://github.com/jtrecenti/juscraper)",
        })
        self._configure_session(self.session)
        self.set_verbose(verbose)
        self.set_download_path(download_path)
        self.sleep_time = sleep_time
        self.args = kwargs

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
        max_retries: int = 3,
        base_backoff: float = 2.0,
        **kwargs: Any,
    ) -> requests.Response:
        """Executa ``method`` em ``url`` com retry exponencial.

        Args:
            method: Verbo HTTP (``"GET"``, ``"POST"``, ...).
            url: URL alvo.
            session: ``requests.Session`` para sobrepor ``self.session`` nesta
                chamada. Default ``None``.
            max_retries: Número máximo de tentativas (inclusive a primeira).
            base_backoff: Base do backoff exponencial (``base_backoff ** attempt``
                segundos entre tentativas).
            **kwargs: Encaminhados para ``session.request``.

        Returns:
            ``requests.Response`` na primeira resposta com status < 400.

        Raises:
            TypeError: Se ``session`` não for ``None`` nem ``requests.Session``.
            ValueError: Se ``max_retries`` for menor que 1.
            RetryExhaustedError: Quando esgota ``max_retries`` em status retryable.
            requests.HTTPError: Para 4xx não-retryable (via ``raise_for_status``).
        """
        if session is not None and not isinstance(session, requests.Session):
            raise TypeError(
                f"session deve ser requests.Session, recebido {type(session).__name__}"
            )
        if max_retries < 1:
            raise ValueError(f"max_retries deve ser >= 1, recebido {max_retries}")

        sess = session if session is not None else self.session

        for attempt in range(1, max_retries + 1):
            resp = sess.request(method, url, **kwargs)
            if resp.status_code < 400:
                return resp

            if resp.status_code in RETRYABLE_STATUSES:
                if attempt == max_retries:
                    raise RetryExhaustedError(resp.status_code, attempt)
                wait = self._parse_retry_after(resp.headers.get("Retry-After"))
                if wait is None:
                    wait = base_backoff ** attempt
                wait = max(0.0, wait)  # tolera Retry-After negativo de servidores mal-comportados
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
