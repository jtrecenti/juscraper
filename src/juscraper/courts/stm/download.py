"""Download das páginas da busca de jurisprudência do STM."""
from __future__ import annotations

import re

from collections.abc import Callable, Iterable, Mapping
from itertools import pairwise
from typing import Any

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

# O mesmo para a aba de processos (``search_filter_option=feitos``).
_FILTROS_DE_PROCESSOS = {
    "cjm": "fq_cjm",
    "orgao": "fq_orgao",
    "conselho": "fq_conselho",
    "situacao": "fq_situacao",
    "classe": "fq_classe",
    "assunto": "fq_assunto_pesquisa",
}

# Pesquisa avançada do portal, a única que filtra por intervalo de datas. O
# formulário monta a consulta no navegador (``processAdvsearch``, em
# ``js/util.js``) e a manda pronta em ``q``.
# Filtro de data do método público -> campo de data da consulta avançada.
_CAMPOS_DE_DATA = {"data_julgamento": "data_decisao", "data_publicacao": "data_publicacao"}
_PONTUACAO_DO_NUMERO = re.compile(r"[.\-/]")
# Operadores da busca simples -> os da consulta avançada.
_OPERADORES = {"E": "AND", "OU": "OR", "NÃO": "NOT"}
_BINARIOS = frozenset({"AND", "OR"})
# Depois destes, a expressão ainda espera um termo.
_SEM_TERMO_ANTES = _BINARIOS | {"NOT", "("}
# Pedaços de ``pesquisa``: expressão entre aspas (com a distância ``~n``, se
# houver), parêntese ou palavra.
_PEDACOS = re.compile(r'"[^"]*"(?:~\d+)?|[()]|[^\s()"]+')
# Palavra com curinga: vai sem aspas, e por isso só com o que a consulta não lê como sintaxe.
_PALAVRA_COM_CURINGA = re.compile(r"[\w*?][\w*?.\-]*")

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


def _operando(pedaco: str, pesquisa: str) -> str:
    """Um pedaço de ``pesquisa`` que não é operador, como vai na consulta avançada."""
    if pedaco in ("(", ")") or pedaco.startswith('"'):
        return pedaco
    if "*" not in pedaco and "?" not in pedaco:
        return f'"{pedaco}"'
    if not _PALAVRA_COM_CURINGA.fullmatch(pedaco):
        raise ValueError(
            "STM: com filtro de data, palavra com curinga ('*' ou '?') aceita só letras, dígitos e, depois do "
            f"começo, ponto e hífen (recebido: {pedaco!r}, em {pesquisa!r})."
        )
    return pedaco


_SEM_PAR = "precisa ter os parênteses em pares"


def _defeito_dos_grupos(partes: list[str]) -> str | None:
    """Confere os pares de parênteses e a mistura de ``AND`` com ``OR`` dentro de cada um."""
    # Operadores binários de cada grupo de parênteses ainda aberto; o primeiro é a expressão toda.
    grupos: list[set[str]] = [set()]
    for parte in partes:
        if parte == "(":
            grupos.append(set())
        elif parte == ")":
            grupos.pop()
            if not grupos:
                return _SEM_PAR
        elif parte in _BINARIOS:
            grupos[-1].add(parte)
            if len(grupos[-1]) > 1:
                return (
                    "precisa de parênteses que digam a ordem onde E (ou termos seguidos) e OU se misturam, como em "
                    "'(furto roubo) OU peculato'"
                )
    return None if len(grupos) == 1 else _SEM_PAR


def _defeito_da_expressao(partes: list[str]) -> str | None:
    """Diz por que a expressão não vai para a consulta; ``None`` quando ela está em ordem."""
    for anterior, atual in pairwise(["(", *partes, ")"]):
        if (atual in _BINARIOS or atual == ")") and anterior in _SEM_TERMO_ANTES:
            return "precisa de um termo de cada lado dos operadores E e OU, depois do NÃO e dentro dos parênteses"
        if atual == "NOT" and anterior != "AND":
            return "só aceita o NÃO depois de um termo (como em 'furto NÃO roubo'), para excluir dele o seguinte"
    return _defeito_dos_grupos(partes)


def _expressao_avancada(termo: str, pesquisa: str) -> str:
    """Traduz a sintaxe da busca simples para a da consulta avançada.

    ``E``, ``OU`` e ``NÃO`` (em qualquer caixa) viram ``AND``, ``OR`` e
    ``NOT``; entre dois termos sem operador entra ``AND``, o padrão da busca
    simples. O ``NÃO`` só vale depois de um termo, e ``E`` e ``OU`` no mesmo
    grupo pedem parênteses: fora disso, a consulta avançada não lê a expressão
    como a busca simples. Palavra sem curinga vai entre aspas, como o formulário do portal
    a manda; expressão entre aspas, parênteses e palavra com curinga seguem
    como vieram.
    """
    if "\\" in termo or termo.count('"') % 2:
        raise ValueError(
            "STM: com filtro de data, 'pesquisa' não pode ter barra invertida nem aspas sem par "
            f"(recebido: {pesquisa!r})."
        )
    partes: list[str] = []
    for pedaco in _PEDACOS.findall(termo):
        operador = _OPERADORES.get(pedaco.upper())
        abre_termo = operador in (None, "NOT") and pedaco != ")"
        if abre_termo and partes and partes[-1] not in _SEM_TERMO_ANTES:
            partes.append("AND")
        partes.append(operador or _operando(pedaco, pesquisa))
    if defeito := _defeito_da_expressao(partes):
        raise ValueError(f"STM: com filtro de data, 'pesquisa' {defeito} (recebido: {pesquisa!r}).")
    # Espaço entre as partes, menos por dentro dos parênteses.
    expressao = "".join(
        parte if parte == ")" or anterior == "(" else f" {parte}"
        for anterior, parte in pairwise(["(", *partes])
    )
    return expressao if len(partes) == 1 else f"({expressao})"


def _clausula_do_termo(pesquisa: str, campo: str) -> str | None:
    """Cláusula do termo na consulta avançada; ``None`` quando não há termo."""
    termo = pesquisa.strip()
    sem_aspas = termo.strip('" ')
    if not sem_aspas:
        return None
    if campo == "tudo":
        raise ValueError(
            "STM: campo='tudo' não combina com filtro de data. A pesquisa avançada do portal, a única que filtra "
            "por intervalo, não tem a opção 'Todos os Campos'; escolha outro campo ou tire as datas."
        )
    if campo == "numero":
        digitos = _PONTUACAO_DO_NUMERO.sub("", sem_aspas)
        if not digitos.isdigit():
            raise ValueError(
                "STM: com filtro de data, 'pesquisa' em campo='numero' aceita só dígitos e a pontuação do número "
                f"do processo (recebido: {pesquisa!r})."
            )
        return f"(numero_processo:*{digitos}*)"
    return f"({campo}:{_expressao_avancada(termo, pesquisa)})"


def montar_consulta_avancada(pesquisa: str, campo: str, datas: Mapping[str, str | None]) -> str | None:
    """Monta a consulta da pesquisa avançada do STM; ``None`` quando não há filtro de data.

    Segue o que o formulário do portal envia: o termo no campo escolhido,
    ``(ementa:"deserção")``, e cada intervalo como
    ``(data_decisao:[2024-01-01T00:00:00.000Z TO 2024-01-31T23:59:59.000Z])``,
    ligados por ``AND``. Termo com operador ou mais de uma palavra vai
    traduzido por :func:`_expressao_avancada`:
    ``(ementa:("furto" OR "roubo"))``. ``datas`` traz ``data_julgamento_inicio/fim`` e
    ``data_publicacao_inicio/fim`` em ``AAAA-MM-DD``; o lado que falta num
    intervalo vai como ``*``. Sem termo, a consulta fica só com os intervalos.

    Raises:
        ValueError: Quando o termo não cabe na consulta: barra invertida,
            aspas ou parênteses sem par, operador sem termo, ``NÃO`` sem termo
            antes, ``E`` e ``OU`` misturados sem parênteses, curinga em
            palavra com outro símbolo, ``campo="tudo"`` ou, em
            ``campo="numero"``, algo além do número do processo.
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


def baixar_paginas_da_busca(
    paginas: Iterable[int] | None,
    montar_params: Callable[[int], dict[str, str]],
    *,
    request_fn: RequestFn,
    perfil: str,
    sleep_time: float = 1.0,
) -> list[str]:
    """Baixa as páginas de uma busca do portal, de jurisprudência ou de processos.

    ``montar_params`` dá a query string de cada página.

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
            "GET", BASE_URL, params=montar_params(pagina), perfil=perfil, on_response=conferir_bloqueio
        )
        resp.encoding = "utf-8"
        html = resp.text
        # ``primeira`` é conferida por ``cjsg_n_pags``. As demais só são
        # pedidas dentro do total: sem contador, não são de resultados.
        if pagina != primeira and not cjsg_n_resultados(html):
            raise ValueError(f"STM: a página {pagina} da busca veio sem o contador de documentos.")
        return html

    return baixar_paginas_pedidas(paginas, buscar, cjsg_n_pags, tribunal="STM", sleep_time=sleep_time)


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
    return baixar_paginas_da_busca(
        paginas,
        lambda pagina: build_cjsg_params(pesquisa, pagina, **busca),
        request_fn=request_fn,
        perfil="cjsg",
        sleep_time=sleep_time,
    )


def build_processos_params(pesquisa: str, pagina: int = 1, **filtros: str | None) -> dict[str, str]:
    """Monta a query string da busca de processos do STM.

    Repete o que o portal envia. Com ``pesquisa``, é a busca simples por
    número do processo; sem ela, a pesquisa avançada com a consulta vazia, que
    lista o que os filtros selecionam. ``filtros`` aceita ``cjm``, ``orgao``,
    ``conselho``, ``situacao``, ``classe`` e ``assunto``; ``None`` ou vazio
    não entra na query.
    """
    params = {"search_filter_option": "feitos"}
    if pesquisa:
        params |= {"search_filter": "numero", "search_input": pesquisa, "q": pesquisa, "q_or": pesquisa}
    else:
        params |= {"search_filter": "busca_avancada", "q": "", "q_or": ""}
    params |= {"start": str((pagina - 1) * RESULTS_PER_PAGE), "rows": str(RESULTS_PER_PAGE)}
    for nome, valor in filtros.items():
        if valor:
            params[_FILTROS_DE_PROCESSOS[nome]] = valor
    return params


def processos_download_manager(
    pesquisa: str,
    paginas: Iterable[int] | None = None,
    *,
    request_fn: RequestFn,
    sleep_time: float = 1.0,
    **filtros: str | None,
) -> list[str]:
    """Baixa as páginas de resultados da busca de processos do STM.

    Raises:
        BotChallengeBlockedError: Quando o WAF recusa a requisição.
        ValueError: Quando a primeira página pedida não traz o contador de
            documentos nem o aviso de busca vazia, ou quando uma das seguintes
            vem sem documentos.

    Returns:
        O HTML de cada página, na ordem pedida.
    """
    return baixar_paginas_da_busca(
        paginas,
        lambda pagina: build_processos_params(pesquisa, pagina, **filtros),
        request_fn=request_fn,
        perfil="processos",
        sleep_time=sleep_time,
    )
