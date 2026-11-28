"""Conferência de cada resposta antes da leitura (``utils/pagination.py``).

Regra: toda resposta é conferida como a página esperada antes de se ler algo
dela; contagem ausente levanta; página pedida dentro do total traz ao menos
um item e não repete outra. Sem isso, a página de erro vira busca vazia e a
página que falha no meio vira coleta menor, sem erro.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from juscraper.core.exceptions import PaginaInesperadaError
from juscraper.utils.pagination import (
    ConferenciaDePaginas,
    PaginaEsperada,
    baixar_paginas_pedidas,
    contagem_json,
    exigir_pagina,
    resolve_total_pages,
)

# ---------------------------------------------------------------------------
# contagem_json
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("dados", "caminho", "esperado"),
    [
        ({"total": 42}, ("total",), 42),
        ({"hits": {"total": {"value": 0}}}, ("hits", "total", "value"), 0),
        ({"data": [{"n": 7}]}, ("data", 0, "n"), 7),
    ],
)
def test_contagem_json_devolve_o_inteiro(dados, caminho, esperado):
    assert contagem_json(dados, *caminho) == esperado


@pytest.mark.parametrize(
    ("dados", "caminho"),
    [
        ({"error": "Solr fora"}, ("total",)),  # chave ausente: resposta de erro
        ({"hits": []}, ("hits", "total")),  # passo que não é objeto
        ({"data": []}, ("data", 0)),  # índice fora da lista
        ({"data": [1]}, ("data", -1)),  # índice negativo não é aceito
        ([{"total": 3}], ("total",)),  # resposta que não é objeto
        ({"total": "42"}, ("total",)),  # texto com dígitos
        ({"total": 42.0}, ("total",)),
        ({"total": True}, ("total",)),  # bool herda de int
        ({"total": None}, ("total",)),
        ({"total": -1}, ("total",)),
    ],
)
def test_contagem_json_devolve_none_sem_inteiro(dados, caminho):
    assert contagem_json(dados, *caminho) is None


def test_contagem_json_ausente_faz_resolve_total_pages_levantar():
    with pytest.raises(PaginaInesperadaError, match="não traz a contagem") as erro:
        resolve_total_pages(contagem_json({}, "total"), resultados_por_pagina=10, tribunal="TJXX")
    assert (erro.value.tribunal, erro.value.etapa) == ("TJXX", "contagem")
    assert isinstance(erro.value, ValueError)


# ---------------------------------------------------------------------------
# resolve_total_pages(n_linhas=)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("n_resultados", "n_linhas"), [(0, 3), (5, 10)])
def test_resolve_total_pages_levanta_com_mais_linhas_que_a_contagem(n_resultados, n_linhas):
    """Contagem 0 numa página com linhas, ou contagem menor que as linhas: não é desta página."""
    with pytest.raises(PaginaInesperadaError, match=f"traz {n_linhas} resultado"):
        resolve_total_pages(n_resultados, resultados_por_pagina=10, tribunal="TJXX", n_linhas=n_linhas)


@pytest.mark.parametrize(("n_resultados", "n_linhas", "esperado"), [(0, 0, 1), (25, 10, 3), (25, 0, 3), (7, 7, 1)])
def test_resolve_total_pages_aceita_linhas_ate_a_contagem(n_resultados, n_linhas, esperado):
    """Linhas a menos não levantam aqui: a página lida pode estar além do total."""
    assert resolve_total_pages(n_resultados, resultados_por_pagina=10, tribunal="TJXX", n_linhas=n_linhas) == esperado


def test_resolve_total_pages_link_divergente_e_pagina_inesperada():
    with pytest.raises(PaginaInesperadaError, match="link de última página"):
        resolve_total_pages(25, resultados_por_pagina=10, totais_links=[1], tribunal="TJXX")


# ---------------------------------------------------------------------------
# exigir_pagina
# ---------------------------------------------------------------------------


def test_exigir_pagina_devolve_a_resposta_reconhecida():
    html = "<table id='resultados'></table>"
    esperada = PaginaEsperada("TJXX", "cjsg", lambda h: "resultados" in h)
    assert exigir_pagina(html, esperada) is html


def test_exigir_pagina_levanta_com_a_url_da_resposta():
    """Página de outro tipo (formulário, sessão expirada) com 200: erro, e não busca vazia."""
    resp = SimpleNamespace(url="https://tj.example/sessao-expirada", text="<form></form>")
    esperada = PaginaEsperada(
        "TJXX",
        "passo 3: escolha do tipo",
        lambda r: "resultados" in r.text,
        "a tabela de escolha do tipo",
        "o portal devolveu o formulário",
    )

    with pytest.raises(PaginaInesperadaError) as erro:
        exigir_pagina(resp, esperada, pagina=2)

    assert str(erro.value) == (
        "TJXX passo 3: escolha do tipo: a resposta de https://tj.example/sessao-expirada não é "
        "a tabela de escolha do tipo: o portal devolveu o formulário."
    )
    assert (erro.value.etapa, erro.value.pagina, erro.value.url) == (
        "passo 3: escolha do tipo", 2, "https://tj.example/sessao-expirada",
    )
    assert isinstance(erro.value, RuntimeError)


def test_exigir_pagina_sem_url_nem_motivo():
    with pytest.raises(PaginaInesperadaError, match=r"^TJXX cjsg: a resposta não é a página esperada\.$"):
        exigir_pagina({}, PaginaEsperada("TJXX", "cjsg", lambda d: "hits" in d))


# ---------------------------------------------------------------------------
# ConferenciaDePaginas
# ---------------------------------------------------------------------------


def test_conferencia_pagina_alheia_levanta():
    with pytest.raises(PaginaInesperadaError, match="não é uma página de resultados") as erro:
        ConferenciaDePaginas("TJXX", n_pags=5).conferir(3, None, url="https://tj.example/p3")
    assert (erro.value.pagina, erro.value.url, erro.value.etapa) == (3, "https://tj.example/p3", "paginação")


@pytest.mark.parametrize(
    ("pagina", "n_pags", "n_resultados"),
    [
        (2, 5, None),  # dentro de um total de várias páginas
        (1, 5, None),  # a página 1 também, quando há mais de uma
        (1, 1, 3),  # página única com resultados contados
        (2, None, 591),  # total de páginas desconhecido, resultados conhecidos
    ],
)
def test_conferencia_pagina_vazia_dentro_do_total_levanta(pagina, n_pags, n_resultados):
    conferencia = ConferenciaDePaginas("TJXX", n_pags=n_pags, n_resultados=n_resultados, itens="documentos")
    with pytest.raises(PaginaInesperadaError, match="deveria trazer documentos"):
        conferencia.conferir(pagina, 0)


@pytest.mark.parametrize(
    ("pagina", "n_pags", "n_resultados"),
    [
        (1, 1, None),  # pode ser a busca vazia: sem a contagem, não há como saber
        (1, 1, 0),  # busca vazia
        (6, 5, None),  # além do total
        (2, None, None),  # nada se sabe do total
        (2, None, 0),
    ],
)
def test_conferencia_pagina_vazia_fora_do_total_passa(pagina, n_pags, n_resultados):
    ConferenciaDePaginas("TJXX", n_pags=n_pags, n_resultados=n_resultados).conferir(pagina, 0)


def test_conferencia_pagina_repetida_levanta():
    conferencia = ConferenciaDePaginas("TJXX")
    conferencia.conferir(1, 2, chaves=["a", "b"])
    conferencia.conferir(2, 2, chaves=["c", "d"])

    with pytest.raises(PaginaInesperadaError, match="página 3 da busca repete os itens da página 1"):
        conferencia.conferir(3, 2, chaves=["b", "a"])


def test_conferencia_com_itens_em_comum_nao_e_repeticao():
    """Ordem instável pode empurrar um item para a página seguinte; só a página igual é repetição."""
    conferencia = ConferenciaDePaginas("TJXX")
    conferencia.conferir(1, 2, chaves=["a", "b"])
    conferencia.conferir(2, 2, chaves=["b", "c"])


def test_conferencia_mesma_pagina_conferida_de_novo_nao_e_repeticao():
    conferencia = ConferenciaDePaginas("TJXX")
    conferencia.conferir(1, 2, chaves=["a", "b"])
    conferencia.conferir(1, 2, chaves=["a", "b"])


# ---------------------------------------------------------------------------
# baixar_paginas_pedidas(n_itens=, chaves=)
# ---------------------------------------------------------------------------


def _portal(paginas: dict[int, list[str] | None], n_pags: int):
    """``buscar`` de um portal falso: cada página é a lista de ids, ou ``None`` (página alheia)."""
    pedidas: list[int] = []

    def buscar(pagina: int):
        pedidas.append(pagina)
        return {"pagina": pagina, "ids": paginas.get(pagina, [])}

    def contar(_primeira) -> int:
        return n_pags

    def n_itens(conteudo) -> int | None:
        return None if conteudo["ids"] is None else len(conteudo["ids"])

    def chaves(conteudo):
        return conteudo["ids"] or ()

    return buscar, contar, n_itens, chaves, pedidas


def test_baixar_paginas_pedidas_sem_n_itens_nao_confere():
    buscar, contar, _, _, _ = _portal({1: ["a"], 2: None}, 2)
    assert len(baixar_paginas_pedidas(None, buscar, contar, tribunal="TJXX")) == 2


def test_baixar_paginas_pedidas_pagina_alheia_levanta_e_para():
    buscar, contar, n_itens, _, pedidas = _portal({1: ["a"], 2: None, 3: ["c"]}, 3)

    with pytest.raises(PaginaInesperadaError, match="página 2 da busca veio sem resultados"):
        baixar_paginas_pedidas(None, buscar, contar, tribunal="TJXX", n_itens=n_itens)

    assert pedidas == [1, 2]


def test_baixar_paginas_pedidas_pagina_vazia_dentro_do_total_levanta():
    buscar, contar, n_itens, _, _ = _portal({1: ["a"], 2: [], 3: ["c"]}, 3)

    with pytest.raises(PaginaInesperadaError, match="dentro do total de 3 páginas"):
        baixar_paginas_pedidas(None, buscar, contar, tribunal="TJXX", n_itens=n_itens)


def test_baixar_paginas_pedidas_primeira_vazia_com_varias_paginas_levanta():
    """A contagem diz 3 páginas, e a primeira veio sem itens: a lista não é a desta busca."""
    buscar, contar, n_itens, _, _ = _portal({1: [], 2: ["b"]}, 3)

    with pytest.raises(PaginaInesperadaError, match="página 1 da busca veio sem resultados"):
        baixar_paginas_pedidas(None, buscar, contar, tribunal="TJXX", n_itens=n_itens)


def test_baixar_paginas_pedidas_pagina_repetida_levanta():
    buscar, contar, n_itens, chaves, _ = _portal({1: ["a", "b"], 2: ["a", "b"]}, 2)

    with pytest.raises(PaginaInesperadaError, match="repete os itens da página 1"):
        baixar_paginas_pedidas(None, buscar, contar, tribunal="TJXX", n_itens=n_itens, chaves=chaves)


def test_baixar_paginas_pedidas_busca_vazia_e_ultima_pagina_curta_passam():
    buscar, contar, n_itens, chaves, _ = _portal({1: []}, 1)
    assert len(baixar_paginas_pedidas(None, buscar, contar, tribunal="TJXX", n_itens=n_itens, chaves=chaves)) == 1

    buscar, contar, n_itens, chaves, pedidas = _portal({1: ["a", "b"], 2: ["c"]}, 2)
    baixar_paginas_pedidas(None, buscar, contar, tribunal="TJXX", n_itens=n_itens, chaves=chaves)
    assert pedidas == [1, 2]


def test_baixar_paginas_pedidas_primeira_alem_do_total_nao_e_conferida():
    """A página pedida além do total vai para o log, sem conferência nem segunda requisição."""
    buscar, contar, n_itens, _, pedidas = _portal({}, 2)
    assert baixar_paginas_pedidas([5], buscar, contar, tribunal="TJXX", n_itens=n_itens) == []
    assert pedidas == [5]


def test_baixar_paginas_pedidas_chaves_sem_n_itens_e_erro_de_uso():
    buscar, contar, _, chaves, pedidas = _portal({1: ["a"]}, 1)
    with pytest.raises(TypeError, match="n_itens"):
        baixar_paginas_pedidas(None, buscar, contar, tribunal="TJXX", chaves=chaves)
    assert pedidas == []
