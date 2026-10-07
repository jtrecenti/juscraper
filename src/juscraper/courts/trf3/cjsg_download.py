"""Download da busca de jurisprudência do TRF3 (``web.trf3.jus.br/jurisprudencia``).

O portal é ASP.NET MVC com estado na sessão do servidor. A sequência é fixa:

1. ``GET home/index/{n}`` abre a sessão (cookie ``ASP.NET_SessionId``) e escolhe
   a base. A base fica gravada na sessão, não no formulário: os campos do POST
   são os mesmos nas três abas.
2. ``POST Home/ResultadoTotais`` executa a busca e redireciona para
   ``Home/ListaResumida/1?np=0``, que já é a página 1 da lista.
3. ``GET Home/ListaResumida/2?np=N`` traz a página N da mesma busca.

Sem o passo 1 o POST cai em ``Home/SessaoExpirada``. Por isso cada chamada de
:func:`cjsg_download_manager` usa uma ``requests.Session`` própria: duas buscas
na mesma sessão disputariam o mesmo estado no servidor.

A lista resumida já traz, para cada documento, a ementa e o inteiro teor (em
blocos ocultos), então não há uma requisição por documento. O custo de uma
busca é de duas requisições fixas mais uma por página além da primeira.
"""
from __future__ import annotations

import logging
import math
import re
import time
from collections.abc import Callable, Iterable

import requests
from tqdm import tqdm

from ...core.exceptions import BotChallengeBlockedError
from ...core.http import RequestFn
from ...utils.pagination import extract_count_with_cascade

logger = logging.getLogger("juscraper.trf3.cjsg")

BASE_URL = "https://web.trf3.jus.br/jurisprudencia/"
INDEX_URL = BASE_URL + "home/index/{indice}"
SEARCH_URL = BASE_URL + "Home/ResultadoTotais"
PAGE_URL = BASE_URL + "Home/ListaResumida/2"
SESSAO_EXPIRADA_PATH = "Home/SessaoExpirada"
TAMANHOS_PAGINA = (10, 30, 50)

#: Aba do portal (``home/index/{n}``) e caixas de origem de cada base. As
#: monocráticas do TRF3 e as das Turmas Recursais saem da mesma aba e se
#: separam pelas caixas ``in_juizado_trf3`` e ``in_juizado_recursal``.
BASES: dict[str, tuple[int, dict[str, str]]] = {
    "acordaos": (0, {}),
    "turmas_recursais": (1, {}),
    "monocraticas": (2, {"in_juizado_trf3": "on"}),
    "monocraticas_turmas_recursais": (2, {"in_juizado_recursal": "on"}),
}

#: Valores de ``data_tipo``. Na aba de monocráticas o rótulo do 1 é "Decisão".
DATA_TIPO = {"publicacao": "0", "julgamento": "1"}

# Cabeçalhos de navegador. O portal fica atrás do bot manager da Akamai, que
# deixa a conexão pendurada em requisições sem os cabeçalhos Sec-Fetch-*.
CJSG_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/147.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
}

_AKAMAI_REF_RE = re.compile(
    rb"Reference(?:&#32;|\s)(?:&#35;|#)([0-9a-f]+(?:(?:&#46;|\.)[0-9a-f]+)*)"
)


def build_cjsg_session() -> requests.Session:
    """Cria a sessão isolada de uma busca, com os cabeçalhos de navegador."""
    session = requests.Session()
    session.headers.update(CJSG_HEADERS)
    return session


def _texto_campo(valor: str | None, molde: str) -> str:
    """Aplica o molde de campo indexado do portal, ou devolve vazio.

    O JavaScript do formulário copia o texto da opção escolhida para os campos
    ocultos nesses moldes (``((NOME)).rel.``, ``(CLASSE).dclas.``,
    ``(ORGAO).org.``); o servidor ignora o ID numérico do dropdown e pesquisa
    só esse texto.
    """
    valor = (valor or "").strip()
    return molde.format(valor) if valor else ""


def build_cjsg_payload(
    pesquisa: str = "",
    *,
    base: str = "acordaos",
    tamanho_pagina: int = 10,
    numero_processo: str = "",
    relator: str = "",
    classe: str = "",
    orgao_julgador: str = "",
    ementa: str = "",
    indexacao: str = "",
    data_inicial: str = "",
    data_final: str = "",
    data_tipo: str = DATA_TIPO["julgamento"],
) -> dict[str, str]:
    """Monta o corpo form-urlencoded do ``POST Home/ResultadoTotais``.

    Reproduz o que o formulário de pesquisa avançada envia. ``magistrado``,
    ``classe`` e ``orgao`` vão como ``"0"`` (sem seleção no dropdown); o filtro
    de verdade viaja nos campos ocultos ``hdnMagistrado``, ``hdnClasse`` e
    ``hdnOrgao``. ``chkMostrarLista=on`` pede a lista resumida, que já traz
    ementa e inteiro teor de cada documento.

    Args:
        pesquisa: Texto da pesquisa livre.
        base: Chave de :data:`BASES`; decide as caixas de origem das
            monocráticas. A aba em si é escolhida pelo ``GET`` anterior.
        tamanho_pagina: 10, 30 ou 50 documentos por página.
        numero_processo: Número do processo, com ou sem máscara.
        relator: Nome do relator como o portal indexa (ex.: ``"NERY JUNIOR"``).
        classe: Classe como no dropdown (ex.: ``"AI - AGRAVO DE INSTRUMENTO"``).
        orgao_julgador: Órgão julgador como o portal indexa.
        ementa: Texto pesquisado só na ementa.
        indexacao: Texto pesquisado na indexação ("Objeto do Processo" nas
            Turmas Recursais).
        data_inicial: ``DD/MM/AAAA``.
        data_final: ``DD/MM/AAAA``.
        data_tipo: ``"0"`` publicação, ``"1"`` julgamento (ou decisão).

    Returns:
        Dicionário pronto para ``data=`` do ``requests``.
    """
    payload = {
        "txtPesquisaLivre": pesquisa or "",
        "chkAcordaos": "on",
        "chkMostrarLista": "on",
        "opcaoQtdePagina": str(tamanho_pagina),
        "numero": numero_processo or "",
        "magistrado": "0",
        "data_inicial": data_inicial or "",
        "data_final": data_final or "",
        "data_tipo": data_tipo,
        "classe": "0",
        "orgao": "0",
        "ementa": ementa or "",
        "indexacao": indexacao or "",
        "hdnMagistrado": _texto_campo(relator, "(({})).rel."),
        "hdnClasse": _texto_campo(classe, "({}).dclas."),
        "hdnOrgao": _texto_campo(orgao_julgador, "({}).org."),
    }
    payload.update(BASES[base][1])
    return payload


def _check_bot_challenge(resp: requests.Response) -> None:
    """Levanta :class:`BotChallengeBlockedError` no 403 ``Access Denied`` da Akamai.

    Só esse formato: um 403 com outro corpo segue para o retry do
    ``HTTPScraper``. O bloqueio vale para o IP inteiro, então retentar com a
    mesma sessão só gastaria tempo.
    """
    if resp.status_code != 403:
        return
    head = resp.content[:600]
    if b"Access Denied" not in head:
        return
    match = _AKAMAI_REF_RE.search(head)
    reference = match.group(1).decode("ascii").replace("&#46;", ".") if match else None
    raise BotChallengeBlockedError("TRF3", resp.url, reference=reference)


def _check_sessao(resp: requests.Response) -> None:
    if SESSAO_EXPIRADA_PATH.lower() in resp.url.lower():
        raise RuntimeError(
            "TRF3 cjsg: o portal respondeu com sessão expirada "
            f"({resp.url}). A busca precisa ser refeita do início."
        )


_TOTAL_SELECTORS = ("section.secao-total .qtd-total",)
_TOTAL_PATTERNS = (re.compile(r"^\s*(\d[\d.]*)\s*$"),)
# Contador do primeiro item da lista, "1/591)": fallback se o resumo mudar.
_CONTAGEM_SELECTORS = ("li.acordao-retorno .contagem",)
_CONTAGEM_PATTERNS = (re.compile(r"^\s*\d+\s*/\s*(\d[\d.]*)\)\s*$"),)
_ZERO_MARKERS = ("Nenhum Resultado Encontrado",)


def cjsg_n_results(html: str) -> int | None:
    """Extrai o total de documentos da busca a partir de uma página da lista.

    Lê o resumo ``N ~ TOTAL`` (``section.secao-total``) e, se ele faltar, o
    contador ``i/TOTAL)`` do primeiro item. Página com "Nenhum Resultado
    Encontrado" vale 0. Devolve ``None`` quando nenhum formato casa.
    """
    total = extract_count_with_cascade(
        html,
        css_selectors=_TOTAL_SELECTORS,
        regex_patterns=_TOTAL_PATTERNS,
    )
    if total is not None:
        return total
    return extract_count_with_cascade(
        html,
        css_selectors=_CONTAGEM_SELECTORS,
        regex_patterns=_CONTAGEM_PATTERNS,
        zero_markers=_ZERO_MARKERS,
    )


def _paginas_pedidas(paginas: Iterable[int] | None, n_paginas: int | None) -> list[int]:
    """Resolve a lista de páginas a baixar, 1-based, na ordem pedida.

    Com ``paginas=None`` baixa todas; exige o total. Páginas além do total são
    descartadas sem requisição: o portal não tem o que devolver para elas.
    """
    if paginas is None:
        if n_paginas is None:
            raise ValueError(
                "TRF3 cjsg: não foi possível ler o total de resultados da primeira "
                "página; passe 'paginas' explicitamente."
            )
        return list(range(1, max(n_paginas, 1) + 1))
    pedidas = list(paginas)
    if n_paginas is None:
        return pedidas
    fora = [p for p in pedidas if p > max(n_paginas, 1)]
    if fora:
        logger.info("TRF3 cjsg: páginas %s além do total (%s); ignoradas.", fora, n_paginas)
    return [p for p in pedidas if p <= max(n_paginas, 1)]


def cjsg_download_manager(
    payload: dict[str, str],
    *,
    base: str,
    paginas: Iterable[int] | None,
    tamanho_pagina: int,
    request_fn: RequestFn,
    session: requests.Session,
    sleep_time: float = 1.0,
    perfil: str | None = None,
    progress: Callable[..., Iterable[int]] = tqdm,
) -> list[str]:
    """Executa uma busca e devolve o HTML das páginas pedidas da lista resumida.

    Args:
        payload: Corpo do POST, de :func:`build_cjsg_payload`.
        base: Chave de :data:`BASES`; escolhe a aba aberta no ``GET`` inicial.
        paginas: Páginas 1-based, ou ``None`` para todas.
        tamanho_pagina: Documentos por página, igual ao do ``payload``; usado
            para converter o total de documentos em total de páginas.
        request_fn: ``HTTPScraper._request_with_retry`` do client.
        session: Sessão isolada da busca (:func:`build_cjsg_session`).
        sleep_time: Pausa, em segundos, entre páginas.
        perfil: Perfil HTTP do client repassado a ``request_fn``.
        progress: Iterador com barra de progresso (``tqdm``).

    Returns:
        Lista de HTML, uma entrada por página baixada, na ordem pedida. A
        página 1 vem da resposta do próprio POST; se ela não foi pedida, é
        descartada.

    Raises:
        BotChallengeBlockedError: 403 ``Access Denied`` da Akamai.
        RuntimeError: O portal redirecionou para a página de sessão expirada.
        ValueError: ``paginas=None`` e o total de resultados não pôde ser lido.
    """
    indice = BASES[base][0]
    index_url = INDEX_URL.format(indice=indice)
    comum = {"session": session, "perfil": perfil, "on_response": _check_bot_challenge}

    request_fn("GET", index_url, **comum)
    resp = request_fn(
        "POST",
        SEARCH_URL,
        data=payload,
        headers={"Referer": index_url, "Origin": "https://web.trf3.jus.br"},
        **comum,
    )
    resp.encoding = "utf-8"
    _check_sessao(resp)
    primeira = resp.text

    total = cjsg_n_results(primeira)
    n_paginas = None if total is None else math.ceil(total / tamanho_pagina)
    pedidas = _paginas_pedidas(paginas, n_paginas)

    resultados: list[str] = []
    for pagina in progress(pedidas, desc="Baixando CJSG TRF3", disable=len(pedidas) <= 1):
        if pagina == 1:
            resultados.append(primeira)
            continue
        # Toda página além da 1 vem depois de ao menos uma requisição (o POST).
        time.sleep(sleep_time)
        page = request_fn("GET", PAGE_URL, params={"np": pagina}, **comum)
        page.encoding = "utf-8"
        _check_sessao(page)
        resultados.append(page.text)
    return resultados
