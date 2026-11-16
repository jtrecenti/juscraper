"""Intervalo mínimo entre pedidos, comum ao eSAJ e ao TSE."""
import threading
import time

import pytest

from juscraper.core.intervalo import IntervaloEntrePedidos


@pytest.fixture
def espera(mocker):
    return mocker.patch("juscraper.core.intervalo.time.sleep")


def _relogio(mocker, *instantes):
    return mocker.patch("juscraper.core.intervalo.time.monotonic", side_effect=instantes)


def test_primeiro_pedido_nao_espera(mocker, espera):
    _relogio(mocker, 100.0)

    with IntervaloEntrePedidos().pedido(10):
        pass

    espera.assert_not_called()


def test_espera_so_o_que_falta_desde_o_fim_do_pedido_anterior(mocker, espera):
    # Fim do primeiro em 100; o segundo chega em 103 e termina em 110.
    _relogio(mocker, 100.0, 103.0, 110.0)
    intervalo = IntervaloEntrePedidos()

    with intervalo.pedido(10):
        pass
    with intervalo.pedido(10):
        pass

    espera.assert_called_once_with(7.0)


def test_intervalo_ja_cumprido_nao_espera(mocker, espera):
    _relogio(mocker, 100.0, 111.0, 112.0)
    intervalo = IntervaloEntrePedidos()

    with intervalo.pedido(10):
        pass
    with intervalo.pedido(10):
        pass

    espera.assert_not_called()


def test_pedido_que_falha_tambem_conta(mocker, espera):
    _relogio(mocker, 50.0, 51.0, 60.0)
    intervalo = IntervaloEntrePedidos()

    def pedido_que_falha() -> None:
        with intervalo.pedido(4):
            raise RuntimeError("falhou")

    with pytest.raises(RuntimeError):
        pedido_que_falha()
    with intervalo.pedido(4):
        pass

    espera.assert_called_once_with(3.0)


def test_intervalo_zero_nao_espera(mocker, espera):
    _relogio(mocker, 100.0, 100.0)
    intervalo = IntervaloEntrePedidos()

    with intervalo.pedido(0):
        pass
    with intervalo.pedido(0):
        pass

    espera.assert_not_called()


def test_cada_pedido_usa_o_proprio_intervalo(mocker, espera):
    _relogio(mocker, 100.0, 101.0, 102.0)
    intervalo = IntervaloEntrePedidos()

    with intervalo.pedido(10):
        pass
    with intervalo.pedido(2):
        pass

    espera.assert_called_once_with(1.0)


def test_threads_fazem_um_pedido_por_vez():
    intervalo = IntervaloEntrePedidos()
    dentro = 0
    maximo = 0

    def pedido() -> None:
        nonlocal dentro, maximo
        with intervalo.pedido(0):
            dentro += 1
            maximo = max(maximo, dentro)
            time.sleep(0.01)
            dentro -= 1

    threads = [threading.Thread(target=pedido) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert maximo == 1
