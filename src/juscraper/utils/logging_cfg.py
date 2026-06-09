"""Logging configuration for juscraper."""
from collections.abc import Mapping

_SENSITIVE_HEADERS = frozenset({
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
})
_REDACTED = "[REDACTED]"


def _is_sensitive(key: str) -> bool:
    """``True`` se ``key`` for um header de credencial (case-insensitive).

    Cobre o conjunto fixo ``_SENSITIVE_HEADERS`` e qualquer chave de API:
    ``api-key`` e o sufixo ``-api-key`` (``x-api-key``, ``vendor-api-key``).
    """
    lowered = key.lower()
    return (
        lowered in _SENSITIVE_HEADERS
        or lowered == "api-key"
        or lowered.endswith("-api-key")
    )


def redact_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Devolve copia de ``headers`` com valores de credenciais redigidos.

    Chaves sensiveis (``Authorization``, ``Cookie``, ``*-api-key``, etc.) tem o
    valor trocado por ``"[REDACTED]"``. A comparacao da chave e case-insensitive
    e o dict original nao e mutado. Use antes de passar headers para
    ``logger.debug``/``logger.info``, evitando emitir tokens em log.
    """
    return {
        k: (_REDACTED if _is_sensitive(k) else v)
        for k, v in headers.items()
    }
