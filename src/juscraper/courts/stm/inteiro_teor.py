"""Download do inteiro teor dos acórdãos do STM.

A coluna ``url_inteiro_teor`` do ``cjsg`` aponta para dois endereços, e os
dois devolvem o PDF direto (sonda de 16/11/2026, de IP aceito pelo portal):
o visualizador do eproc, nos acórdãos recentes, e a pasta de PDFs em
``www2.stm.jus.br``, nos antigos.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

import requests

from juscraper.core.exceptions import _RecriaSemInit

HOST_EPROC = "eproc2g.stm.jus.br"
HOST_WWW2 = "www2.stm.jus.br"
_UUID = re.compile(r"[0-9a-fA-F]+")
_PDF_DO_WWW2 = re.compile(r"/pesquisa/acordao/(?:[\w.\-]+/)*([\w.\-]+\.pdf)")


class InteiroTeorIndisponivelError(_RecriaSemInit):
    """O portal respondeu, mas não entregou o PDF do inteiro teor; nada é gravado.

    Attributes:
        url: Endereço pedido.
    """

    def __init__(self, url: str, mensagem: str) -> None:
        """Guarda o endereço e prefixa a mensagem com ele."""
        self.url = url
        super().__init__(f"Inteiro teor {url}: {mensagem}")


def nome_do_arquivo(url_inteiro_teor: object) -> str:
    """Nome do PDF de ``url_inteiro_teor``; recusa o que não é endereço de inteiro teor do STM.

    No eproc, o nome é o ``uuid`` do acórdão; em ``www2``, o do próprio arquivo.

    Raises:
        ValueError: Se não for um dos dois formatos que o ``cjsg`` devolve.
    """
    if isinstance(url_inteiro_teor, str):
        partes = urlsplit(url_inteiro_teor.strip())
        if partes.scheme == "https" and partes.netloc == HOST_EPROC:
            uuids = parse_qs(partes.query).get("uuid", [])
            if len(uuids) == 1 and _UUID.fullmatch(uuids[0]):
                return f"{uuids[0]}.pdf"
        if partes.scheme == "https" and partes.netloc == HOST_WWW2:
            pdf = _PDF_DO_WWW2.fullmatch(partes.path)
            if pdf:
                return pdf.group(1)
    raise ValueError(
        "STM: url_inteiro_teor deve ser um endereço da coluna 'url_inteiro_teor' do cjsg "
        f"(https://{HOST_EPROC}/...&uuid=... ou https://{HOST_WWW2}/pesquisa/acordao/....pdf), "
        f"recebido {url_inteiro_teor!r}."
    )


def pdf_da_resposta(resposta: requests.Response, url: str) -> bytes:
    """PDF do inteiro teor em ``resposta``.

    Raises:
        InteiroTeorIndisponivelError: Quando a resposta não é um PDF.
    """
    if resposta.content.startswith(b"%PDF"):
        return resposta.content
    inicio = resposta.content[:200].decode("utf-8", "replace").strip()
    raise InteiroTeorIndisponivelError(
        url, f"o STM respondeu {resposta.headers.get('Content-Type')!r} sem PDF ({inicio!r}); nada foi gravado."
    )
