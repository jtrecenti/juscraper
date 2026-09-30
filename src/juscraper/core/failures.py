"""Motivo de falha por linha, em vocabulário fechado.

Scrapers que devolvem uma linha por item mesmo quando a requisição do item
falha (conteúdo ``None``) registram o motivo em :data:`COLUNA_MOTIVO_FALHA`,
preenchida por :func:`motivo_falha` a partir da exceção capturada. Linha sem
falha leva ``None``.

O vocabulário separa ``timeout`` (leitura lenta: o ``timeout`` do perfil pode
estar curto) de ``conexao`` (host inalcançável) e de ``retry_esgotado_<status>``
(o servidor respondeu, mas com status retentável até o fim das tentativas).
"""
from __future__ import annotations

import requests

from juscraper.core.exceptions import InvalidJSONResponseError, RetryExhaustedError

COLUNA_MOTIVO_FALHA = "motivo_falha"
"""Nome da coluna de motivo de falha nos DataFrames com uma linha por item."""

MOTIVOS_FALHA: tuple[str, ...] = (
    "http_<status>",
    "retry_esgotado_<status>",
    "timeout",
    "conexao",
    "json_invalido",
)
"""Valores possíveis de :data:`COLUNA_MOTIVO_FALHA`; ``<status>`` é o código HTTP."""


def motivo_falha(exc: BaseException) -> str:
    """Traduz a exceção de uma requisição no motivo de falha da linha.

    A ordem dos testes importa: ``requests.ConnectTimeout`` herda de
    ``ConnectionError`` e de ``Timeout``, e sai ``conexao`` porque o teste de
    conexão vem antes.

    Args:
        exc: Exceção levantada por ``HTTPScraper._request_with_retry`` ou pela
            leitura do corpo.

    Returns:
        Um valor de :data:`MOTIVOS_FALHA`, com o status preenchido.

    Raises:
        TypeError: Para exceção fora do vocabulário (``TooManyRedirects``,
            ``InvalidURL``, erro de parse, ...) ou sem status HTTP onde ele é
            exigido. O chamador decide se a propaga; o helper não inventa motivo.
    """
    if isinstance(exc, RetryExhaustedError):
        if exc.status_code is None:
            raise TypeError("RetryExhaustedError sem status não tem motivo de falha.") from exc
        return f"retry_esgotado_{exc.status_code}"
    if isinstance(exc, InvalidJSONResponseError):
        return "json_invalido"
    if isinstance(exc, requests.HTTPError):
        if exc.response is None:
            raise TypeError("HTTPError sem resposta não tem motivo de falha.") from exc
        return f"http_{exc.response.status_code}"
    if isinstance(exc, requests.ConnectionError):
        return "conexao"
    if isinstance(exc, requests.Timeout):
        return "timeout"
    raise TypeError(f"Exceção sem motivo de falha no vocabulário: {type(exc).__name__}.") from exc
