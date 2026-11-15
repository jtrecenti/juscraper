"""Motivo de falha por linha, em vocabulário fechado.

Scrapers que devolvem uma linha por item mesmo quando a requisição do item
falha (conteúdo ``None``) registram o motivo em :data:`COLUNA_MOTIVO_FALHA`,
preenchida por :func:`motivo_falha` a partir da exceção capturada. Linha sem
falha leva ``None``.

O vocabulário separa ``timeout`` (leitura lenta: o ``timeout`` do perfil pode
estar curto) de ``conexao`` (host inalcançável) e de ``retry_esgotado_<status>``
(o servidor respondeu, mas com status retentável até o fim das tentativas).
``json_invalido`` cobre o corpo que não é o JSON esperado: corpo que não é
JSON (``InvalidJSONResponseError`` e o ``requests.JSONDecodeError`` de
``Response.json()``) e JSON na forma errada (lista no lugar de objeto,
contagem sem inteiro).
``nao_encontrado`` é o processo que a fonte declara ausente por um sinal medido
dela; cada scraper documenta que sinal é esse.
``bloqueio_anti_bot`` é o desafio ou bloqueio de um bot manager (Akamai,
CloudFront, AWS WAF) que derrubou a requisição da linha.
"""
from __future__ import annotations

import requests

from juscraper.core.avisos import avisar
from juscraper.core.exceptions import (
    BloqueioAntiBotWarning,
    BotChallengeBlockedError,
    InvalidJSONResponseError,
    RetryExhaustedError,
)

COLUNA_MOTIVO_FALHA = "motivo_falha"
"""Nome da coluna de motivo de falha nos DataFrames com uma linha por item."""

MOTIVO_NAO_ENCONTRADO = "nao_encontrado"
"""Motivo do processo que a fonte declara ausente.

É motivo, e não resposta com motivo ``None``, porque nem todo método tem onde
dizer "não encontrado": uma lista de documentos vazia se confundiria com
processo sem peças. Entra no aviso agregado como os demais motivos.
"""

MOTIVO_SEM_ACORDAO = "sem_acordao"
"""Processo encontrado, mas sem documento de acórdão acessível na data pedida.

Usado pelo download do inteiro teor pela movimentação do eSAJ.
"""

MOTIVO_NAO_PDF = "nao_pdf"
"""O servidor respondeu ao pedido de PDF com outra coisa; nada foi gravado."""

MOTIVO_RESPOSTA_INESPERADA = "resposta_inesperada"
"""Página HTML fora do formato conhecido, no lugar da que o fluxo espera.

Também é o motivo de erro do item sem motivo próprio no vocabulário, por
:func:`motivo_falha_ou_inesperada`, para que a linha siga no lote em vez de
derrubá-lo.
"""

MOTIVO_ENTRADA_INVALIDA = "entrada_invalida"
"""A linha de entrada não traz um valor utilizável (número CNJ, data); nada foi pedido à fonte."""

MOTIVO_BLOQUEIO_ANTI_BOT = "bloqueio_anti_bot"
"""Um bot manager desafiou ou bloqueou a requisição (:class:`BotChallengeBlockedError`).

Vira linha, e não erro, para que um desafio no meio do lote não descarte as
linhas já processadas (#471). O bloqueio costuma valer para a sessão inteira,
então as linhas seguintes tendem a sair com este motivo também: aguardar
alguns minutos ou trocar de IP antes de pedir de novo só as que falharam.
"""

MOTIVOS_FALHA: tuple[str, ...] = (
    "http_<status>",
    "retry_esgotado_<status>",
    "timeout",
    "conexao",
    "json_invalido",
    MOTIVO_NAO_ENCONTRADO,
    MOTIVO_SEM_ACORDAO,
    MOTIVO_NAO_PDF,
    MOTIVO_RESPOSTA_INESPERADA,
    MOTIVO_ENTRADA_INVALIDA,
    MOTIVO_BLOQUEIO_ANTI_BOT,
)
"""Valores possíveis de :data:`COLUNA_MOTIVO_FALHA`; ``<status>`` é o código HTTP."""

EXCECOES_DE_FALHA_POR_LINHA: tuple[type[BaseException], ...] = (
    RetryExhaustedError,
    InvalidJSONResponseError,
    requests.HTTPError,
    requests.ConnectionError,
    requests.Timeout,
    BotChallengeBlockedError,
)
"""Exceções que o scraper captura e converte em linha de falha.

Todas têm motivo em :func:`motivo_falha`. Qualquer outra (``TooManyRedirects``,
``InvalidURL``, erro de programação) propaga, porque não há motivo no
vocabulário para ela. ``requests.JSONDecodeError`` tem motivo
(``json_invalido``) e mesmo assim fica de fora, para não mudar o que os
scrapers que usam esta tupla capturam. O 401 é ``HTTPError`` mas propaga antes
de virar linha: ver :func:`e_token_invalido`. ``BotChallengeBlockedError``
vira linha: ver :data:`MOTIVO_BLOQUEIO_ANTI_BOT`.
"""

FALHAS_DE_TRANSPORTE: tuple[type[Exception], ...] = (requests.RequestException, RetryExhaustedError)
"""Toda falha de transporte de ``HTTPScraper._request_with_retry``, com ou sem motivo no vocabulário.

Mais larga que :data:`EXCECOES_DE_FALHA_POR_LINHA` no transporte: inclui ``TooManyRedirects``,
``InvalidURL``, ``requests.JSONDecodeError`` e os demais ``RequestException``, mas
não ``BotChallengeBlockedError``, que não é falha de transporte. Serve a
quem converte a falha de um item em resultado parcial mesmo quando
:func:`motivo_falha` não tem motivo para ela. ``RetryExhaustedError`` entra à
parte porque não herda de ``RequestException``.
"""

STATUS_TOKEN_INVALIDO = 401
"""Status que interrompe o lote em vez de virar linha de falha.

401 indica token ausente, expirado ou inválido. O erro vale para todas as
requisições seguintes, então engoli-lo produziria um DataFrame inteiro de
conteúdo ``None`` sem que o usuário percebesse que precisa renovar o token.
O 403 fica de fora de propósito: com token válido, a API da PDPJ pode negar um
documento só (um sigiloso, por exemplo), e propagar descartaria o lote inteiro.
"""

STATUS_CONSULTA_FALHA = "Falha na consulta"
"""Valor de ``status_consulta`` na linha de ``cpopg`` cuja requisição falhou.

O mesmo nos scrapers da PDPJ, para que um filtro por falha funcione igual nos
dois. A linha traz o motivo em :data:`COLUNA_MOTIVO_FALHA`.
"""

EXEMPLOS_NO_AVISO = 3
"""Quantas falhas o aviso agregado e a nota do 401 citam; as demais entram só na contagem."""


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
    if isinstance(exc, (InvalidJSONResponseError, requests.JSONDecodeError)):
        return "json_invalido"
    if isinstance(exc, requests.HTTPError):
        if exc.response is None:
            raise TypeError("HTTPError sem resposta não tem motivo de falha.") from exc
        return f"http_{exc.response.status_code}"
    if isinstance(exc, requests.ConnectionError):
        return "conexao"
    if isinstance(exc, requests.Timeout):
        return "timeout"
    if isinstance(exc, BotChallengeBlockedError):
        return MOTIVO_BLOQUEIO_ANTI_BOT
    raise TypeError(f"Exceção sem motivo de falha no vocabulário: {type(exc).__name__}.") from exc


def motivo_falha_ou_inesperada(exc: BaseException) -> str:
    """:func:`motivo_falha` da exceção, ou :data:`MOTIVO_RESPOSTA_INESPERADA` fora do vocabulário.

    Só as :data:`EXCECOES_DE_FALHA_POR_LINHA` têm motivo próprio. Serve a
    quem converte qualquer erro de um item em linha de falha, inclusive o que
    não tem motivo no vocabulário.
    """
    if isinstance(exc, EXCECOES_DE_FALHA_POR_LINHA):
        return motivo_falha(exc)
    return MOTIVO_RESPOSTA_INESPERADA


def e_token_invalido(exc: BaseException) -> bool:
    """Diz se ``exc`` é o ``HTTPError`` de :data:`STATUS_TOKEN_INVALIDO`."""
    return (
        isinstance(exc, requests.HTTPError)
        and exc.response is not None
        and exc.response.status_code == STATUS_TOKEN_INVALIDO
    )


def resumir_falhas(falhas: list[str], descricao: str) -> str:
    """Contagem e alguns exemplos das falhas, para o aviso e para a nota do 401.

    Args:
        falhas: Uma entrada por requisição que falhou, já com o item e o motivo.
        descricao: O que falhou, no plural, como ``"download(s) de documento"``.
    """
    exemplos = falhas[:EXEMPLOS_NO_AVISO]
    if len(falhas) > len(exemplos):
        exemplos = [*exemplos, f"e mais {len(falhas) - len(exemplos)}"]
    return f"{len(falhas)} {descricao} falharam. Falhas: {'; '.join(exemplos)}."


def avisar_falhas(
    falhas: list[str],
    metodo: str,
    descricao: str,
    consequencia: str = "As linhas correspondentes saem com o conteúdo None.",
) -> None:
    """Emite um único ``UserWarning`` ao fim de uma coleta concluída.

    O aviso aponta para o código de quem chamou o método público, por
    :func:`juscraper.core.avisos.avisar`. Se alguma falha é
    ``bloqueio_anti_bot``, sai como :class:`BloqueioAntiBotWarning`, subclasse
    de ``UserWarning``.

    Args:
        falhas: Ver :func:`resumir_falhas`; cada entrada traz o motivo.
            Lista vazia não emite aviso.
        metodo: Nome qualificado do método público, que abre a mensagem.
        descricao: Ver :func:`resumir_falhas`.
        consequencia: Frase que fecha o aviso, dizendo onde a falha aparece no
            resultado.
    """
    if not falhas:
        return
    bloqueio = any(MOTIVO_BLOQUEIO_ANTI_BOT in falha for falha in falhas)
    avisar(
        f"{metodo}: {resumir_falhas(falhas, descricao)} {consequencia}",
        BloqueioAntiBotWarning if bloqueio else UserWarning,
    )


def anotar_falhas_anteriores(erro: BaseException, falhas: list[str], descricao: str) -> None:
    """Anexa ao erro que interrompeu o lote as falhas que vieram antes dele.

    Usado no 401: um ``warnings.warn`` durante a propagação, com avisos
    promovidos a erro (``-W error``), trocaria o 401 por um ``UserWarning`` e
    esconderia a causa real. Por isso as falhas anteriores vão numa nota do
    próprio erro (``__notes__``).
    """
    if falhas:
        erro.add_note(f"Antes do 401, {resumir_falhas(falhas, descricao)}")
