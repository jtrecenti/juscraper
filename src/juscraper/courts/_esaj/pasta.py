"""Documento público do eSAJ pela pasta digital, sem login.

Três rotas chegam à mesma página da pasta (``pastadigital/abrirDocumentoEdt.do``),
que traz ``"parametros":"..."``; ``pastadigital/getPDF.do?<parametros>`` devolve
o PDF do documento inteiro.

1. Acórdão, pela movimentação do 2º grau: ver :mod:`.acordao`.
2. Documento vinculado a uma movimentação do 1º grau. O link
   ``a.linkMovVincProc`` da movimentação aponta para
   ``cpopg/abrirDocumentoVinculadoMovimentacao.do?processo.codigo=...&cdDocumento=...``,
   que redireciona para a pasta. É a rota de ``tjsp_baixar_doc_movimentacao``
   no pacote R ``tjsp`` de jjesusfilho.
3. Sentença do cjpg. O atributo ``name`` do link "Visualizar Inteiro Teor" é
   ``cdProcesso-cdForo-nmAlias-cdDocumento``, e o ``consulta.js`` da página do
   cjpg monta com eles ``cjpg/obterArquivo.do``, que redireciona para a pasta.
   ``tjsp_baixar_sentenca_cjpg``, no mesmo pacote R, usa os mesmos quatro
   códigos para montar os ``parametros`` à mão.

O documento que pede a senha do processo traz ``href="#liberarAutoPorSenha"``
no lugar da URL: o HTML das movimentações já diz o que abre sem senha, sem
pedido a mais. O acesso com senha fica fora deste módulo (ver
jtrecenti/juscraper#481).

Estado de sessão (probe 2026-11): ``abrirDocumentoVinculadoMovimentacao.do``
só libera documento cuja página de movimentações a sessão já carregou, e
responde "Não foi possível validar o seu acesso" para os demais; ``getPDF.do``
também exige a sessão que abriu a pasta. A rota do cjpg funciona em sessão
nova.

Rotas confirmadas sem login em 2026-11: a 2 no TJSP, TJAC, TJAL, TJAM e TJCE (o
TJMS pede captcha na busca do cpopg); a 3 no TJSP e no TJMS (o TJCE pede
captcha no cjpg; TJAC, TJAL e TJAM não têm cjpg).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar
from urllib.parse import unquote_plus

import requests
from bs4 import BeautifulSoup, Tag

from ...core.failures import MOTIVO_NAO_PDF, MOTIVO_RESPOSTA_INESPERADA

ROTA_DOCUMENTO_MOVIMENTACAO = "abrirDocumentoVinculadoMovimentacao.do"
"""Fim do ``href`` do link de documento público numa movimentação do 1º grau."""

_PARAMETROS_RE = re.compile(r'"parametros":"([^"]+)"')
# O id do link é ``linkMovVincProc-<cdDocumento>`` (ícone) ou
# ``linkMovVincProc-2-<cdDocumento>`` (descrição), com ou sem senha.
_CD_DOCUMENTO_NO_ID = re.compile(r"^linkMovVincProc-(?:\d+-)?(\d+)$")
_ACESSO_NAO_VALIDADO = "Não foi possível validar o seu acesso"


class DocumentoIndisponivelError(Exception):
    """A rota respondeu, mas não entregou o PDF do documento.

    ``motivo`` é o valor de :data:`~juscraper.core.failures.COLUNA_MOTIVO_FALHA`
    que o chamador grava para o documento.
    """

    motivo: ClassVar[str]

    def __init__(self, documento: str, mensagem: str) -> None:
        self.documento = documento
        super().__init__(f"Documento {documento}: {mensagem}")


class DocumentoNaoPdfError(DocumentoIndisponivelError):
    """``getPDF.do`` respondeu com algo que não começa por ``%PDF``; nada é gravado."""

    motivo = MOTIVO_NAO_PDF


class PastaInesperadaError(DocumentoIndisponivelError):
    """A página que devia ser a da pasta não traz ``parametros``.

    Inclui a recusa "Não foi possível validar o seu acesso", que o eSAJ manda
    quando a sessão não listou o documento.
    """

    motivo = MOTIVO_RESPOSTA_INESPERADA


@dataclass(frozen=True)
class DocumentoVinculado:
    """Documento ligado a uma movimentação.

    ``url`` é o ``href`` do link, relativo à raiz do eSAJ, quando o documento
    abre sem senha; ``None`` quando o eSAJ pede a senha do processo.
    """

    cd_documento: str
    url: str | None

    @property
    def publico(self) -> bool:
        """``True`` quando o documento abre sem senha."""
        return self.url is not None


def parse_parametros_pasta(html: str) -> str | None:
    """Query string que ``getPDF.do`` espera, tirada da página da pasta digital.

    A pasta lista uma entrada por página do documento, todas com os mesmos
    ``parametros``; ``getPDF.do`` devolve o documento inteiro com qualquer uma.
    """
    encontrado = _PARAMETROS_RE.search(html)
    return encontrado.group(1) if encontrado else None


def tipo_documento(parametros: str) -> str:
    """``deTipoDocDigital`` dos ``parametros``, que o eSAJ codifica em latin-1."""
    for par in parametros.split("&"):
        chave, _, valor = par.partition("=")
        if chave == "deTipoDocDigital":
            return unquote_plus(valor, encoding="latin-1")
    return ""


def documento_vinculado(link: Tag) -> DocumentoVinculado | None:
    """Documento do link ``a.linkMovVincProc``, ou ``None`` se o id não traz o código.

    O código vem do ``id`` do link, que só tem dígitos, e não do ``href``: o
    link com senha não traz ``cdDocumento`` na URL. Público é só o link que
    aponta para :data:`ROTA_DOCUMENTO_MOVIMENTACAO`; ``#liberarAutoPorSenha`` e
    qualquer outro ``href`` contam como fechados.
    """
    achado = _CD_DOCUMENTO_NO_ID.match(str(link.get("id") or ""))
    if achado is None:
        return None
    href = str(link.get("href") or "")
    publico = href.split("?", 1)[0].endswith(ROTA_DOCUMENTO_MOVIMENTACAO)
    return DocumentoVinculado(achado.group(1), href.lstrip("/") if publico else None)


def documentos_vinculados(html: str) -> list[DocumentoVinculado]:
    """Documentos das movimentações de uma página, na ordem dela e sem repetição.

    Cada movimentação com documento tem dois links (ícone e descrição) para o
    mesmo ``cdDocumento``; fica o primeiro.
    """
    vistos: dict[str, DocumentoVinculado] = {}
    for link in BeautifulSoup(html, "html.parser").find_all("a", class_="linkMovVincProc"):
        documento = documento_vinculado(link) if isinstance(link, Tag) else None
        if documento is not None:
            vistos.setdefault(documento.cd_documento, documento)
    return list(vistos.values())


def pdf_pela_pasta(
    get: Callable[[str], requests.Response],
    url: str,
    url_base: str,
    documento: str,
) -> bytes:
    """PDF do documento cuja pasta ``url`` abre (direto ou por redirecionamento).

    Args:
        get: Faz o GET na sessão que deve abrir a pasta e levanta ``HTTPError``
            em status de erro.
        url: URL que leva à página da pasta.
        url_base: Raiz do eSAJ, terminada em ``/``. O ``getPDF.do`` sai dela, e
            não do endereço para onde o redirecionamento levou.
        documento: Identificador do documento, para as mensagens de erro.

    Raises:
        PastaInesperadaError: A página não traz ``parametros``.
        DocumentoNaoPdfError: ``getPDF.do`` respondeu sem ``%PDF``.
    """
    pagina = get(url)
    parametros = parse_parametros_pasta(pagina.text)
    if parametros is None:
        if _ACESSO_NAO_VALIDADO in pagina.text:
            raise PastaInesperadaError(documento, "o eSAJ recusou o acesso: a sessão não listou o documento.")
        raise PastaInesperadaError(documento, f"a página de {pagina.url} não traz 'parametros'.")
    resposta = get(f"{url_base}pastadigital/getPDF.do?{parametros}")
    if not resposta.content.startswith(b"%PDF"):
        inicio = resposta.content[:60].decode("utf-8", "replace")
        raise DocumentoNaoPdfError(
            documento,
            f"getPDF.do respondeu {resposta.headers.get('Content-Type')!r} começando por {inicio!r}; nada foi gravado.",
        )
    return resposta.content


def gravar_pdf(conteudo: bytes, destino: Path) -> Path:
    """Grava por arquivo temporário renomeado: falha no meio não deixa PDF truncado."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(".tmp")
    try:
        temporario.write_bytes(conteudo)
        temporario.replace(destino)
    except OSError:
        temporario.unlink(missing_ok=True)
        raise
    return destino
