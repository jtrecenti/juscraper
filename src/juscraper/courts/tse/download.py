"""Endereços, pedidos e leitura das respostas das rotas abertas do TSE.

O portal de jurisprudência (``jurisprudencia.tse.jus.br``) fala com dois
serviços. O de pesquisa (``sjur-pesquisa-api``) exige um token de captcha na
busca, mas entrega sem ele os catálogos do formulário. O de documentos
(``sjur-servicos``) entrega o PDF do inteiro teor pelo código da decisão.

O portal dos TREs (``jurisprudencia-tres.tse.jus.br``) usa os mesmos serviços.
No de pesquisa, o primeiro segmento do caminho escolhe o tribunal: ``tse``,
``tre-<uf>`` ou ``tres`` (os 27 TREs juntos); a busca pede o mesmo captcha. O
de documentos não tem esse segmento: o código de uma decisão de TRE baixa
pela mesma rota. Sondas de 16/11/2026.
"""

from __future__ import annotations

import numbers
from typing import Any, ClassVar

import requests

from juscraper.core.exceptions import _RecriaSemInit
from juscraper.core.failures import MOTIVO_LIMITE_DE_REQUISICOES, MOTIVO_NAO_PDF

PESQUISA_API = "https://sjur-pesquisa-api.tse.jus.br"
PESQUISA_ROTA = "sjur-pesquisa-backend/rest/public/pesquisa"
PESQUISA_URL = f"{PESQUISA_API}/tse/{PESQUISA_ROTA}"
INTEIRO_TEOR_URL = "https://sjur-servicos.tse.jus.br/sjur-servicos/rest/download/pdf"

CATALOGOS = ("classes", "relatorias", "eleicoes", "normas")
"""Sub-rotas de ``PESQUISA_URL`` que devolvem um catálogo do formulário."""

TRIBUNAIS = (
    "tse",
    "tres",
    *(
        f"tre-{uf}"
        for uf in (
            "ac", "al", "am", "ap", "ba", "ce", "df", "es", "go", "ma", "mg", "ms", "mt", "pa",
            "pb", "pe", "pi", "pr", "rj", "rn", "ro", "rr", "rs", "sc", "se", "sp", "to",
        )
    ),
)
"""Valores de ``tribunal`` nos catálogos: o TSE, cada TRE e ``tres``, os 27 TREs juntos."""

# Sem o corpo ``[]`` a rota responde HTTP 500.
CATALOGO_BODY: list[Any] = []

# Segundos entre dois pedidos de inteiro teor: o serviço aceitou pedidos a cada
# 10 s e recusou a 5 s com "Excesso de requisições".
INTERVALO_INTEIRO_TEOR = 10.0

EXCESSO_DE_REQUISICOES = "Excesso de requisições"


class InteiroTeorIndisponivelError(_RecriaSemInit):
    """O serviço respondeu, mas não entregou o PDF do inteiro teor; nada é gravado.

    ``motivo`` é o valor de :data:`~juscraper.core.failures.COLUNA_MOTIVO_FALHA`
    da linha em ``baixar_inteiros_teores``.

    Attributes:
        codigo_decisao: Código pedido.
    """

    motivo: ClassVar[str] = MOTIVO_NAO_PDF

    def __init__(self, codigo_decisao: str, mensagem: str) -> None:
        """Guarda o código e prefixa a mensagem com ele."""
        self.codigo_decisao = codigo_decisao
        super().__init__(f"Decisão {codigo_decisao}: {mensagem}")


class LimiteDeRequisicoesError(InteiroTeorIndisponivelError):
    """O serviço recusou o pedido com "Excesso de requisições"; basta esperar e pedir de novo."""

    motivo = MOTIVO_LIMITE_DE_REQUISICOES


def normalizar_tribunal(tribunal: object) -> str:
    """Devolve ``tribunal`` em minúsculas; recusa o que não está em :data:`TRIBUNAIS`.

    Raises:
        ValueError: Tribunal desconhecido, antes de qualquer pedido.
    """
    sigla = tribunal.strip().lower() if isinstance(tribunal, str) else tribunal
    if sigla not in TRIBUNAIS:
        raise ValueError(f"tribunal deve ser 'tse', 'tres' ou 'tre-<uf>' (como 'tre-sp'), recebido {tribunal!r}.")
    return str(sigla)


def catalogo_url(catalogo: str, tribunal: str = "tse") -> str:
    """URL do ``catalogo`` (um de :data:`CATALOGOS`) de ``tribunal`` (um de :data:`TRIBUNAIS`)."""
    return f"{PESQUISA_API}/{tribunal}/{PESQUISA_ROTA}/{catalogo}"


def inteiro_teor_url(codigo_decisao: str) -> str:
    """URL do PDF do inteiro teor da decisão ``codigo_decisao``."""
    return f"{INTEIRO_TEOR_URL}/{codigo_decisao}"


def normalizar_codigo_decisao(codigo_decisao: object) -> str:
    """Devolve o código como texto de dígitos; recusa o resto antes de qualquer pedido.

    Raises:
        ValueError: Se ``codigo_decisao`` não for inteiro nem texto só de dígitos.
    """
    texto = None
    if isinstance(codigo_decisao, str):
        texto = codigo_decisao.strip()
    # ``numbers.Integral`` aceita também os inteiros do numpy, de código lido de um DataFrame.
    elif not isinstance(codigo_decisao, bool) and isinstance(codigo_decisao, numbers.Integral):
        texto = str(int(codigo_decisao))
    # ``isascii`` barra os dígitos de outros alfabetos; o sinal de um negativo não é dígito.
    if texto and texto.isascii() and texto.isdigit():
        return texto
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
    # Por posições, para copiar o PDF uma vez só.
    fim_do_limite = corpo.find(b"\r\n")
    inicio = corpo.find(b"\r\n\r\n", fim_do_limite) + 4
    fim = corpo.rfind(b"\r\n" + corpo[:fim_do_limite] + b"--", inicio)
    if fim_do_limite == -1 or inicio < 4 or fim == -1 or not corpo.startswith(b"%PDF", inicio):
        return None
    return corpo[inicio:fim]


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
    if EXCESSO_DE_REQUISICOES in inicio:
        raise LimiteDeRequisicoesError(
            codigo_decisao,
            f"o TSE recusou o pedido por excesso de requisições ({inicio!r}). "
            f"Espere ao menos {INTERVALO_INTEIRO_TEOR:.0f} s e peça de novo.",
        )
    raise InteiroTeorIndisponivelError(
        codigo_decisao,
        f"o TSE respondeu {resposta.headers.get('Content-Type')!r} sem PDF ({inicio!r}); nada foi gravado.",
    )
