"""Testes de ``baixar_dividindo_por_data``: divisão por data da busca que passa do teto do portal."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from juscraper.core.exceptions import ColetaParcialError
from juscraper.utils.divisao_por_data import BuscaComTeto, baixar_dividindo_por_data

HOJE = date(2024, 12, 31)
PISO = date(2024, 1, 1)
POR_PAGINA = 2

# O aviso da primeira divisão tem teste próprio; nos demais é esperado.
pytestmark = pytest.mark.filterwarnings("ignore:.*Ela será dividida por:UserWarning")


def _data(valor: str | None) -> date | None:
    return date.fromisoformat(valor) if valor else None


class _Portal:
    """Portal de mentira: filtra por data com limites inclusivos, pagina e informa o total inteiro.

    Como o TJBA e o TJRO, recusa a página além do ``teto``. Cada item é
    ``{"id", "data"}``; ``data=None`` é o registro sem a data do filtro, que
    só aparece na busca sem limite nenhum.
    """

    def __init__(self, itens: list[dict], teto: int):
        self.itens = itens
        self.teto = teto
        self.pedidos: list[tuple[date | None, date | None, int]] = []
        self.falhar_em: tuple[date | None, date | None, int] | None = None

    def buscar(self, inicio: str | None, fim: str | None, pagina: int) -> dict:
        janela = (_data(inicio), _data(fim))
        self.pedidos.append((*janela, pagina))
        if (*janela, pagina) == self.falhar_em:
            raise ConnectionError("portal caiu")
        assert pagina * POR_PAGINA <= self.teto or pagina == 1, "pedido além do teto do portal"
        na_janela = [
            item for item in self.itens
            if janela == (None, None)
            or (item["data"] is not None and (janela[0] or date.min) <= item["data"] <= (janela[1] or date.max))
        ]
        corte = (pagina - 1) * POR_PAGINA
        return {"total": len(na_janela), "itens": na_janela[corte:corte + POR_PAGINA]}


def _baixar(
    portal: _Portal, inicio: date | None = None, fim: date | None = None, sleep_time: float = 0.0
) -> list[dict]:
    busca: BuscaComTeto[dict] = BuscaComTeto(
        tribunal="TJXX",
        rotulo="data_julgamento",
        teto=portal.teto,
        por_pagina=POR_PAGINA,
        piso=PISO,
        buscar=portal.buscar,
        contar_resultados=lambda pagina: pagina["total"],
        itens=lambda pagina: pagina["itens"],
        chave=lambda item: item["id"],
        parse=lambda paginas: pd.DataFrame([item for pagina in paginas for item in pagina["itens"]]),
        sleep_time=sleep_time,
    )
    return baixar_dividindo_por_data(
        busca, inicio.isoformat() if inicio else None, fim.isoformat() if fim else None
    )


def _ids(paginas: list[dict]) -> list[int]:
    return [item["id"] for pagina in paginas for item in pagina["itens"]]


def _um_por_dia(n: int) -> list[dict]:
    """``n`` itens, um por dia a partir de ``PISO``, na ordem do mais recente para o mais antigo."""
    return [{"id": i, "data": PISO + timedelta(days=i)} for i in reversed(range(n))]


@pytest.fixture(autouse=True)
def _hoje(mocker):
    mocker.patch("juscraper.utils.divisao_por_data._hoje", return_value=HOJE)


def test_busca_que_cabe_no_teto_sai_numa_janela_so_com_os_limites_de_quem_chamou(recwarn):
    portal = _Portal(_um_por_dia(5), teto=6)

    paginas = _baixar(portal)

    assert _ids(paginas) == [4, 3, 2, 1, 0]
    assert portal.pedidos == [(None, None, 1), (None, None, 2), (None, None, 3)]
    assert not recwarn.list


def test_busca_vazia_devolve_a_pagina_vazia():
    portal = _Portal([], teto=6)

    assert _baixar(portal) == [{"total": 0, "itens": []}]


def test_busca_acima_do_teto_e_dividida_ate_caber_e_devolve_tudo():
    portal = _Portal(_um_por_dia(25), teto=6)

    with pytest.warns(UserWarning, match="a busca tem 25 resultados") as avisos:
        paginas = _baixar(portal)

    # Um aviso só, na primeira divisão, com o tamanho da coleta.
    assert [str(aviso.message) for aviso in avisos] == [
        "TJXX: a busca tem 25 resultados, e o portal só entrega os 6 primeiros. Ela será dividida por "
        "data_julgamento e baixada inteira, em cerca de 13 requisições. Para baixar só até o teto, passe "
        "auto_chunk=False."
    ]

    # Da janela mais recente para a mais antiga, e dentro de cada uma na ordem do portal.
    assert _ids(paginas) == list(reversed(range(25)))
    # Os limites abertos viram o piso e hoje, já partidos ao meio, sem dia em comum entre as metades.
    assert portal.pedidos[:2] == [(None, None, 1), (date(2024, 7, 2), HOJE, 1)]
    assert min(pedido[0] for pedido in portal.pedidos[1:]) == PISO  # type: ignore[type-var]


def test_limites_de_quem_chamou_sao_o_ponto_de_partida_da_divisao():
    portal = _Portal(_um_por_dia(25), teto=6)
    inicio, fim = PISO + timedelta(days=3), PISO + timedelta(days=20)

    paginas = _baixar(portal, inicio, fim)

    assert _ids(paginas) == list(reversed(range(3, 21)))
    assert portal.pedidos[0] == (inicio, fim, 1)
    assert all(inicio <= pedido[0] <= pedido[1] <= fim for pedido in portal.pedidos)  # type: ignore[operator]


def test_limite_aberto_de_um_lado_so_e_fechado_no_piso_ou_em_hoje():
    portal = _Portal(_um_por_dia(25), teto=6)

    paginas = _baixar(portal, PISO + timedelta(days=10), None)

    assert _ids(paginas) == list(reversed(range(10, 25)))
    assert portal.pedidos[1][1] == HOJE
    assert min(pedido[0] for pedido in portal.pedidos) == PISO + timedelta(days=10)  # type: ignore[type-var]


def test_registro_sem_a_data_do_filtro_fica_de_fora_com_aviso():
    itens = [*_um_por_dia(10), {"id": 100, "data": None}, {"id": 101, "data": PISO - timedelta(days=1)}]
    portal = _Portal(itens, teto=6)

    with pytest.warns(UserWarning, match=r"informou 12 resultados, e as janelas de data_julgamento somaram 10"):
        paginas = _baixar(portal)

    assert sorted(_ids(paginas)) == list(range(10))


def test_dia_que_sozinho_passa_do_teto_vem_ate_o_teto_com_aviso():
    cheio = PISO + timedelta(days=40)
    itens = [{"id": i, "data": cheio} for i in range(100, 109)] + _um_por_dia(4)
    portal = _Portal(itens, teto=6)

    with pytest.warns(UserWarning, match=rf"o dia {cheio} tem 9 resultados.*só entrega os 6 primeiros") as avisos:
        paginas = _baixar(portal)

    assert len(avisos) == 2  # o da primeira divisão e o do dia
    assert _ids(paginas) == [100, 101, 102, 103, 104, 105, 3, 2, 1, 0]
    assert (cheio, cheio, 4) not in portal.pedidos


def test_item_repetido_entre_janelas_sai_uma_vez_e_o_repetido_na_mesma_janela_fica():
    class _PortalQueRepete(_Portal):
        """Devolve também o item da véspera do início da janela, e o item 20 duas vezes na mesma página."""

        def buscar(self, inicio, fim, pagina):
            resposta = super().buscar(inicio, fim, pagina)
            ids = [item["id"] for item in resposta["itens"]]
            dia = _data(inicio)
            vespera = [item for item in self.itens if dia and item["data"] == dia - timedelta(days=1)]
            if any(item["data"] == dia for item in resposta["itens"]):
                resposta["itens"].extend(dict(item) for item in vespera)
            if 20 in ids:
                resposta["itens"].append({"id": 20, "data": PISO + timedelta(days=20)})
            return resposta

    portal = _PortalQueRepete(_um_por_dia(25), teto=6)

    ids = _ids(_baixar(portal))

    assert sorted(ids) == sorted([*range(25), 20])


def test_falha_depois_da_divisao_preserva_o_que_foi_baixado():
    portal = _Portal(_um_por_dia(25), teto=6)
    _baixar(portal)
    falha = [pedido for pedido in portal.pedidos if pedido[2] == 3][2]
    portal = _Portal(_um_por_dia(25), teto=6)
    portal.falhar_em = falha

    with pytest.raises(ColetaParcialError, match=rf"Falta o intervalo de {PISO} a {falha[1]}") as erro:
        _baixar(portal)

    assert isinstance(erro.value.__cause__, ConnectionError)
    assert erro.value.falhas == [(str(falha[0]), str(falha[1]), erro.value.__cause__)]
    baixados = erro.value.resultado["id"].tolist()
    # Tudo o que é mais recente que a janela que falhou, mais as duas páginas já lidas dela.
    assert baixados == sorted(baixados, reverse=True)
    assert (erro.value.resultado["data"] > falha[1]).sum() > 0
    assert (erro.value.resultado["data"] <= falha[1]).sum() == 2 * POR_PAGINA
    assert portal.pedidos[-1] == falha


@pytest.mark.parametrize("falha", [(None, None, 1), (date(2024, 7, 2), HOJE, 1)])
def test_falha_sem_pagina_baixada_sobe_como_veio(falha):
    portal = _Portal(_um_por_dia(25), teto=6)
    portal.falhar_em = falha

    with pytest.raises(ConnectionError):
        _baixar(portal)


def test_falha_na_busca_que_nao_foi_dividida_sobe_como_veio():
    portal = _Portal(_um_por_dia(5), teto=6)
    portal.falhar_em = (None, None, 2)

    with pytest.raises(ConnectionError):
        _baixar(portal)


def test_intervalo_entre_todas_as_requisicoes_menos_antes_da_primeira(mocker):
    sleep = mocker.patch("juscraper.core.intervalo.time.sleep")
    mocker.patch("juscraper.core.intervalo.time.monotonic", return_value=0.0)
    portal = _Portal(_um_por_dia(25), teto=6)

    _baixar(portal, sleep_time=0.5)

    assert [chamada.args for chamada in sleep.call_args_list] == [(0.5,)] * (len(portal.pedidos) - 1)


def test_pagina_que_nao_divide_o_teto_para_na_ultima_pagina_inteira():
    """Com 2 por página e teto 7, o portal recusa a página 4: 6 resultados cabem, 7 não."""
    portal = _Portal(_um_por_dia(7), teto=7)

    paginas = _baixar(portal)

    assert _ids(paginas) == list(reversed(range(7)))
    assert len(portal.pedidos) > 4  # foi dividida, em vez de pedir a página 4 da busca inteira
