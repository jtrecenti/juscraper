"""Intervalo mínimo entre pedidos a um mesmo serviço."""
from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager


class IntervaloEntrePedidos:
    """Guarda o fim do último pedido e espera o que falta do intervalo antes do próximo.

    Quem compartilha o objeto compartilha a espera: um por instância de
    raspador separa só os pedidos dela (eSAJ); um na classe separa os de todas
    as instâncias do processo, para o serviço que limita por cliente (TSE).
    Uma trava cobre a espera e o pedido: threads que compartilham o objeto
    fazem um pedido por vez.
    """

    def __init__(self) -> None:
        """Começa sem pedido anterior: o primeiro não espera."""
        self._ultimo: float | None = None
        self._trava = threading.Lock()

    @contextmanager
    def pedido(self, intervalo: float) -> Iterator[None]:
        """Contexto de um pedido, a ``intervalo`` segundos ou mais do fim do anterior.

        A espera só completa o que falta: o processamento entre um pedido e
        outro abate dela, o tempo de resposta não. O pedido que falha também
        conta. ``intervalo`` zero não espera.
        """
        with self._trava:
            if self._ultimo is not None and intervalo:
                espera = intervalo - (time.monotonic() - self._ultimo)
                if espera > 0:
                    time.sleep(espera)
            try:
                yield
            finally:
                self._ultimo = time.monotonic()
