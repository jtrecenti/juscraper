"""Download das páginas da busca de jurisprudência do STM."""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

import requests
from bs4 import BeautifulSoup

from juscraper.core.avisos import avisar
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

# Pesquisa avançada do portal, a única que filtra por intervalo de datas. O
# formulário monta a consulta no navegador (``processAdvsearch``, em
# ``js/util.js``) e a manda pronta em ``q``.
# Filtro de data do método público -> campo de data da consulta avançada.
_CAMPOS_DE_DATA = {"data_julgamento": "data_decisao", "data_publicacao": "data_publicacao"}
_PONTUACAO_DO_NUMERO = re.compile(r"[.\-/]")
# Operadores e curingas da busca simples, que a expressão exata não aplica.
_OPERADORES = re.compile(r"\s|[*?]")

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


def _termo_exato(pesquisa: str) -> tuple[str, bool]:
    """Devolve o termo sem o par de aspas que o envolve e se ele veio entre aspas."""
    termo = pesquisa.strip()
    entre_aspas = len(termo) > 1 and termo[0] == termo[-1] == '"'
    return (termo[1:-1].strip() if entre_aspas else termo), entre_aspas


def _clausula_do_termo(pesquisa: str, campo: str) -> str | None:
    """Cláusula do termo na consulta avançada; ``None`` quando não há termo."""
    termo, _ = _termo_exato(pesquisa)
    if not termo:
        return None
    if campo == "numero":
        digitos = _PONTUACAO_DO_NUMERO.sub("", termo)
        if not digitos.isdigit():
            raise ValueError(
                "STM: com filtro de data, 'pesquisa' em campo='numero' aceita só dígitos e a pontuação do número "
                f"do processo (recebido: {pesquisa!r})."
            )
        return f"(numero_processo:*{digitos}*)"
    if '"' in termo or "\\" in termo:
        raise ValueError(
            "STM: com filtro de data, 'pesquisa' é procurada como expressão exata e não pode ter aspas no meio "
            f"nem barra invertida (recebido: {pesquisa!r})."
        )
    return f'({campo}:"{termo}")'


def avisar_expressao_exata(pesquisa: str, campo: str) -> None:
    """Avisa quando a pesquisa avançada vai ler como expressão exata um termo com operador ou curinga."""
    termo, entre_aspas = _termo_exato(pesquisa)
    if campo != "numero" and not entre_aspas and _OPERADORES.search(termo):
        avisar(
            "STM: com filtro de data, a busca vai pela pesquisa avançada do portal, que procura 'pesquisa' como "
            f"expressão exata ({termo!r}) e não aplica os operadores E, OU e NÃO nem os curingas. "
            "Ponha o termo entre aspas para confirmar a expressão exata e dispensar este aviso."
        )


def montar_consulta_avancada(pesquisa: str, campo: str, datas: Mapping[str, str | None]) -> str | None:
    """Monta a consulta da pesquisa avançada do STM; ``None`` quando não há filtro de data.

    Repete o que o formulário do portal envia: o termo como expressão exata
    no campo escolhido, ``(ementa:"deserção")``, e cada intervalo como
    ``(data_decisao:[2024-01-01T00:00:00.000Z TO 2024-01-31T23:59:59.000Z])``,
    ligados por ``AND``. ``datas`` traz ``data_julgamento_inicio/fim`` e
    ``data_publicacao_inicio/fim`` em ``AAAA-MM-DD``; o lado que falta num
    intervalo vai como ``*``. Sem termo, a consulta fica só com os intervalos.

    Raises:
        ValueError: Quando o termo tem aspas no meio ou barra invertida, ou,
            em ``campo="numero"``, algo além do número do processo.
    """
    intervalos = []
    for filtro, campo_de_data in _CAMPOS_DE_DATA.items():
        inicio, fim = datas.get(f"{filtro}_inicio"), datas.get(f"{filtro}_fim")
        if inicio or fim:
            de = f"{inicio}T00:00:00.000Z" if inicio else "*"
            ate = f"{fim}T23:59:59.000Z" if fim else "*"
            intervalos.append(f"({campo_de_data}:[{de} TO {ate}])")
    if not intervalos:
        return None
    termo = _clausula_do_termo(pesquisa, campo)
    return " AND ".join([termo, *intervalos] if termo else intervalos)


def build_cjsg_params(
    pesquisa: str,
    pagina: int = 1,
    campo: str = "ementa",
    *,
    datas: Mapping[str, str | None] | None = None,
    **filtros: str | None,
) -> dict[str, str]:
    """Monta a query string da busca de jurisprudência do STM.

    Repete o que o formulário do portal envia. Na busca simples, o termo vai
    em ``q``, ``q_or`` e ``search_input``, e o portal traduz os operadores
    (``E``, ``OU``, ``NÃO``) do lado dele. Com filtro de data em ``datas``, a
    busca é a avançada: ``q`` leva a consulta de
    :func:`montar_consulta_avancada`. ``filtros`` aceita ``classe``,
    ``relator``, ``relator_acordao``, ``revisor`` e ``assunto``; ``None`` ou
    vazio não entra na query.
    """
    params = {"search_filter_option": "jurisprudencia"}
    consulta = montar_consulta_avancada(pesquisa, campo, datas or {})
    if consulta is None:
        params |= {"search_filter": campo, "search_input": pesquisa, "q": pesquisa, "q_or": pesquisa}
    else:
        params |= {"search_filter": "busca_avancada", "q": consulta, "q_or": ""}
    params |= {"start": str((pagina - 1) * RESULTS_PER_PAGE), "rows": str(RESULTS_PER_PAGE)}
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
    **busca: Any,
) -> list[str]:
    """Baixa as páginas de resultados da busca de jurisprudência do STM.

    ``busca`` leva os demais argumentos de :func:`build_cjsg_params`:
    ``campo``, ``datas`` e os filtros da coluna "Filtrar por".

    Raises:
        BotChallengeBlockedError: Quando o WAF recusa a requisição.
        ValueError: Quando há filtro de data e o termo não cabe na consulta
            avançada (ver :func:`montar_consulta_avancada`); quando a primeira página pedida não traz o contador de
            documentos nem o aviso de busca vazia, ou quando uma das seguintes
            vem sem documentos.

    Returns:
        O HTML de cada página, na ordem pedida.
    """
    primeira = menor_pagina(paginas)
    if any((busca.get("datas") or {}).values()):
        avisar_expressao_exata(pesquisa, busca.get("campo", "ementa"))

    def buscar(pagina: int) -> str:
        resp = request_fn(
            "GET",
            BASE_URL,
            params=build_cjsg_params(pesquisa, pagina, **busca),
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
