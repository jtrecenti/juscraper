"""Logging configuration for juscraper."""
from collections.abc import Mapping

_SENSITIVE_HEADERS = frozenset({
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "api-key",
})
_REDACTED = "[REDACTED]"


def redact_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Devolve copia de ``headers`` com valores de credenciais redigidos.

    Chaves sensiveis (``Authorization``, ``Cookie``, etc.) tem o valor trocado
    por ``"[REDACTED]"``. A comparacao da chave e case-insensitive e o dict
    original nao e mutado. Use antes de passar headers para
    ``logger.debug``/``logger.info``, evitando emitir tokens em log.
    """
    return {
        k: (_REDACTED if k.lower() in _SENSITIVE_HEADERS else v)
        for k, v in headers.items()
    }
