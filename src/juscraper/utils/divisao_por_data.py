"""Divisão de uma busca em janelas de data quando o portal corta os resultados num teto."""
from __future__ import annotations

import math
import time
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Generic, TypeVar

import pandas as pd
from tqdm import tqdm

from juscraper.core.avisos import avisar
from juscraper.core.exceptions import ColetaParcialError

_Pagina = TypeVar("_Pagina")
# Início e fim inclusivos e, na janela que fechou os limites abertos, o total da busca original.
_Janela = tuple[date | None, date | None, int | None]


@dataclass(frozen=True)
class BuscaComTeto(Generic[_Pagina]):
    """O que :func:`baixar_dividindo_por_data` precisa saber de uma busca e do portal que a corta.

    Attributes:
        tribunal: Sigla, para os avisos e a barra de progresso.
        rotulo: Nome do filtro de data que divide a busca, sem sufixo (``"data_julgamento"``).
        teto: Quantos resultados o portal entrega de uma busca.
        por_pagina: Resultados por página.
        piso: Início das janelas quando a busca não tem data inicial.
        buscar: ``buscar(inicio, fim, pagina)`` pede a página 1-based da busca
            restrita à janela. As datas vão em ``AAAA-MM-DD``, com os dois
            limites inclusivos; ``None`` é o limite que quem chamou deixou
            aberto, e só aparece na busca original.
        contar_resultados: Lê numa página o total de resultados da busca.
        itens: A lista, mutável, dos resultados de uma página.
        chave: O identificador estável de um resultado.
        parse: Transforma páginas em DataFrame, para o resultado parcial.
        sleep_time: Segundos de espera entre requisições.
    """

    tribunal: str
    rotulo: str
    teto: int
    por_pagina: int
    piso: date
    buscar: Callable[[str | None, str | None, int], _Pagina]
    contar_resultados: Callable[[_Pagina], int]
    itens: Callable[[_Pagina], list]
    chave: Callable[[Any], Hashable]
    parse: Callable[[list[_Pagina]], pd.DataFrame]
    sleep_time: float = 0.0


def baixar_dividindo_por_data(
    busca: BuscaComTeto[_Pagina], inicio: str | None, fim: str | None
) -> list[_Pagina]:
    """Baixa todas as páginas de uma busca, dividindo-a por data quando ela passa do teto do portal.

    Para o portal que só entrega os ``busca.teto`` primeiros resultados e
    informa o total inteiro em toda página (10.000 no TJBA e no TJRO). A
    primeira página da busca, pedida com ``inicio`` e ``fim`` como vieram
    (``AAAA-MM-DD`` ou ``None``), diz o total. Se ele cabe no teto, as demais
    páginas saem como numa busca comum. Se não cabe, a janela de data é
    partida ao meio e cada metade passa pelo mesmo teste, até caber; a divisão
    segue a contagem que o portal informa, não um tamanho fixo de janela.

    * Ao dividir, o limite aberto vira ``busca.piso`` (início) ou a data de
      hoje (fim). Se a janela fechada tem menos resultados que a busca
      original, há registro sem a data do filtro ou fora desse intervalo: ele
      não entra em janela nenhuma, e um ``UserWarning`` diz quantos são.
    * As janelas saem da mais recente para a mais antiga. Cada uma traz os
      resultados na ordem do portal, mas a ordem entre janelas é a de data.
    * O dia que sozinho passa do teto não se divide: saem os primeiros
      resultados dele, até o teto, com ``UserWarning``.
    * Com divisão, o item que já veio numa janela anterior (``busca.chave``
      igual) é retirado da página em que reaparece. A repetição dentro de uma
      mesma janela é do portal e fica como veio. O portal segue indexando
      durante a coleta: a soma das janelas pode diferir do total que a
      primeira página informou.

    Raises:
        ColetaParcialError: Quando uma requisição falha depois de a busca ter
            sido dividida e já haver página baixada. A coleta para ali;
            ``resultado`` traz ``busca.parse`` das páginas baixadas e a
            mensagem diz o intervalo que falta.
        Exception: A falha de ``busca.buscar``, como veio, quando a busca não
            foi dividida ou ainda não há página baixada.
    """
    janelas: list[list[_Pagina]] = []
    pendentes: list[_Janela] = [(_data(inicio), _data(fim), None)]
    dividiu = False
    pedir = _pedir_com_intervalo(busca)

    while pendentes:
        janela = pendentes.pop()
        try:
            primeira = pedir(janela, 1)
            total = busca.contar_resultados(primeira)
            filhas = _janelas_filhas(busca, janela, total)
            pendentes.extend(filhas)
            dividiu = dividiu or bool(filhas)
            if not filhas and (total or not dividiu):
                janelas.append([primeira])
                _baixar_demais_paginas(busca, janela, total, pedir, janelas[-1])
        except Exception as exc:
            if not dividiu or not janelas:
                raise
            raise ColetaParcialError(
                f"{busca.tribunal}: a coleta dividida por {busca.rotulo} parou na janela de {janela[0]} a "
                f"{janela[1]}: {exc!r}. O atributo .resultado do erro traz o que foi baixado, inclusive as "
                f"páginas já lidas dessa janela. Falta o intervalo que termina em {janela[1]}: repita a busca "
                f"com {busca.rotulo}_fim nessa data e junte os resultados, retirando as linhas repetidas.",
                resultado=busca.parse(_sem_repetidos(busca, janelas)),
                falhas=[(str(janela[0]), str(janela[1]), exc)],
            ) from exc

    return _sem_repetidos(busca, janelas)


def _hoje() -> date:
    """A data de hoje no fuso da máquina, fim da janela quando a busca não tem data final."""
    return datetime.now().astimezone().date()


def _data(valor: str | None) -> date | None:
    return date.fromisoformat(valor) if valor else None


def _pedir_com_intervalo(busca: BuscaComTeto[_Pagina]) -> Callable[[_Janela, int], _Pagina]:
    """``busca.buscar`` com ``busca.sleep_time`` antes de cada requisição, menos da primeira."""
    pediu = False

    def pedir(janela: _Janela, pagina: int) -> _Pagina:
        nonlocal pediu
        if pediu and busca.sleep_time:
            time.sleep(busca.sleep_time)
        pediu = True
        inicio, fim, _ = janela
        return busca.buscar(inicio.isoformat() if inicio else None, fim.isoformat() if fim else None, pagina)

    return pedir


def _baixar_demais_paginas(
    busca: BuscaComTeto[_Pagina],
    janela: _Janela,
    total: int,
    pedir: Callable[[_Janela, int], _Pagina],
    paginas: list[_Pagina],
) -> None:
    """Acrescenta a ``paginas`` as páginas da janela a partir da segunda, até o teto.

    Uma a uma: quando uma requisição falha, as anteriores já estão em ``paginas``.
    """
    n_pags = math.ceil(min(total, busca.teto) / busca.por_pagina)
    barra = tqdm(range(2, n_pags + 1), desc=f"Baixando páginas {busca.tribunal}{_legenda(janela)}")
    paginas.extend(pedir(janela, pagina) for pagina in barra)


def _janelas_filhas(busca: BuscaComTeto, janela: _Janela, total: int) -> list[_Janela]:
    """As janelas que substituem ``janela`` se ela passa do teto, a mais antiga primeiro; vazio se ela é baixada.

    A janela com limite aberto é fechada em ``busca.piso`` e hoje, e leva
    ``total`` para a conferência dos registros que ficam de fora, feita aqui
    quando ela volta. A fechada é partida ao meio, sem dia em comum entre as
    metades. O dia único acima do teto não tem filhas: avisa e é baixado.
    """
    inicio, fim, total_da_busca = janela
    if total_da_busca is not None and total < total_da_busca:
        avisar(
            f"{busca.tribunal}: a busca tem {total_da_busca} resultados, mas só {total} têm {busca.rotulo} "
            f"entre {inicio} e {fim}; os demais não entram na divisão por data e não foram baixados."
        )
    if total <= busca.teto:
        return []
    if inicio is None or fim is None:
        return [(inicio or busca.piso, fim or _hoje(), total)]
    if inicio < fim:
        meio = inicio + (fim - inicio) // 2
        return [(inicio, meio, None), (meio + timedelta(days=1), fim, None)]
    avisar(
        f"{busca.tribunal}: o dia {inicio} tem {total} resultados, e o portal só entrega os {busca.teto} "
        "primeiros de uma busca; os demais desse dia não foram baixados. Restrinja a busca por outro filtro "
        "para alcançá-los."
    )
    return []


def _legenda(janela: _Janela) -> str:
    """Sufixo da barra de progresso com a janela, vazio na busca de limite aberto."""
    return "" if janela[0] is None or janela[1] is None else f" ({janela[0]} a {janela[1]})"


def _sem_repetidos(busca: BuscaComTeto[_Pagina], janelas: list[list[_Pagina]]) -> list[_Pagina]:
    """As páginas de todas as janelas, em ordem, sem o item cuja chave já veio numa janela anterior.

    O item é retirado no lugar, da lista que ``busca.itens`` devolve. Com uma janela só, nada muda.
    """
    vistas: set[Hashable] = set()
    todas: list[_Pagina] = []
    for paginas in janelas:
        listas = [busca.itens(pagina) for pagina in paginas]
        for lista in listas:
            lista[:] = [item for item in lista if busca.chave(item) not in vistas]
        vistas.update(busca.chave(item) for lista in listas for item in lista)
        todas.extend(paginas)
    return todas
