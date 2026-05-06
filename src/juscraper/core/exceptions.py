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
