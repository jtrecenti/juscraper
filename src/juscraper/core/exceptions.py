"""Exceções compartilhadas pela infraestrutura HTTP/parse de juscraper.

`RetryExhaustedError` é levantada por `core.http.HTTPScraper._request_with_retry`
quando todas as tentativas de retry esgotaram em status retryable (429/5xx).

`HTTPSemanticError` é a base abstrata para casos de "HTTP-200 com página de erro"
(captcha expirado, sessão inválida, formulário não submetido). Subclasses concretas
ficam nos parsers que detectam o erro — ver Regra 2 ("Detecção de erro HTTP-200")
em ``CLAUDE.md``.
"""
from __future__ import annotations


class RetryExhaustedError(Exception):
    """Levantada quando ``_request_with_retry`` esgota o número de tentativas."""

    def __init__(self, status_code: int | None, attempts: int):
        self.status_code = status_code
        self.attempts = attempts
        super().__init__(
            f"HTTP request failed after {attempts} attempts (last status: {status_code})"
        )


class HTTPSemanticError(Exception):
    """Base para respostas HTTP-200 semanticamente erradas (página de erro disfarçada)."""


class BotChallengeBlockedError(Exception):
    """Levantada quando um portal bloqueia o request via bot manager (ex.: Akamai).

    O sintoma típico é HTTP 403 com body curto ``Access Denied`` e uma referência
    Akamai (``Reference #...``); o cookie de challenge (``ak_bmsc``) nem chega
    a ser emitido. Isso normalmente significa que o IP do cliente foi
    rate-limited — não adianta retentar com a mesma sessão.

    Mensagem orienta o usuário a aguardar alguns minutos antes de tentar de
    novo, ou trocar de IP (VPN, hotspot). É propagada (em vez de engolida
    pelos try/except por-item) porque um bloqueio nesse nível é session-wide:
    nenhum CNJ do batch vai conseguir passar.
    """

    def __init__(self, tribunal: str, url: str, reference: str | None = None):
        self.tribunal = tribunal
        self.url = url
        self.reference = reference
        msg = (
            f"{tribunal} bloqueou a requisição (HTTP 403 'Access Denied') "
            f"em {url}. Provavelmente foi o bot manager (Akamai) limitando "
            f"o seu IP — aguarde alguns minutos antes de tentar de novo "
            f"ou troque de IP (VPN, hotspot)."
        )
        if reference:
            msg += f" Reference: {reference}."
        super().__init__(msg)
