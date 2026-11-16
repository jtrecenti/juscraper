"""Download das páginas da busca de jurisprudência do STM."""
from __future__ import annotations

import re
from collections.abc import Iterable

import requests
from bs4 import BeautifulSoup

from juscraper.core.exceptions import BotChallengeBlockedError
from juscraper.core.http import RequestFn
from juscraper.utils.pagination import (
    baixar_paginas_pedidas,
    extract_count_with_cascade,
    menor_pagina,
    resolve_total_pages,
)

BASE_URL = "https://jurisprudencia.stm.jus.br/consulta.php"
# O portal oferece 25, 50 e 100 documentos por página; 100 reduz os pedidos.
RESULTS_PER_PAGE = 100

# Filtro do método público -> parâmetro da coluna "Filtrar por" do portal.
_FILTROS = {
    "classe": "fq_classe",
    "relator": "fq_ministro_relator",
    "relator_acordao": "fq_ministro_relator_acordao",
    "revisor": "fq_ministro_revisor",
    "assunto": "fq_assunto_pesquisa",
}

# Contador da página de resultados: "<b>1</b> - <b>100</b> de <b>351</b> documentos".
_COUNT_SELECTORS = ("div.row.message",)
# Abertura desse ``div`` no HTML bruto e quanto dele basta para ler o contador.
_COUNT_ANCHOR = '<div class="row message">'
_COUNT_TRECHO = 2000
_COUNT_PATTERNS = (re.compile(r"[\d.]+\s*-\s*[\d.]+\s*de\s*([\d.]+)\s*documentos", re.IGNORECASE),)
# Busca sem resultados: o portal redireciona para ``index.php`` e mostra o
# aviso num ``div.alert-danger``. O marcador só vale dentro desse aviso.
_ZERO_SELECTOR = "div.alert-danger"
_ZERO_MARKER = "Nenhum documento encontrado"
# Página do WAF, servida com HTTP 200 no lugar do portal.
_WAF_MARKER = b"<title>Request Rejected</title>"
_WAF_SUPPORT_ID = re.compile(r"support ID is:\s*(\d+)")


def build_cjsg_params(
    pesquisa: str,
    pagina: int = 1,
    campo: str = "ementa",
    **filtros: str | None,
) -> dict[str, str]:
    """Monta a query string da busca de jurisprudência do STM.

    Repete o que o formulário do portal envia: o termo vai em ``q``, ``q_or``
    e ``search_input``, e o portal traduz os operadores (``E``, ``OU``,
    ``NÃO``) do lado dele. ``filtros`` aceita ``classe``, ``relator``,
    ``relator_acordao``, ``revisor`` e ``assunto``; ``None`` ou vazio não
    entra na query.
    """
    params = {
        "search_filter_option": "jurisprudencia",
        "search_filter": campo,
        "search_input": pesquisa,
        "q": pesquisa,
        "q_or": pesquisa,
        "start": str((pagina - 1) * RESULTS_PER_PAGE),
        "rows": str(RESULTS_PER_PAGE),
    }
    for nome, valor in filtros.items():
        if valor:
            params[_FILTROS[nome]] = valor
    return params


def conferir_bloqueio(resp: requests.Response) -> None:
    """Levanta :class:`BotChallengeBlockedError` se a resposta for a página do WAF.

    Vai em ``on_response=``, para valer antes da política de novas tentativas.

    O WAF do STM recusa o pedido com HTTP 200 e uma página "Request
    Rejected". Em 16/11/2026, recusou todos os pedidos de um IP de datacenter
    fora do Brasil.
    """
    if _WAF_MARKER not in resp.content:
        return
    support_id = _WAF_SUPPORT_ID.search(resp.text)
    raise BotChallengeBlockedError(
        "STM",
        resp.url,
        reference=support_id.group(1) if support_id else None,
        bot_manager="WAF",
        mensagem=(
            f"O WAF do STM recusou a requisição em {resp.url} (página 'Request Rejected', com HTTP 200). "
            "O bloqueio depende do IP de origem; tente de outra conexão, como uma residencial no Brasil."
        ),
    )


def cjsg_n_resultados(html: str) -> int | None:
    """Lê o total de documentos de uma página do STM: o contador, ou 0 no aviso de busca vazia.

    ``None`` quando a página não traz nem um nem outro. A página de
    resultados passa de 1 MB, e por isso o contador é lido primeiro só no
    trecho que o contém; a página inteira é parseada quando ele não aparece.
    """
    inicio = html.find(_COUNT_ANCHOR)
    if inicio >= 0:
        trecho = html[inicio:inicio + _COUNT_TRECHO]
        no_trecho = extract_count_with_cascade(trecho, css_selectors=_COUNT_SELECTORS, regex_patterns=_COUNT_PATTERNS)
        if no_trecho is not None:
            return no_trecho
    soup = BeautifulSoup(html, "html.parser")
    n_resultados = extract_count_with_cascade(soup, css_selectors=_COUNT_SELECTORS, regex_patterns=_COUNT_PATTERNS)
    if n_resultados is None and any(_ZERO_MARKER in aviso.get_text() for aviso in soup.select(_ZERO_SELECTOR)):
        return 0
    return n_resultados


def cjsg_n_pags(html: str) -> int:
    """Lê o total de páginas de uma página de resultados do STM.

    Raises:
        ValueError: Quando a página não traz o contador nem o aviso de busca
            vazia; ver :func:`~juscraper.utils.pagination.resolve_total_pages`.
    """
    return resolve_total_pages(cjsg_n_resultados(html), resultados_por_pagina=RESULTS_PER_PAGE, tribunal="STM")


def cjsg_download_manager(
    pesquisa: str,
    paginas: Iterable[int] | None = None,
    *,
    request_fn: RequestFn,
    sleep_time: float = 1.0,
    campo: str = "ementa",
    **filtros: str | None,
) -> list[str]:
    """Baixa as páginas de resultados da busca de jurisprudência do STM.

    ``campo`` e ``filtros`` são os de :class:`~juscraper.courts.stm.schemas.InputCJSGSTM`.

    Raises:
        BotChallengeBlockedError: Quando o WAF recusa a requisição.
        ValueError: Quando a primeira página pedida não traz o contador de
            documentos nem o aviso de busca vazia, ou quando uma das seguintes
            vem sem documentos.

    Returns:
        O HTML de cada página, na ordem pedida.
    """
    primeira = menor_pagina(paginas)

    def buscar(pagina: int) -> str:
        resp = request_fn(
            "GET",
            BASE_URL,
            params=build_cjsg_params(pesquisa, pagina, campo, **filtros),
            perfil="cjsg",
            on_response=conferir_bloqueio,
        )
        resp.encoding = "utf-8"
        html = resp.text
        # ``primeira`` é conferida por ``cjsg_n_pags``. As demais só são
        # pedidas dentro do total: sem contador, não são de resultados.
        if pagina != primeira and not cjsg_n_resultados(html):
            raise ValueError(f"STM: a página {pagina} da busca veio sem o contador de documentos.")
        return html

    return baixar_paginas_pedidas(paginas, buscar, cjsg_n_pags, tribunal="STM", sleep_time=sleep_time)
