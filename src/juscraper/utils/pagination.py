"""Cascata de seletores CSS + cascata de regex para extracao robusta de
contagem (numero de resultados ou de paginas) em paginas de tribunais.

Motivacao (refs #87): paginas de tribunais mudam markup sem aviso. Usar
regex unica em HTML cru (padrao antigo de varios scrapers) torna o
parser silenciosamente fragil. A estrategia canonica do projeto, ja
documentada para a familia eSAJ em ``cjsg_n_pags``, e tentar varios
seletores CSS em ordem ate algum casar e, no texto extraido, tentar
varias regex em ordem ate alguma achar o numero. Este modulo expoe essa
estrategia como helper generico para os tribunais nao-eSAJ.
"""
from __future__ import annotations

import logging
import math
import re
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from functools import partial
from itertools import chain, islice, pairwise
from typing import TYPE_CHECKING, Generic, NamedTuple, TypeGuard, TypeVar, overload

from bs4 import BeautifulSoup, Tag
from tqdm import tqdm

from ..core.avisos import avisar
from ..core.exceptions import ColetaParcialError

if TYPE_CHECKING:
    import pandas as pd

_Pagina = TypeVar("_Pagina")

_NUMERO_PAGINA_RE = re.compile(r"[0-9]+")


def _coerce_int(raw: str) -> int | None:
    digits = raw.replace(".", "").replace(",", "")
    return int(digits) if digits.isdigit() else None


def _extract_from_match(match: re.Match[str]) -> int | None:
    for group in match.groups():
        if group is None:
            continue
        coerced = _coerce_int(group)
        if coerced is not None:
            return coerced
    return _coerce_int(match.group(0))


class AvisoVazio(NamedTuple):
    """Aviso de busca vazia: os marcadores só valem no texto dos ``seletores``.

    Ementas e sentenças citam as frases do aviso ("nenhum documento
    encontrado nos autos"), e por isso o texto da página inteira não serve:
    o marcador é procurado só nos elementos que o portal usa para o aviso
    (``div.alert-danger`` no STM, por exemplo).

    Attributes:
        seletores: Seletores CSS do contêiner do aviso.
        marcadores: Substrings (sem diferença de maiúsculas) procuradas no
            texto de cada elemento que os seletores casam.
    """

    seletores: tuple[str, ...]
    marcadores: tuple[str, ...]


def _tem_aviso_vazio(soup: Tag, aviso: AvisoVazio | None) -> bool:
    if aviso is None:
        return False
    marcadores = [marcador.lower() for marcador in aviso.marcadores]
    textos = (
        elemento.get_text(" ", strip=True).lower()
        for seletor in aviso.seletores
        for elemento in soup.select(seletor)
    )
    return any(marcador in texto for texto in textos for marcador in marcadores)


def _collect_candidates(
    soup: Tag,
    html: str | Tag,
    css_selectors: Sequence[str],
    *,
    fallback_html: bool,
) -> list[str]:
    candidates = [
        content
        for selector in css_selectors
        for element in soup.select(selector)
        if (content := element.get_text(" ", strip=True))
    ]
    # ``str(Tag)`` serializa a árvore inteira: só quando o HTML bruto é usado.
    return candidates or ([str(html)] if fallback_html else [])


def _extract_first(
    candidates: Sequence[str],
    regex_patterns: Sequence[re.Pattern[str]],
) -> int | None:
    for candidate in candidates:
        for pattern in regex_patterns:
            match = pattern.search(candidate)
            if not match:
                continue
            value = _extract_from_match(match)
            if value is not None:
                return value
    return None


def extract_count_with_cascade(
    html: str | Tag,
    *,
    css_selectors: Sequence[str] = (),
    regex_patterns: Sequence[re.Pattern[str]] = (),
    aviso_vazio: AvisoVazio | None = None,
    fallback_html: bool = False,
) -> int | None:
    r"""Extrai uma contagem (resultados ou paginas) usando cascata.

    O retorno ``None`` quer dizer markup não reconhecido. O caller deve
    passá-lo a :func:`resolve_total_pages` ou levantar: assumir 1 página ou
    0 resultados faz o download parar na primeira página sem aviso.

    A ordem é: seletores e regex; ``aviso_vazio``; ``None``. O aviso de busca
    vazia só vale quando nenhuma contagem foi achada, e só dentro dos
    seletores dele, porque ementas e sentenças citam essas frases ("nenhum
    documento encontrado nos autos") e uma contagem 0 faz o download parar na
    primeira página sem aviso.

    Args:
        html: HTML bruto da primeira pagina de resultados, ou o trecho ja
            parseado (``Tag``) onde a contagem esta, como o ``div`` de uma
            tabela, sem parsear de novo. Com uma ``Tag``, a
            cascata inteira (seletores, regex, ``fallback_html`` e
            ``aviso_vazio``) olha so o trecho.
        css_selectors: Seletores CSS tentados em ordem. Para cada um,
            ``soup.select(selector)`` produz elementos cujo texto vira
            candidato. Se nenhum seletor casa elemento com texto (ou se a
            lista e vazia), a cascata nao acha contagem, salvo com
            ``fallback_html=True``.
        regex_patterns: Regex tentadas em ordem para cada texto candidato.
            Se a regex tem grupos, retorna o primeiro grupo numerico
            valido; caso contrario tenta ``group(0)``. Vence o primeiro
            match valido na ordem da cascata (candidato, depois regex).
        aviso_vazio: Contêiner e frases do aviso de busca vazia
            (:class:`AvisoVazio`), consultado quando a cascata nao acha
            contagem; se algum marcador aparece no texto de algum elemento
            dos seletores do aviso, o util retorna ``0``. Fora desses
            elementos o marcador nao conta. Com uma ``Tag``, os seletores
            casam os descendentes dela, como ``css_selectors``.
        fallback_html: Se ``True``, as regex rodam no HTML bruto quando
            nenhum seletor casa elemento com texto. Default ``False``: o
            HTML inteiro traz as ementas, e uma regex como ``de\\s+(\\d+)\\)``
            casa "(fevereiro de 2009)" nelas. So quando todas as regex exigem
            as palavras do rotulo do resumo ("Documentos encontrados: N"),
            que tambem nao podem casar com o aviso de busca vazia, porque a
            regex roda antes de ``aviso_vazio``.

    Returns:
        ``int`` extraido; ``0`` quando a cascata nao acha contagem e o
            ``aviso_vazio`` aparece; ``None`` nos demais casos.
    """
    soup = html if isinstance(html, Tag) else BeautifulSoup(html, "html.parser")
    candidates = _collect_candidates(soup, html, css_selectors, fallback_html=fallback_html)
    value = _extract_first(candidates, regex_patterns)
    if value is not None:
        return value
    if _tem_aviso_vazio(soup, aviso_vazio):
        return 0
    return None


def parse_page_number(valor: str, *, tribunal: str, origem: str) -> int:
    """Converte o número de página lido de um link; exige dígitos ASCII e valor >= 1.

    Só ``[0-9]``: ``str.isdigit`` aceita ``²``, que ``int()`` recusa com uma
    mensagem que não diz de onde veio, e ``str.isdecimal`` aceita dígitos de
    largura total, que nenhum portal gera. ``0`` passaria no teste de dígito
    e viraria total 0, e o download pararia na primeira página sem erro.

    Raises:
        ValueError: Quando ``valor`` não é inteiro >= 1 em dígitos ASCII.
    """
    if not _NUMERO_PAGINA_RE.fullmatch(valor) or int(valor) < 1:
        raise ValueError(f"{tribunal}: {origem} sem número de página válido (inteiro >= 1): {valor!r}")
    return int(valor)


def resolve_total_pages(
    n_resultados: int | None,
    *,
    resultados_por_pagina: int,
    totais_links: Iterable[int] = (),
    tribunal: str,
) -> int:
    """Calcula o total de páginas pela contagem de resultados e confere com os links.

    A contagem publicada na página (``N registros encontrados``) é a fonte do
    total, e não o link de última página: o link some ou muda de contêiner
    quando o tribunal troca o tema do paginador, e o maior número visível sem
    ele é o fim da janela de páginas, não o total. ``totais_links`` traz o
    que os links de última página apontam (1 para link desativado); cada
    valor precisa bater com a conta, e qualquer divergência (link com
    ``page=1`` numa busca de várias páginas, "Última" desativada com "Próxima"
    ativa, tamanho de página errado no payload) levanta em vez de escolher um
    lado. Zero resultados dá 1 página: o caller já tem a primeira.

    Raises:
        ValueError: Quando ``n_resultados`` é ``None`` (a página não traz a
            contagem, por exemplo página de erro ou markup novo) ou quando
            algum link aponta para total diferente do calculado.
    """
    if n_resultados is None:
        raise ValueError(
            f"{tribunal}: a página lida não traz a contagem de resultados; "
            "o total de páginas não pode ser determinado sem estimar."
        )
    total = max(1, math.ceil(n_resultados / resultados_por_pagina))
    divergentes = sorted(set(totais_links) - {total})
    if divergentes:
        raise ValueError(
            f"{tribunal}: o link de última página aponta {divergentes}, mas {n_resultados} resultados "
            f"em páginas de {resultados_por_pagina} dão {total} página(s)."
        )
    return total


_PAGINAS_FORA_NO_AVISO = 5


@dataclass(frozen=True, slots=True, repr=False)
class Paginas:
    """A seleção ``paginas`` normalizada, opaca: só os helpers deste módulo a leem.

    É o que :attr:`juscraper.schemas.PaginasMixin.paginas_normalizadas` devolve
    (``None`` continua valendo todas as páginas). Não tem ``__iter__``,
    ``__len__``, índice nem ``in``: o laço, ``max``, ``list`` ou ``.start``
    escrito à mão no raspador é erro no mypy e ``TypeError`` ao rodar, e os
    contratos, que passam pela API pública com ``paginas`` explícito, o pegam.
    O contrato comum (página repetida uma vez só, página além do total no log
    do tribunal, ``range`` cortado sem ser percorrido, passo respeitado) fica
    nos helpers: :func:`baixar_paginas_pedidas`, :func:`paginas_no_intervalo`,
    :func:`menor_pagina`, :func:`maior_pagina`, :func:`paginas_unicas` e
    :func:`pagina_pedida`. Caso novo entra aqui, não no raspador.
    """

    _pedidas: range | tuple[int, ...]

    def __repr__(self) -> str:
        """``Paginas([3, 5])`` ou ``Paginas(range(1, 4))``, como a seleção foi pedida."""
        pedidas = self._pedidas
        return f"Paginas({pedidas if isinstance(pedidas, range) else list(pedidas)})"


SelecaoBruta = Paginas | range | list[int] | tuple[int, ...] | int | None


@overload
def selecao_de_paginas(paginas: None) -> None: ...


@overload
def selecao_de_paginas(paginas: Paginas | range | list[int] | tuple[int, ...] | int) -> Paginas: ...


def selecao_de_paginas(paginas: SelecaoBruta) -> Paginas | None:
    """``paginas`` como :class:`Paginas`: o inteiro ``n`` vira ``range(1, n + 1)``; ``None`` fica ``None``.

    Não valida (página >= 1, seleção não vazia): isso é do ``PaginasMixin``.
    """
    if paginas is None or isinstance(paginas, Paginas):
        return paginas
    if isinstance(paginas, int):
        return Paginas(range(1, paginas + 1))
    return Paginas(paginas if isinstance(paginas, range) else tuple(paginas))


def _pedidas(paginas: SelecaoBruta) -> range | tuple[int, ...] | None:
    """As páginas guardadas em ``paginas``.

    Aceita também ``list``/``range``/``int``, para a função de download chamada
    direto, sem passar pelo schema (testes de unidade).
    """
    selecao = selecao_de_paginas(paginas)
    # O módulo dono do tipo é o único que lê o interior.
    return None if selecao is None else selecao._pedidas  # noqa: SLF001  # pylint: disable=protected-access


def _pedidas_obrigatorias(paginas: Paginas, helper: str) -> range | tuple[int, ...]:
    """As páginas de uma seleção que não pode ser ``None`` (todas)."""
    pedidas = _pedidas(paginas)
    if pedidas is None:
        raise TypeError(f"{helper}: paginas=None não lista páginas; trate o None antes.")
    return pedidas


def _unicas(pedidas: range | tuple[int, ...]) -> Sequence[int]:
    """Sem repetição, na ordem pedida; o ``range`` volta como veio, porque não repete."""
    return pedidas if isinstance(pedidas, range) else list(dict.fromkeys(pedidas))


def _range_crescente(paginas: range | tuple[int, ...]) -> TypeGuard[range]:
    """``range`` crescente, cortado pelos limites sem ser percorrido."""
    return isinstance(paginas, range) and paginas.step > 0


def menor_pagina(paginas: Paginas | None) -> int:
    """A página a pedir primeiro quando o total só vem numa resposta: a menor pedida, ou 1 com ``None``.

    Se ela passa do total, as demais também passam, e
    :func:`paginas_no_intervalo` descarta todas sem novo pedido. ``range``
    crescente não é percorrido.
    """
    pedidas = _pedidas(paginas)
    if pedidas is None:
        return 1
    if _range_crescente(pedidas):
        return pedidas.start
    return min(pedidas)


def maior_pagina(paginas: Paginas) -> int:
    """A maior página pedida, sem percorrer o ``range`` crescente.

    Para o laço que precisa saber até onde ir antes de ler o total: o cursor
    que só avança (PDPJ, DataJud) e a validação do payload antes da primeira
    requisição (STF).
    """
    pedidas = _pedidas_obrigatorias(paginas, "maior_pagina")
    if _range_crescente(pedidas):
        return pedidas[-1]
    return max(pedidas)


def paginas_unicas(paginas: Paginas) -> Sequence[int]:
    """As páginas pedidas na ordem pedida, cada uma uma vez só, na posição em que aparece primeiro.

    Para o portal que não informa o total e por isso não corta a seleção com
    :func:`paginas_no_intervalo` (TJAP), e para guardar a seleção num
    checkpoint (STF). O ``range`` volta como veio, sem ser percorrido, porque
    não repete página.
    """
    return _unicas(_pedidas_obrigatorias(paginas, "paginas_unicas"))


def pagina_pedida(paginas: Paginas | None, pagina: int) -> bool:
    """Se ``pagina`` está na seleção (``None``: todas estão).

    Para o cursor que só avança (DataJud, PDPJ), que percorre as páginas de
    1 até :func:`maior_pagina` e guarda só as pedidas.
    """
    pedidas = _pedidas(paginas)
    return pedidas is None or pagina in pedidas


def paginas_no_intervalo(paginas: Paginas | None, n_pags: int, *, tribunal: str) -> list[int]:
    """As páginas pedidas dentro de ``1..n_pags``, na ordem pedida e sem repetição; as demais vão para o log.

    ``paginas=None`` vale todas, de 1 a ``n_pags``. Uma página repetida é
    baixada uma vez só, na posição em que aparece primeiro. A busca vazia
    (``n_pags=0``) não tem página a baixar nem a avisar.

    As páginas de fora saem num aviso só, no logger do tribunal
    (``juscraper.<sigla>``), onde já saía antes de o filtro virar helper:
    ``paginas=1000`` numa busca de 7 páginas gera uma linha, não 993.
    """
    pedidas = _pedidas(paginas)
    if pedidas is None:
        return list(range(1, n_pags + 1))
    if n_pags == 0:
        return []
    if _range_crescente(pedidas):
        validas, primeiras_fora, n_fora = _range_no_intervalo(pedidas, n_pags)
    else:
        unicas = _unicas(pedidas)
        validas = [pagina for pagina in unicas if 1 <= pagina <= n_pags]
        fora = [pagina for pagina in unicas if not 1 <= pagina <= n_pags]
        primeiras_fora, n_fora = fora[:_PAGINAS_FORA_NO_AVISO], len(fora)
    if n_fora:
        _avisar_paginas_fora(primeiras_fora, n_fora, n_pags, tribunal)
    return validas


def recusar_alem_do_teto(paginas: Paginas | None, teto: int, *, tribunal: str) -> None:
    """Levanta se alguma página pedida passa de ``teto``, a última que o portal entrega.

    É o significado único de "página além do teto do portal" (TJBA, TJMT,
    TJPB, TJRO e Falcão): erro antes de qualquer requisição, porque o portal
    responde com erro ou repete a última página. ``range`` crescente não é
    percorrido. Com ``paginas=None``, quem baixa avisa e para no teto (ver o
    ``teto`` de :func:`baixar_paginas_pedidas`).

    Raises:
        ValueError: Quando a maior página pedida passa de ``teto``.
    """
    if paginas is not None and (maior := maior_pagina(paginas)) > teto:
        raise ValueError(
            f"{tribunal}: o portal só entrega as {teto} primeiras páginas de uma busca, e foi pedida "
            f"a página {maior}. Restrinja a busca para alcançar os demais resultados."
        )


def _avisar_teto(paginas: Paginas | None, n_pags: int, teto: int, *, tribunal: str) -> int:
    """``n_pags`` limitado a ``teto``; com ``paginas=None`` e total acima do teto, ``UserWarning``.

    Avisos:
        ``UserWarning``: com ``paginas=None``, quando o total passa de
        ``teto``, porque o download para nele.
    """
    if n_pags <= teto:
        return n_pags
    if paginas is None:
        avisar(
            f"{tribunal}: a busca tem {n_pags} páginas, e o portal só entrega as {teto} primeiras; "
            "as demais não foram baixadas. Restrinja a busca para alcançá-las."
        )
    return teto


def mensagem_de_coleta_parcial(tribunal: str, faltando: Sequence[int], n_baixadas: int, exc: Exception) -> str:
    """O texto padrão do ``ColetaParcialError`` de :func:`baixar_paginas_pedidas`.

    Diz a página que falhou, quantas vieram e as que faltam num texto que vale
    como ``paginas=`` (:func:`descrever_paginas`). O raspador que precisa de
    mais (o bloqueio do WAF no TJTO) acrescenta ao fim.
    """
    return (
        f"{tribunal}: a página {faltando[0]} falhou ({exc!r}), e a busca parou. "
        f"As {n_baixadas} página(s) baixadas antes estão, já lidas, no atributo .resultado do erro; "
        f"faltam as páginas {descrever_paginas(faltando)}, que podem ser pedidas de novo com paginas=."
    )


def baixar_paginas_pedidas(  # noqa: PLR0913 - laço comum; ganchos opcionais de página fixa, teto e coleta parcial
    paginas: Paginas | None,
    buscar: Callable[[int], _Pagina],
    contar_paginas: Callable[[_Pagina], int],
    *,
    tribunal: str,
    sleep_time: float = 0.0,
    primeira: int | None = None,
    teto: int | None = None,
    ler_parcial: Callable[[list[_Pagina]], pd.DataFrame] | None = None,
    mensagem_parcial: Callable[[list[int], int, Exception], str] | None = None,
) -> list[_Pagina]:
    """Baixa as ``paginas`` (1-based) de uma busca: o laço de páginas comum dos raspadores.

    A primeira requisição é ``primeira`` ou, sem ela, a menor página pedida;
    ``contar_paginas`` lê nela o total. As demais saem na ordem pedida, uma vez
    cada, com ``sleep_time`` antes de cada requisição, e as além do total vão
    para o log, sem requisição (ver :func:`paginas_no_intervalo`). O retorno
    traz só as páginas pedidas, na ordem pedida. Toda resposta, inclusive a
    primeira, sai de ``buscar``: é ali que entra a conferência de cada página
    antes de ela ir para o resultado.

    Args:
        paginas: A seleção; ``None`` baixa todas.
        buscar: Baixa uma página (1-based).
        contar_paginas: Lê o total de páginas na resposta da primeira requisição.
        tribunal: Sigla, para o log, a barra de progresso e as mensagens.
        sleep_time: Segundos de espera antes de cada requisição depois da primeira.
        primeira: A página pedida primeiro, mesmo fora da seleção, para o
            portal que abre a busca nela (a página 1 no TJMG, que precisa do
            total para pedir as demais). Ela só entra no retorno se foi pedida.
        teto: A última página que o portal entrega. A página pedida além dela
            levanta ``ValueError`` antes de qualquer requisição
            (:func:`recusar_alem_do_teto`); com ``paginas=None`` e total
            acima do teto, ``UserWarning`` e o download para nele.
        ler_parcial: Lê as páginas baixadas num DataFrame. Com ele, a falha de
            ``buscar`` depois de alguma página pedida já baixada levanta
            :class:`~juscraper.core.exceptions.ColetaParcialError`. Sem ele,
            ou sem página pedida baixada, a falha sobe como veio.
        mensagem_parcial: ``mensagem_parcial(faltando, n_baixadas, exc)``, o
            texto do ``ColetaParcialError``; o padrão é
            :func:`mensagem_de_coleta_parcial`.

    Raises:
        ColetaParcialError: Com ``ler_parcial``, quando uma página falha depois
            de outra pedida já baixada. ``resultado`` traz as baixadas, lidas
            por ``ler_parcial`` na ordem pedida (a da primeira requisição, se
            ela vinha depois da que falhou, entra no fim); ``falhas`` tem um
            item ``(None, None, exc)``; ``__cause__`` é a falha.
        ValueError: Com ``teto``, quando a maior página pedida passa dele.
        Exception: A falha de ``buscar``, como veio, na primeira requisição,
            sem ``ler_parcial`` ou sem página pedida baixada.
    """
    if teto is not None:
        recusar_alem_do_teto(paginas, teto, tribunal=tribunal)
    inicial = menor_pagina(paginas) if primeira is None else primeira
    first = buscar(inicial)
    n_pags = contar_paginas(first)
    if teto is not None:
        n_pags = _avisar_teto(paginas, n_pags, teto, tribunal=tribunal)
    validas = paginas_no_intervalo(paginas, n_pags, tribunal=tribunal)
    parcial = _Parcial(mensagem_parcial or partial(mensagem_de_coleta_parcial, tribunal), ler_parcial, inicial, first)
    resultados: list[_Pagina] = []
    for posicao, pagina in enumerate(tqdm(validas, desc=f"Baixando páginas {tribunal}")):
        if pagina == inicial:
            resultados.append(first)
            continue
        if sleep_time:
            time.sleep(sleep_time)
        try:
            resultados.append(buscar(pagina))
        except Exception as exc:  # vai para ColetaParcialError, se houver o que guardar
            parcial.levantar(resultados, validas[posicao:], exc)
            raise
    return resultados


@dataclass(frozen=True)
class _Parcial(Generic[_Pagina]):
    """A coleta parcial de :func:`baixar_paginas_pedidas`: a página da primeira requisição e os ganchos."""

    mensagem: Callable[[list[int], int, Exception], str]
    ler: Callable[[list[_Pagina]], pd.DataFrame] | None
    inicial: int
    first: _Pagina

    def levantar(self, resultados: list[_Pagina], restantes: list[int], exc: Exception) -> None:
        """Levanta o ``ColetaParcialError`` da falha da página ``restantes[0]``, se houver o que guardar.

        A página da primeira requisição, se ainda viria em ``restantes``, entra
        no fim das baixadas e sai das que faltam. Sem ``ler`` ou sem página
        baixada, volta sem levantar, e quem chamou relança ``exc``.
        """
        baixadas = [*resultados, self.first] if self.inicial in restantes else resultados
        if self.ler is None or not baixadas:
            return
        faltando = [pagina for pagina in restantes if pagina != self.inicial]
        mensagem = self.mensagem(faltando, len(baixadas), exc)
        raise ColetaParcialError(mensagem, resultado=self.ler(baixadas), falhas=[(None, None, exc)]) from exc


def descrever_paginas(paginas: Sequence[int]) -> str:
    """Páginas para uma mensagem, num texto que vale como ``paginas=``.

    A sequência crescente sem saltos de três páginas ou mais sai
    ``"range(2, 8241)"``; as demais saem como lista, ``"[2, 5, 9]"``. Usado na
    mensagem do ``ColetaParcialError`` dos raspadores paginados, em que
    ``paginas=None`` pode deixar milhares de páginas por baixar.
    """
    contiguas = (
        len(paginas) > 2
        and paginas[-1] - paginas[0] == len(paginas) - 1
        and all(seguinte - pagina == 1 for pagina, seguinte in pairwise(paginas))
    )
    return f"range({paginas[0]}, {paginas[-1] + 1})" if contiguas else str(list(paginas))


def _avisar_paginas_fora(primeiras: list[int], n_fora: int, n_pags: int, tribunal: str) -> None:
    """Um aviso só com as primeiras páginas fora de ``1..n_pags`` e quantas mais."""
    listadas = ", ".join(str(pagina) for pagina in primeiras)
    if n_fora > len(primeiras):
        listadas += f" e mais {n_fora - len(primeiras)}"
    rotulo = "página" if n_fora == 1 else "páginas"
    logging.getLogger(f"juscraper.{tribunal.lower()}").warning(
        "%s: %s %s fora do intervalo 1-%s", tribunal, rotulo, listadas, n_pags
    )


def _range_no_intervalo(paginas: range, n_pags: int) -> tuple[list[int], list[int], int]:
    """Corta um ``range`` crescente em ``1..n_pags`` sem percorrê-lo, como o ``PaginasMixin``.

    Devolve as páginas dentro, as primeiras de fora (para o aviso) e quantas
    ficaram de fora: ``paginas=10**7`` não custa mais que ``paginas=10``.
    """
    abaixo = len(range(paginas.start, min(paginas.stop, 1), paginas.step))
    ate_o_total = len(range(paginas.start, min(paginas.stop, n_pags + 1), paginas.step))
    validas = list(paginas[abaixo:ate_o_total])
    primeiras_fora = list(islice(chain(paginas[:abaixo], paginas[ate_o_total:]), _PAGINAS_FORA_NO_AVISO))
    return validas, primeiras_fora, len(paginas) - len(validas)
