"""Divisão de uma busca em janelas de data quando o portal corta os resultados num teto.

Para o portal que limita a quantidade de resultados: as janelas saem da
contagem que ele informa. O portal que limita o tamanho do intervalo de datas
(eSAJ, 1 ano) usa janelas fixas, em :func:`juscraper.utils.params.run_chunked_search`.
"""
from __future__ import annotations

import math
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Generic, TypeVar

import pandas as pd
from tqdm import tqdm

from juscraper.core.avisos import avisar
from juscraper.core.exceptions import ColetaParcialError
from juscraper.core.intervalo import IntervaloEntrePedidos

_Pagina = TypeVar("_Pagina")
# Início e fim inclusivos; ``None`` é o limite aberto da busca original.
_Janela = tuple[date | None, date | None]


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

    @property
    def alcance(self) -> int:
        """Quantos resultados as páginas inteiras dentro do teto alcançam (9.990 com 30 por página)."""
        return self.teto - self.teto % self.por_pagina

    def paginas_ao_alcance(self, total: int) -> int:
        """Quantas páginas de uma busca de ``total`` resultados o portal entrega."""
        return math.ceil(min(total, self.alcance) / self.por_pagina)


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

    * A primeira divisão emite ``UserWarning`` com o total e o número
      aproximado de requisições da coleta que começa.
    * Ao dividir, o limite aberto vira ``busca.piso`` (início) ou a data de
      hoje (fim), sem novo pedido. O registro sem a data do filtro, ou fora desse intervalo,
      não entra em janela nenhuma: se as janelas somam menos que o total da
      busca original, um ``UserWarning`` ao fim diz os dois números.
    * As janelas saem da mais recente para a mais antiga. Cada uma traz os
      resultados na ordem do portal, mas a ordem entre janelas é a de data.
    * O dia que sozinho passa do teto não se divide: saem os primeiros
      resultados dele, até o teto, com ``UserWarning``. Quando
      ``por_pagina`` não divide o teto, vale a última página inteira dentro
      dele (``busca.alcance``).
    * Com divisão, o item que já veio numa janela anterior (``busca.chave``
      igual) é retirado da página em que reaparece. A repetição dentro de uma
      mesma janela é do portal e fica como veio. O portal segue indexando
      durante a coleta: a soma das janelas pode passar do total que a
      primeira página informou.

    Raises:
        ColetaParcialError: Quando uma requisição falha depois de a busca ter
            sido dividida e já haver página baixada. A coleta para ali;
            ``resultado`` traz ``busca.parse`` das páginas baixadas e a
            mensagem diz o intervalo que falta.
        Exception: A falha de ``busca.buscar``, como veio, quando a busca não
            foi dividida ou ainda não há página baixada.
    """
    coleta = _Coleta(busca)
    pendentes: list[_Janela] = [(_data(inicio), _data(fim))]
    while pendentes:
        janela = pendentes.pop()
        try:
            pendentes.extend(coleta.visitar(janela))
        except Exception as exc:
            if not coleta.dividiu or not coleta.janelas:
                raise
            mais_antiga = (pendentes[0] if pendentes else janela)[0]
            raise ColetaParcialError(
                f"{busca.tribunal}: a coleta dividida por {busca.rotulo} parou na janela de {janela[0]} a "
                f"{janela[1]}: {exc!r}. O atributo .resultado do erro traz o que foi baixado, inclusive as "
                f"páginas já lidas dessa janela. Falta o intervalo de {mais_antiga} a {janela[1]}: repita a "
                f"busca com {busca.rotulo}_inicio e {busca.rotulo}_fim nessas datas e junte os resultados, "
                "retirando as linhas repetidas.",
                resultado=busca.parse(_sem_repetidos(busca, coleta.janelas)),
                falhas=[(str(janela[0]), str(janela[1]), exc)],
            ) from exc

    if coleta.soma_das_janelas < coleta.total_da_busca:
        avisar(
            f"{busca.tribunal}: a busca informou {coleta.total_da_busca} resultados, e as janelas de "
            f"{busca.rotulo} somaram {coleta.soma_das_janelas}. A diferença não foi baixada: é registro sem essa "
            "data, com data fora do intervalo dividido, ou que saiu do índice do portal durante a coleta."
        )
    return _sem_repetidos(busca, coleta.janelas)


class _Coleta(Generic[_Pagina]):
    """O andamento de uma coleta: as páginas baixadas, por janela, e as contagens da conferência final."""

    def __init__(self, busca: BuscaComTeto[_Pagina]) -> None:
        self.busca = busca
        self.janelas: list[list[_Pagina]] = []
        # O total da busca original, conhecido na primeira divisão; zero enquanto ela não foi dividida.
        self.total_da_busca = 0
        self.soma_das_janelas = 0
        self._intervalo = IntervaloEntrePedidos()

    @property
    def dividiu(self) -> bool:
        """Se a busca já passou do alcance do portal e foi dividida."""
        return self.total_da_busca > 0

    def _pedir(self, janela: _Janela, pagina: int) -> _Pagina:
        with self._intervalo.pedido(self.busca.sleep_time):
            return self.busca.buscar(_iso(janela[0]), _iso(janela[1]), pagina)

    def visitar(self, janela: _Janela) -> list[_Janela]:
        """Pede a primeira página da janela e a baixa inteira, ou devolve as janelas que a substituem."""
        busca = self.busca
        primeira = self._pedir(janela, 1)
        total = busca.contar_resultados(primeira)
        filhas = _janelas_filhas(busca, janela, total)
        if filhas and not self.dividiu:
            self.total_da_busca = total
            avisar(
                f"{busca.tribunal}: a busca tem {total} resultados, e o portal só entrega os {busca.alcance} "
                f"primeiros. Ela será dividida por {busca.rotulo} e baixada inteira, em cerca de "
                f"{math.ceil(total / busca.por_pagina)} requisições. Para baixar só até o teto, passe "
                "auto_chunk=False."
            )
        # A janela vazia de uma busca dividida não tem o que devolver; a busca vazia devolve a sua página.
        if not filhas and (total or not self.dividiu):
            self.soma_das_janelas += total
            self.janelas.append([primeira])
            for pagina in _barra(busca, janela, total):
                self.janelas[-1].append(self._pedir(janela, pagina))
        return filhas


def _hoje() -> date:
    """A data de hoje no fuso da máquina, fim da janela quando a busca não tem data final."""
    return datetime.now().astimezone().date()


def _data(valor: str | None) -> date | None:
    return date.fromisoformat(valor) if valor else None


def _iso(valor: date | None) -> str | None:
    return valor.isoformat() if valor else None


def _janelas_filhas(busca: BuscaComTeto, janela: _Janela, total: int) -> list[_Janela]:
    """As janelas que substituem ``janela`` se ela passa do alcance, a mais antiga primeiro; vazio se ela é baixada.

    O limite aberto é fechado em ``busca.piso`` e hoje, e a janela é partida
    ao meio, sem dia em comum entre as metades. O dia único acima do alcance
    não tem filhas: avisa e é baixado.
    """
    if total <= busca.alcance:
        return []
    inicio, fim = janela[0] or busca.piso, janela[1] or _hoje()
    if inicio < fim:
        meio = inicio + (fim - inicio) // 2
        return [(inicio, meio), (meio + timedelta(days=1), fim)]
    if None in janela:
        return [(inicio, fim)]
    avisar(
        f"{busca.tribunal}: o dia {inicio} tem {total} resultados, e o portal só entrega os {busca.alcance} "
        "primeiros de uma busca; os demais desse dia não foram baixados. Restrinja a busca por outro filtro "
        "para alcançá-los."
    )
    return []


def _barra(busca: BuscaComTeto, janela: _Janela, total: int) -> tqdm:
    """Barra de progresso sobre as páginas da janela a partir da segunda, até a última que o portal entrega."""
    legenda = "" if janela[0] is None or janela[1] is None else f" ({janela[0]} a {janela[1]})"
    return tqdm(range(2, busca.paginas_ao_alcance(total) + 1), desc=f"Baixando páginas {busca.tribunal}{legenda}")


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
