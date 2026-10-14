"""Download da busca de jurisprudência do TRF3 (``web.trf3.jus.br/jurisprudencia``).

O portal é ASP.NET MVC com estado na sessão do servidor. A sequência é fixa:

1. ``GET home/index/{n}`` abre a sessão (cookie ``ASP.NET_SessionId``) e escolhe
   a base. A base fica gravada na sessão, não no formulário: os campos do POST
   são os mesmos nas três abas.
2. ``POST Home/ResultadoTotais`` executa a busca e responde 302 para
   ``Home/ListaResumida/1?np=0``; o ``GET`` desse redirect já é a página 1 da
   lista.
3. ``GET Home/ListaResumida/2?np=N`` traz a página N da mesma busca.

Sem o passo 1 o POST cai em ``Home/SessaoExpirada``. Por isso cada chamada de
:func:`cjsg_download_manager` usa uma ``requests.Session`` própria: duas buscas
na mesma sessão disputariam o mesmo estado no servidor.

A lista resumida já traz, para cada documento, a ementa e o inteiro teor (em
blocos ocultos), então não há uma requisição por documento. O custo de uma
busca é de três requisições fixas (o ``GET`` da aba, o ``POST`` e o ``GET`` do
redirect, que traz a página 1) mais uma por página além da primeira.
"""
from __future__ import annotations

import logging
import math
import re
import time
from collections.abc import Callable, Iterable

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

from ...core.exceptions import BotChallengeBlockedError
from ...core.http import RequestFn
from ...utils.pagination import extract_count_with_cascade
from ...utils.params import normalize_paginas
from .cjsg_parse import SELETOR_DOCUMENTO
from .cjsg_schemas import InputCJSGTRF3

logger = logging.getLogger("juscraper.trf3.cjsg")

BASE_URL = "https://web.trf3.jus.br/jurisprudencia/"
INDEX_URL = BASE_URL + "home/index/{indice}"
SEARCH_URL = BASE_URL + "Home/ResultadoTotais"
PAGE_URL = BASE_URL + "Home/ListaResumida/2"
SESSAO_EXPIRADA_PATH = "Home/SessaoExpirada"
TAMANHOS_PAGINA = (10, 30, 50)

#: Nome do perfil HTTP da busca. O manager o envia em toda requisição e o
#: client declara a política com a mesma chave em ``TRF3Scraper.perfis_http``.
PERFIL_CJSG = "cjsg"

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

# Cabeçalhos de navegador. O portal fica atrás do bot manager da Akamai. Na
# medição, ``requests`` sem cabeçalhos (User-Agent ``python-requests``) ficou
# com a conexão pendurada, sem resposta; com User-Agent e Accept de navegador,
# mesmo sem os Sec-Fetch-*, a aba respondeu em 0,2 s. Os Sec-Fetch-* completam
# o perfil de navegador, sem efeito medido isoladamente.
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


# O JavaScript do formulário reescreve "1a. seção" como "1A" antes de montar o
# filtro de órgão. Medido no portal: "QUINTA TURMA - 1A" encontra documentos,
# e "QUINTA TURMA - 1A. SEÇÃO", que é o que a coluna ``orgao_julgador`` mostra
# nos acórdãos antigos, encontra zero. Mesma expressão do JS
# (``/1a\.\s+se[cç][aã]o/gi``).
_PRIMEIRA_SECAO_RE = re.compile(r"1a\.\s+se[cç][aã]o", re.IGNORECASE)


def _orgao_indexado(orgao: str | None) -> str:
    return _PRIMEIRA_SECAO_RE.sub("1A", orgao or "")


def _opcoes_orgao(html: str) -> list[tuple[str, str]]:
    """Lê as opções do dropdown ``select#orgao`` da aba: (rótulo, nome indexado).

    O rótulo é o texto exibido (``"5ª Turma"``) e o nome indexado é o
    atributo ``data-val-jef`` (``"QUINTA TURMA"``). A opção "Selecione...",
    de valor ``0``, fica de fora. Cada aba tem o seu dropdown: o das Turmas
    Recursais lista outros órgãos.
    """
    soup = BeautifulSoup(html, "html.parser")
    opcoes: list[tuple[str, str]] = []
    for opcao in soup.select("select#orgao option"):
        if str(opcao.get("value") or "").strip() in {"", "0"}:
            continue
        rotulo = opcao.get_text(" ", strip=True)
        # Todas as opções medidas têm ``data-val-jef``. Numa que não tenha, o
        # JavaScript do formulário quebraria ao montar ``hdnOrgaoJef``; o
        # rótulo nos dois campos é o que a busca mandava antes desta leitura.
        opcoes.append((rotulo, str(opcao.get("data-val-jef") or rotulo).strip()))
    return opcoes


def _chave_orgao(texto: str) -> str:
    """Forma de comparação do órgão: troca de "1a. seção", espaços e caixa.

    A troca vem antes, para que o valor da coluna nos acórdãos antigos
    (``"QUINTA TURMA - 1A. SEÇÃO"``) e o ``data-val-jef`` da opção
    (``"QUINTA TURMA - 1a. SEÇÃO"``) cheguem à mesma chave.
    """
    return " ".join(_orgao_indexado(texto).split()).casefold()


def _campos_orgao(orgao: str | None, opcoes: list[tuple[str, str]]) -> dict[str, str]:
    """Monta ``hdnOrgao`` e ``hdnOrgaoJef`` como o navegador, a partir da opção escolhida.

    O navegador grava em ``hdnOrgao`` o rótulo da opção e em ``hdnOrgaoJef``
    o nome indexado, e o servidor junta os dois com OU. Medido em 14/10/2026,
    com "medicamento" nos acórdãos: o par ``5ª Turma``/``QUINTA TURMA`` traz
    576 documentos; o rótulo nos dois campos traz 443, e o nome indexado nos
    dois, 133. ``hdnOrgaoJef`` sozinho é ignorado, e o servidor não aceita
    mais de um nome indexado no campo, por isso o texto tem que escolher uma
    opção só.

    O texto casa com o rótulo ou com o nome indexado de uma opção, sem
    diferença de caixa e de espaços (:func:`_chave_orgao`).

    Args:
        orgao: ``orgao_julgador`` do modelo.
        opcoes: Opções do dropdown da aba (:func:`_opcoes_orgao`).

    Returns:
        Os dois campos da opção que casou, nos moldes do formulário. Vazio
        sem órgão, sem opções lidas da aba, ou quando o texto não casa com
        nenhuma opção: nesse caso fica o que :func:`build_cjsg_payload`
        montou, o mesmo texto nos dois campos.

    Raises:
        ValueError: O texto casa com mais de uma opção, como o rótulo
            ``"5ª Turma"``, que no portal nomeia ``QUINTA TURMA`` e
            ``QUINTA TURMA - 1a. SEÇÃO``.
    """
    if not (orgao or "").strip():
        return {}
    if not opcoes:
        # Aba sem ``select#orgao`` é layout mudado, e não texto do usuário
        # que não casa: o mesmo texto nos dois campos ainda busca, mas perde
        # o par que o navegador manda e traz menos documentos (com
        # "medicamento", 443 para ``5ª Turma`` contra 576 do site), e um
        # rótulo ambíguo deixa de levantar erro. Por isso WARNING, e não o
        # INFO do texto sem correspondência. Levantar erro aqui derrubaria
        # toda busca com órgão por uma mudança de layout que ainda deixa o
        # filtro funcionar em parte.
        logger.warning(
            "TRF3 cjsg: o formulário da aba não trouxe o dropdown de órgão; "
            "o filtro %r vai sem a tradução do formulário e pode trazer menos "
            "resultados que o site.",
            orgao,
        )
        return {}
    chave = _chave_orgao(orgao or "")
    casadas = [op for op in opcoes if chave in {_chave_orgao(op[0]), _chave_orgao(op[1])}]
    if not casadas:
        logger.info(
            "TRF3 cjsg: o órgão %r não corresponde a nenhuma opção do formulário; "
            "o texto vai como está nos dois campos do órgão.",
            orgao,
        )
        return {}
    if len(casadas) > 1:
        nomes = ", ".join(repr(nome) for _, nome in casadas)
        raise ValueError(
            f"TRF3 cjsg: o órgão {orgao!r} é ambíguo no portal: corresponde a "
            f"{len(casadas)} opções do formulário. Passe o nome indexado da "
            f"opção desejada: {nomes}."
        )
    rotulo, nome = casadas[0]
    return {
        "hdnOrgao": _texto_campo(_orgao_indexado(rotulo), "({}).org."),
        "hdnOrgaoJef": _texto_campo(_orgao_indexado(nome), "({}).org."),
    }


def build_cjsg_payload(inp: InputCJSGTRF3) -> dict[str, str]:
    """Monta o corpo form-urlencoded do ``POST Home/ResultadoTotais``.

    Usa os campos e os moldes do formulário de pesquisa avançada, mas não
    reproduz tudo o que o JavaScript dele faz. ``magistrado``, ``classe`` e
    ``orgao`` vão como ``"0"`` (sem seleção no dropdown); o filtro de verdade
    viaja nos campos ocultos ``hdnMagistrado``, ``hdnClasse``, ``hdnOrgao`` e
    ``hdnOrgaoJef``. ``chkMostrarLista=on`` pede a lista resumida, que já traz
    ementa e inteiro teor de cada documento.

    No órgão julgador, esta função põe o texto de ``inp`` nos dois campos,
    ``hdnOrgao`` e ``hdnOrgaoJef``, depois da mesma troca de "1a. seção" por
    "1A" que o JavaScript faz. O navegador manda nesses campos o rótulo e o
    nome indexado da opção escolhida, e essa tabela é dado do portal, que
    só chega com o formulário da aba: :func:`cjsg_download_manager` lê o
    dropdown da aba e troca os dois campos pelos da opção que casa com o
    texto (:func:`_campos_orgao`). Esta função também não aplica as
    checagens do formulário (critério obrigatório, datas); as que importam
    ficam em ``validar_combinacoes``.

    O formulário tem um só par de datas (``data_inicial`` e ``data_final``) e
    o seletor ``data_tipo``. Com data de publicação em ``inp``, o par leva as
    datas de publicação e ``data_tipo`` vale ``"0"``; nos demais casos leva as
    de julgamento e vale ``"1"``, que na aba de monocráticas é a data da
    decisão. ``validar_combinacoes`` recusa os dois tipos juntos antes de a
    busca chegar aqui.

    Args:
        inp: Filtros da busca, como saem de ``apply_input_pipeline_search``.
            As datas têm que estar em ``DD/MM/AAAA``
            (``InputCJSGTRF3.BACKEND_DATE_FORMAT``): o pipeline do client as
            converte, e um modelo montado à mão (script de captura, testes)
            precisa trazê-las já nesse formato, porque esta função as copia
            sem converter. ``relator``, ``classe`` e ``orgao_julgador`` são o
            texto que o portal indexa, e não o ID do dropdown. ``base`` só
            decide as caixas de origem das monocráticas, porque a aba é
            escolhida pelo ``GET`` anterior. ``paginas`` não entra no corpo.

    Returns:
        Dicionário pronto para ``data=`` do ``requests``.
    """
    por_publicacao = bool(inp.data_publicacao_inicio or inp.data_publicacao_fim)
    data_inicial = inp.data_publicacao_inicio if por_publicacao else inp.data_julgamento_inicio
    data_final = inp.data_publicacao_fim if por_publicacao else inp.data_julgamento_fim
    orgao = _texto_campo(_orgao_indexado(inp.orgao_julgador), "({}).org.")
    payload = {
        "txtPesquisaLivre": inp.pesquisa,
        "chkAcordaos": "on",
        "chkMostrarLista": "on",
        "opcaoQtdePagina": str(inp.tamanho_pagina),
        "numero": inp.numero_processo or "",
        "magistrado": "0",
        "data_inicial": data_inicial or "",
        "data_final": data_final or "",
        "data_tipo": DATA_TIPO["publicacao" if por_publicacao else "julgamento"],
        "classe": "0",
        "orgao": "0",
        "ementa": inp.ementa or "",
        "indexacao": inp.indexacao or "",
        "hdnMagistrado": _texto_campo(inp.relator, "(({})).rel."),
        "hdnClasse": _texto_campo(inp.classe, "({}).dclas."),
        "hdnOrgao": orgao,
        "hdnOrgaoJef": orgao,
    }
    payload.update(BASES[inp.base][1])
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
_CONTAGEM_SELECTORS = (f"{SELETOR_DOCUMENTO} .contagem",)
_CONTAGEM_PATTERNS = (re.compile(r"^\s*\d+\s*/\s*(\d[\d.]*)\)\s*$"),)
_ZERO_MARKERS = ("Nenhum Resultado Encontrado",)


def _check_lista(html: str, url: str, *, total_da_busca: int | None = None) -> None:
    """Levanta ``RuntimeError`` se a página não for a lista de resultados esperada.

    O portal responde 200 também quando devolve outra coisa no lugar da lista
    (o formulário de busca, uma página de manutenção). Sem esta checagem essa
    resposta chegaria ao parser, que não acha documento nenhum e devolve o
    mesmo DataFrame vazio de uma busca sem resultados. A lista é reconhecida
    por ter ao menos um documento ou o aviso de nenhum resultado.

    O aviso só vale como lista quando combina com a busca. Com
    ``total_da_busca`` maior que zero, a página foi pedida dentro do total e
    tem que trazer documento: o aviso de nenhum resultado, nesse caso, também
    levanta. Sem o total (``None``, o caso da primeira página e o de um total
    ilegível) ou com total zero, o aviso é aceito.

    Args:
        html: Corpo da resposta.
        url: Endereço da resposta, citado na mensagem de erro.
        total_da_busca: Total de documentos lido na primeira página, para as
            páginas seguintes; ``None`` quando não se sabe.

    Raises:
        RuntimeError: A página não traz documentos nem o aviso de nenhum
            resultado, ou traz o aviso e a busca tem ``total_da_busca``
            resultados.
    """
    soup = BeautifulSoup(html, "html.parser")
    if soup.select_one(SELETOR_DOCUMENTO) is not None:
        return
    texto = soup.get_text(" ", strip=True).lower()
    if any(marcador.lower() in texto for marcador in _ZERO_MARKERS):
        if not total_da_busca:
            return
        raise RuntimeError(
            f"TRF3 cjsg: a resposta de {url} traz o aviso de nenhum resultado, "
            f"mas deveria trazer documentos, porque a busca tem {total_da_busca} "
            "resultados."
        )
    raise RuntimeError(
        f"TRF3 cjsg: a resposta de {url} não é a lista de resultados: não traz "
        "documentos nem o aviso de nenhum resultado. O portal pode estar em "
        "manutenção ou ter mudado de layout."
    )


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

    ``n_paginas=None`` só chega aqui para uma primeira página que já passou por
    :func:`_check_lista` e traz documentos, mas cujo resumo e contador não
    foram lidos. Nesse caso o pedido explícito é mantido sem corte, e cada
    página baixada passa pela mesma checagem.
    """
    if paginas is None:
        if n_paginas is None:
            raise ValueError(
                "TRF3 cjsg: a primeira página traz documentos, mas o total de "
                "resultados não pôde ser lido; passe 'paginas' explicitamente."
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
    inp: InputCJSGTRF3,
    *,
    request_fn: RequestFn,
    session: requests.Session,
    sleep_time: float = 1.0,
    progress: Callable[..., Iterable[int]] = tqdm,
) -> list[str]:
    """Executa uma busca e devolve o HTML das páginas pedidas da lista resumida.

    O modelo é a fonte única da busca: dele saem o corpo do POST
    (:func:`build_cjsg_payload`), a aba aberta no ``GET`` inicial, as páginas
    pedidas e o tamanho de página que converte o total de documentos em total
    de páginas. Assim o tamanho enviado ao portal e o usado na conta não têm
    como divergir. Com ``orgao_julgador``, o formulário devolvido pelo ``GET``
    da aba dá o par de rótulo e nome indexado que o navegador mandaria
    (:func:`_campos_orgao`), sem requisição a mais.

    Args:
        inp: Filtros da busca, como saem de ``apply_input_pipeline_search``.
            ``paginas`` é 1-based, e ``None`` baixa todas.
        request_fn: ``HTTPScraper._request_with_retry`` do client. Recebe
            ``perfil=PERFIL_CJSG`` em toda requisição.
        session: Sessão isolada da busca (:func:`build_cjsg_session`).
        sleep_time: Pausa, em segundos, entre páginas.
        progress: Iterador com barra de progresso (``tqdm``).

    Returns:
        Lista de HTML, uma entrada por página baixada, na ordem pedida. A
        página 1 vem da resposta do próprio POST; se ela não foi pedida, é
        descartada.

    Raises:
        BotChallengeBlockedError: 403 ``Access Denied`` da Akamai.
        RuntimeError: O portal redirecionou para a página de sessão expirada,
            ou respondeu 200 com uma página que não é a lista de resultados
            (formulário de busca, manutenção); vale para a primeira página e
            para as seguintes. Da página 2 em diante, também quando a página
            traz o aviso de nenhum resultado e o total lido na primeira é
            maior que zero.
        ValueError: ``orgao_julgador`` corresponde a mais de uma opção do
            dropdown da aba; ou ``paginas=None`` e a primeira página traz
            documentos, mas o total de resultados não pôde ser lido.
    """
    payload = build_cjsg_payload(inp)
    index_url = INDEX_URL.format(indice=BASES[inp.base][0])
    comum = {"session": session, "perfil": PERFIL_CJSG, "on_response": _check_bot_challenge}

    aba = request_fn("GET", index_url, **comum)
    if inp.orgao_julgador:
        aba.encoding = "utf-8"
        payload.update(_campos_orgao(inp.orgao_julgador, _opcoes_orgao(aba.text)))
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
    # Antes de ler o total: uma página que não é a lista também não tem total,
    # e o erro dela é mais específico que o de total ilegível.
    _check_lista(primeira, resp.url)

    total = cjsg_n_results(primeira)
    n_paginas = None if total is None else math.ceil(total / inp.tamanho_pagina)
    # O pipeline do client já entrega ``paginas`` como lista, range ou None; a
    # normalização só muda o inteiro de um modelo montado fora dele.
    pedidas = _paginas_pedidas(normalize_paginas(inp.paginas), n_paginas)

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
        html = page.text
        # Com o total lido, toda página que chega aqui está dentro dele
        # (``_paginas_pedidas`` cortou as demais) e tem que trazer documento.
        # Com o total ilegível, a página pode estar além do fim da busca, e o
        # aviso de nenhum resultado continua aceito.
        _check_lista(html, page.url, total_da_busca=total)
        resultados.append(html)
    return resultados
