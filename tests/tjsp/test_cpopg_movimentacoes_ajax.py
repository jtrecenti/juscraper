"""Movimentações do CPOPG carregadas sob demanda (carregarMovimentacoesAjax.do). Refs #428."""
from unittest.mock import Mock

import pytest
import requests
from bs4 import BeautifulSoup

from juscraper.courts.tjsp.cpopg_download import _completar_movimentacoes
from juscraper.courts.tjsp.cpopg_parse import cpopg_parse_single_html
from tests._helpers import load_sample

BASE = "https://esaj.tjsp.jus.br/"
CODIGO = "5G0003K1B0000"
URL_AJAX = BASE + "cpopg/carregarMovimentacoesAjax.do"

# Trecho do show.do atual: o botão e o contêiner vazio que o navegador preenche.
SHOW_SOB_DEMANDA = """<html><body>
\t\t<div id="containerExibirMovimentacoes" style="padding: 8px 0;">
\t\t\t<a id="btnExibirMovimentacoes" href="javascript:" class="linkNaoSelecionado">Exibir movimentações</a>
\t\t</div>
\t\t<div id="containerMovimentacoes"></div>
</body></html>"""


def _paginas():
    return [
        Mock(text=load_sample("tjsp", f"cpopg/movimentacoes_ajax_{nome}.html"), status_code=200)
        for nome in ("primeira", "meio", "ultima")
    ]


def test_segue_o_cursor_ate_a_ultima_pagina(tmp_path):
    sessao = Mock()
    sessao.get.side_effect = _paginas()
    html = _completar_movimentacoes(SHOW_SOB_DEMANDA, sessao, BASE, CODIGO)

    chamadas = sessao.get.call_args_list
    assert [c.args[0] for c in chamadas] == [URL_AJAX] * 3
    assert chamadas[0].kwargs["params"] == {"processo.codigo": CODIGO}
    # A primeira página traz o cursor num input; as demais, numa linha oculta.
    primeira, meio, _ = (BeautifulSoup(p.text, "html.parser") for p in _paginas())
    assert chamadas[1].kwargs["params"]["cursor"] == primeira.find("input", id="cursorMovimentacoesPaginado")["value"]
    assert chamadas[2].kwargs["params"]["cursor"] == meio.find("tr", id="trCursorMovimentacoes")["data-cursor"]

    arquivo = tmp_path / "processo.html"
    arquivo.write_text(html, encoding="utf-8")
    movimentacoes = cpopg_parse_single_html(str(arquivo))["movimentacoes"]
    assert len(movimentacoes) == 15
    assert movimentacoes.iloc[0][["data", "movimento"]].tolist() == ["02/11/2025", "Arquivado Definitivamente"]
    assert movimentacoes.iloc[-1]["data"] == "11/08/2015"
    assert movimentacoes.iloc[-1]["movimento"].startswith("Distribuído Livremente")


def test_layout_antigo_nao_faz_requisicao():
    sessao = Mock()
    html = load_sample("tjsp", "cpopg/show_standard.html")
    assert _completar_movimentacoes(html, sessao, BASE, CODIGO) == html
    sessao.get.assert_not_called()


def test_falha_no_ajax_levanta_http_error():
    sessao = Mock()
    sessao.get.return_value = Mock(text="", status_code=500)
    with pytest.raises(requests.HTTPError, match="movimentações"):
        _completar_movimentacoes(SHOW_SOB_DEMANDA, sessao, BASE, CODIGO)


def test_movimentacao_com_documento_le_a_descricao_do_link(tmp_path):
    sessao = Mock()
    sessao.get.side_effect = _paginas()
    arquivo = tmp_path / "processo.html"
    arquivo.write_text(_completar_movimentacoes(SHOW_SOB_DEMANDA, sessao, BASE, CODIGO), encoding="utf-8")
    movimentacoes = cpopg_parse_single_html(str(arquivo))["movimentacoes"]
    assert (movimentacoes["movimento"].str.len() > 0).all()
    # Na página do meio, o ato ordinatório tem o documento vinculado em a.linkMovVincProc.
    assert movimentacoes["movimento"].str.startswith("Ato Ordinatório").any()


def test_cursor_repetido_com_pagina_vazia_encerra_a_busca():
    primeira = _paginas()[0]
    cursor = BeautifulSoup(primeira.text, "html.parser").find("input", id="cursorMovimentacoesPaginado")["value"]
    vazia = Mock(text=f'<tr id="trCursorMovimentacoes" data-cursor="{cursor}"></tr>', status_code=200)
    sessao = Mock()
    sessao.get.side_effect = [primeira, vazia, vazia]
    _completar_movimentacoes(SHOW_SOB_DEMANDA, sessao, BASE, CODIGO)
    assert sessao.get.call_count == 2


def test_ultima_pagina_repetida_com_cursor_novo_encerra_a_busca(tmp_path):
    primeira, meio, ultima = _paginas()
    # A última página volta igual, só com outro cursor.
    repetida = Mock(text=ultima.text + '<tr id="trCursorMovimentacoes" data-cursor="outro-1"></tr>', status_code=200)
    de_novo = Mock(text=ultima.text + '<tr id="trCursorMovimentacoes" data-cursor="outro-2"></tr>', status_code=200)
    sessao = Mock()
    sessao.get.side_effect = [primeira, meio, repetida, de_novo, de_novo]
    arquivo = tmp_path / "processo.html"
    arquivo.write_text(_completar_movimentacoes(SHOW_SOB_DEMANDA, sessao, BASE, CODIGO), encoding="utf-8")
    assert sessao.get.call_count == 4
    assert len(cpopg_parse_single_html(str(arquivo))["movimentacoes"]) == 15


def test_limite_de_paginas_levanta_erro(monkeypatch):
    # Cada página traz linhas novas e um cursor novo: só o limite encerra a busca.
    monkeypatch.setattr("juscraper.courts.tjsp.cpopg_download._LIMITE_PAGINAS_MOVIMENTACOES", 2)
    primeira, meio, _ = _paginas()
    sessao = Mock()
    sessao.get.side_effect = [primeira, meio]
    with pytest.raises(RuntimeError, match="passaram de 2 páginas"):
        _completar_movimentacoes(SHOW_SOB_DEMANDA, sessao, BASE, CODIGO)
    assert sessao.get.call_count == 2
