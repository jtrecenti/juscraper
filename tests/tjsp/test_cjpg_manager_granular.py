"""Contrato de ``cjpg_parse_manager`` para arquivo, diretório e falhas.

Os HTMLs são montados à mão e mínimos: o que se testa aqui é o que o manager
faz com o resultado ou o erro de cada arquivo, e não a extração dos campos,
coberta em ``test_cjpg_single_granular.py``.
"""
import logging

import pandas as pd
import pytest

from juscraper.courts.tjsp.cjpg_parse import cjpg_parse_manager

_COM_RESULTADO = (
    '<div id="divDadosResultado"><tr class="fundocinza1"><table>'
    '<tr class="fonte"><td><strong>Classe:</strong> {classe}</td></tr>'
    '</table></tr></div>'
)
# Rótulo sem dois-pontos: ``cjpg_parse_single`` levanta ``ValueError``.
_COM_ERRO = (
    '<div id="divDadosResultado"><tr class="fundocinza1"><table>'
    '<tr class="fonte"><td><strong>Classe sem separador</strong></td></tr>'
    '</table></tr></div>'
)
_SEM_RESULTADO = '<div id="divDadosResultado"></div>'


def _gravar(caminho, html):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(html, encoding="utf-8")
    return caminho


def test_arquivo_unico_devolve_os_resultados(tmp_path):
    arquivo = _gravar(tmp_path / "pagina.html", _COM_RESULTADO.format(classe="A"))

    pd.testing.assert_frame_equal(cjpg_parse_manager(arquivo), pd.DataFrame([{"classe": "A"}]))


def test_arquivo_unico_com_erro_propaga_o_erro_do_parser(tmp_path):
    """Sem diretório não há o que descartar: o erro original sobe sem embrulho."""
    arquivo = _gravar(tmp_path / "ruim.html", _COM_ERRO)

    with pytest.raises(ValueError, match="unpack"):
        cjpg_parse_manager(arquivo)


def test_diretorio_descarta_arquivo_com_erro_e_registra_no_log(tmp_path, caplog):
    """Percorre subdiretórios, aceita ``.htm``, junta o que deu certo e renumera o índice."""
    _gravar(tmp_path / "pagina_1.html", _COM_RESULTADO.format(classe="A"))
    _gravar(tmp_path / "lote" / "pagina_2.htm", _COM_RESULTADO.format(classe="B"))
    _gravar(tmp_path / "lote" / "ruim.html", _COM_ERRO)

    with caplog.at_level(logging.ERROR, logger="juscraper.cjpg_parse"):
        resultado = cjpg_parse_manager(tmp_path)

    assert sorted(resultado["classe"]) == ["A", "B"]
    assert list(resultado.index) == [0, 1]
    assert [r.getMessage() for r in caplog.records if "ruim.html" in r.getMessage()]


def test_diretorio_sem_html_devolve_dataframe_vazio(tmp_path):
    """Subdiretório com nome de HTML não é arquivo e não conta como falha."""
    _gravar(tmp_path / "notas.txt", "nada a processar")
    (tmp_path / "lote.html").mkdir()

    pd.testing.assert_frame_equal(cjpg_parse_manager(tmp_path), pd.DataFrame())


def test_diretorio_so_com_paginas_sem_resultado_devolve_vazio(tmp_path):
    """Página lida sem resultados não é falha, mesmo quando é a única."""
    _gravar(tmp_path / "pagina_1.html", _SEM_RESULTADO)

    assert cjpg_parse_manager(tmp_path).empty


def test_diretorio_so_com_pagina_vazia_e_arquivo_com_erro_devolve_vazio(tmp_path):
    """Uma página lida sem resultados basta para a falha não ser total."""
    _gravar(tmp_path / "pagina_1.html", _SEM_RESULTADO)
    _gravar(tmp_path / "ruim.html", _COM_ERRO)

    assert cjpg_parse_manager(tmp_path).empty


def test_diretorio_em_que_todos_os_arquivos_falham_levanta_erro(tmp_path):
    """Falha total não pode sair como DataFrame vazio, igual a busca sem resultado.

    A ordem do ``rglob`` depende do sistema de arquivos, então a mensagem pode
    citar qualquer um dos dois arquivos; o teste exige o nome e o erro dele.
    """
    _gravar(tmp_path / "ruim_1.html", _COM_ERRO)
    _gravar(tmp_path / "ruim_2.html", _COM_ERRO)

    with pytest.raises(
        ValueError,
        match=r"Nenhum dos 2 arquivo\(s\) em .+ pôde ser processado\. "
        r"Primeiro erro, em ruim_[12]\.html: not enough values to unpack",
    ) as excecao:
        cjpg_parse_manager(tmp_path)

    assert isinstance(excecao.value.__cause__, ValueError)
    assert "unpack" in str(excecao.value.__cause__)


def test_caminho_inexistente_levanta_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError, match=r"Caminho não encontrado ou inacessível: .*nao_existe"):
        cjpg_parse_manager(tmp_path / "nao_existe")
