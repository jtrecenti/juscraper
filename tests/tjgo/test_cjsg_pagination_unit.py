"""Testes unitarios da extracao de contagem TJGO via util compartilhado (refs #87)."""
from __future__ import annotations

import pytest

from juscraper.courts.tjgo.download import _extract_total, cjsg_download
from tests._helpers import load_sample


def _sample(name: str) -> str:
    return load_sample("tjgo", f"cjsg/{name}", encoding="iso-8859-1")


def test_extract_total_results_normal_first_page():
    html = _sample("results_normal_page_01.html")
    assert _extract_total(html) == 1273234


def test_extract_total_single_page():
    html = _sample("single_page.html")
    assert _extract_total(html) == 1


def test_extract_total_no_results_sem_legend_da_none():
    """A busca vazia volta sem o ``legend``; o download a reconhece por não ter resultados."""
    html = _sample("no_results.html")
    assert _extract_total(html) is None


def test_extract_total_handles_dot_separated_thousands():
    html = (
        '<legend class="formLocalizarLegenda">'
        "1.234 resultados encontrados para o filtro da pesquisa"
        "</legend>"
    )
    assert _extract_total(html) == 1234


def test_extract_total_sem_o_legend_nao_le_o_html_bruto():
    """Sem ``legend.formLocalizarLegenda``, "N resultados" fora dele (numa ementa) não vira total."""
    html = (
        '<div class="painel-resultados">'
        "<p>a diligência teve 456 resultados negativos</p></div>"
    )
    assert _extract_total(html) is None


def _download(html: str, paginas=None) -> list:
    """``cjsg_download`` com a página 1 respondida por ``html``; outra página falha o teste."""
    def request_fn(method, *_args, **kwargs):
        if method == "GET":
            return _Resposta("")
        assert kwargs["data"]["PosicaoPaginaAtual"] == "0", "só a página 1 deveria ser pedida"
        return _Resposta(html)

    return cjsg_download(
        "dano moral", paginas, request_fn=request_fn, id_instancia="0", id_area="0",
        id_serventia_subtipo="0", data_publicacao_inicio="", data_publicacao_fim="",
        numero_processo="", qtde_itens_pagina=10, sleep_time=0,
    )


class _Resposta:
    def __init__(self, text: str) -> None:
        self.text = text
        self.encoding = None


@pytest.mark.parametrize("paginas", [None, [1]])
def test_download_com_resultados_sem_o_legend_levanta(paginas):
    """HTML derivado do sample real: resultados sem o ``legend`` são markup novo, não 1 página."""
    html = _sample("results_normal_page_01.html")
    sem_legend = html.replace('class="formLocalizarLegenda"', 'class="outra-classe"')
    assert sem_legend != html
    with pytest.raises(ValueError, match="TJGO: a página lida não traz a contagem"):
        _download(sem_legend, paginas)


def test_download_busca_vazia_da_uma_pagina():
    with pytest.warns(UserWarning, match="Turnstile"):
        assert _download(_sample("no_results.html")) == [_sample("no_results.html")]
