"""Endereços, pedidos e leitura das respostas das rotas abertas do TSE.

O portal de jurisprudência (``jurisprudencia.tse.jus.br``) fala com dois
serviços. O de pesquisa (``sjur-pesquisa-api``) exige um token de captcha na
busca, mas entrega sem ele os catálogos do formulário. O de documentos
(``sjur-servicos``) entrega o PDF do inteiro teor pelo código da decisão.
Sondas de 16/11/2026.
"""

from __future__ import annotations

from typing import Any

import requests

from juscraper.core.exceptions import _RecriaSemInit

PESQUISA_URL = "https://sjur-pesquisa-api.tse.jus.br/tse/sjur-pesquisa-backend/rest/public/pesquisa"
INTEIRO_TEOR_URL = "https://sjur-servicos.tse.jus.br/sjur-servicos/rest/download/pdf"

CATALOGOS = ("classes", "relatorias", "eleicoes", "normas")
"""Sub-rotas de ``PESQUISA_URL`` que devolvem um catálogo do formulário."""

# Sem o corpo ``[]`` a rota responde HTTP 500.
CATALOGO_BODY: list[Any] = []

# Segundos entre dois pedidos de inteiro teor: o serviço aceitou pedidos a cada
# 10 s e recusou a 5 s com "Excesso de requisições".
INTERVALO_INTEIRO_TEOR = 10.0

_EXCESSO_DE_REQUISICOES = "Excesso de requisições"


class InteiroTeorIndisponivelError(_RecriaSemInit):
    """O serviço respondeu, mas não entregou o PDF do inteiro teor; nada é gravado.

    Attributes:
        codigo_decisao: Código pedido.
    """

    def __init__(self, codigo_decisao: str, mensagem: str) -> None:
        """Guarda o código e prefixa a mensagem com ele."""
        self.codigo_decisao = codigo_decisao
        super().__init__(f"Decisão {codigo_decisao}: {mensagem}")


class LimiteDeRequisicoesError(InteiroTeorIndisponivelError):
    """O serviço recusou o pedido com "Excesso de requisições"; basta esperar e pedir de novo."""


def catalogo_url(catalogo: str) -> str:
    """URL do ``catalogo`` (um de :data:`CATALOGOS`)."""
    if catalogo not in CATALOGOS:
        raise ValueError(f"Catálogo desconhecido: {catalogo!r}. Use um de: {', '.join(CATALOGOS)}.")
    return f"{PESQUISA_URL}/{catalogo}"


def inteiro_teor_url(codigo_decisao: str) -> str:
    """URL do PDF do inteiro teor da decisão ``codigo_decisao``."""
    return f"{INTEIRO_TEOR_URL}/{codigo_decisao}"


def normalizar_codigo_decisao(codigo_decisao: object) -> str:
    """Devolve o código como texto de dígitos; recusa o resto antes de qualquer pedido.

    Raises:
        ValueError: Se ``codigo_decisao`` não for inteiro nem texto só de dígitos.
    """
    if isinstance(codigo_decisao, int) and not isinstance(codigo_decisao, bool) and codigo_decisao >= 0:
        return str(codigo_decisao)
    if isinstance(codigo_decisao, str) and codigo_decisao.strip().isascii() and codigo_decisao.strip().isdigit():
        return codigo_decisao.strip()
    raise ValueError(f"codigo_decisao deve ser um inteiro ou um texto só de dígitos, recebido {codigo_decisao!r}.")


def extrair_pdf(corpo: bytes) -> bytes | None:
    """PDF contido em ``corpo``, ou ``None`` quando não há um.

    O serviço manda o PDF de dois jeitos, sempre com ``Content-Type:
    application/pdf``: o arquivo puro ou um envelope ``multipart/form-data``
    com uma parte só (linha do limite, cabeçalhos, linha em branco, PDF e o
    limite de fechamento). Envelope sem o limite de fechamento é resposta
    cortada e não rende PDF.
    """
    if corpo.startswith(b"%PDF"):
        return corpo
    if not corpo.startswith(b"--"):
        return None
    limite, _, resto = corpo.partition(b"\r\n")
    _, separador, conteudo = resto.partition(b"\r\n\r\n")
    fim = conteudo.rfind(b"\r\n" + limite + b"--")
    if not separador or fim == -1:
        return None
    pdf = conteudo[:fim]
    return pdf if pdf.startswith(b"%PDF") else None


def pdf_da_resposta(resposta: requests.Response, codigo_decisao: str) -> bytes:
    """PDF do inteiro teor em ``resposta``.

    O serviço responde HTTP 200 também quando não entrega o documento, com a
    explicação em texto puro.

    Raises:
        LimiteDeRequisicoesError: O serviço respondeu "Excesso de requisições".
        InteiroTeorIndisponivelError: Qualquer outra resposta sem PDF, como a
            de código que não existe.
    """
    pdf = extrair_pdf(resposta.content)
    if pdf is not None:
        return pdf
    inicio = resposta.content[:300].decode("utf-8", "replace").strip()
    if _EXCESSO_DE_REQUISICOES in inicio:
        raise LimiteDeRequisicoesError(
            codigo_decisao,
            f"o TSE recusou o pedido por excesso de requisições ({inicio!r}). "
            f"Espere ao menos {INTERVALO_INTEIRO_TEOR:.0f} s e peça de novo.",
        )
    raise InteiroTeorIndisponivelError(
        codigo_decisao,
        f"o TSE respondeu {resposta.headers.get('Content-Type')!r} sem PDF ({inicio!r}); nada foi gravado.",
    )
