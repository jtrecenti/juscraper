"""Caracterização offline da busca HTML CPOPG e das tentativas de download."""
from unittest.mock import Mock, call

import pytest
import requests

from juscraper.courts.tjsp.cpopg_download import cpopg_download_html_single

CNJ = "1000000-00.2024.8.26.0001"
CNJ_LIMPO = "10000000020248260001"
BASE = "https://esaj.tjsp.jus.br/"
LINKS = ["cpopg/show.do?processo.codigo=PRIMEIRO", "cpopg/show.do?processo.codigo=SEGUNDO"]


@pytest.fixture
def contexto(tmp_path, mocker):
    pausa = mocker.patch("juscraper.courts.tjsp.cpopg_download.time.sleep")
    sessao = Mock()
    resposta = Mock(text="<html>Busca</html>", status_code=503)
    sessao.get.return_value = resposta
    extrair = Mock(return_value=LINKS[:1])
    diretorio = tmp_path / "cpopg" / CNJ_LIMPO
    return sessao, resposta, extrair, pausa, diretorio


def test_link_unico_salva_busca_sem_requisicao_adicional(tmp_path, contexto):
    sessao, resposta, extrair, pausa, diretorio = contexto
    resultado = cpopg_download_html_single(CNJ, sessao, BASE, str(tmp_path), 0.2, extrair)
    assert resultado == str(diretorio)
    assert (diretorio / f"{CNJ_LIMPO}_PRIMEIRO.html").read_text() == resposta.text
    sessao.get.assert_called_once_with(BASE + "cpopg/search.do", params={
        "conversationId": "",
        "cbPesquisa": "NUMPROC",
        "numeroDigitoAnoUnificado": "1000000-00.2024",
        "foroNumeroUnificado": "0001",
        "dadosConsulta.valorConsultaNuUnificado": CNJ,
        "dadosConsulta.valorConsulta": "",
        "dadosConsulta.tipoNuProcesso": "UNIFICADO",
    })
    extrair.assert_called_once_with(resposta)
    pausa.assert_called_once_with(0.2)


def test_cache_html_e_respeitado_antes_da_busca(tmp_path, contexto):
    sessao, _, extrair, pausa, diretorio = contexto
    diretorio.mkdir(parents=True)
    (diretorio / "existente.html").write_text("cache", encoding="utf-8")
    assert cpopg_download_html_single(CNJ, sessao, BASE, str(tmp_path), 0.2, extrair) == str(diretorio)
    sessao.get.assert_not_called()
    extrair.assert_not_called()
    pausa.assert_not_called()


def test_varios_links_baixam_html_individual_em_ordem(tmp_path, contexto):
    sessao, resposta, extrair, _, diretorio = contexto
    extrair.return_value = LINKS
    sessao.get.side_effect = [resposta, Mock(text="Primeiro", status_code=200), Mock(text="Segundo", status_code=200)]
    cpopg_download_html_single(CNJ, sessao, BASE, str(tmp_path), 0, extrair)
    assert sessao.get.call_args_list[1:] == [call(BASE + link) for link in LINKS]
    assert (diretorio / f"{CNJ_LIMPO}_PRIMEIRO.html").read_text() == "Primeiro"
    assert (diretorio / f"{CNJ_LIMPO}_SEGUNDO.html").read_text() == "Segundo"


@pytest.mark.parametrize("links,mensagem", [([], "Nenhum link encontrado"), (["sem-codigo"], "Link sem")])
def test_links_invalidos_nao_repetem_busca(tmp_path, contexto, links, mensagem):
    sessao, _, extrair, pausa, diretorio = contexto
    extrair.return_value = links
    with pytest.raises(RuntimeError, match=mensagem):
        cpopg_download_html_single(CNJ, sessao, BASE, str(tmp_path), 0.2, extrair)
    assert sessao.get.call_count == 1
    assert list(diretorio.iterdir()) == []
    pausa.assert_called_once_with(0.2)


def test_callback_ausente_falha_depois_da_requisicao(tmp_path, contexto):
    sessao, _, _, pausa, _ = contexto
    with pytest.raises(RuntimeError, match="get_links_callback precisa serfornecido"):
        cpopg_download_html_single(CNJ, sessao, BASE, str(tmp_path), 0.2)
    assert sessao.get.call_count == 1
    pausa.assert_called_once_with(0.2)


@pytest.mark.parametrize("erro", [requests.ConnectionError("rede"), ValueError("valor"), OSError("disco")])
def test_cinco_falhas_retornam_diretorio_vazio(tmp_path, contexto, erro):
    sessao, _, extrair, pausa, diretorio = contexto
    sessao.get.side_effect = erro
    assert cpopg_download_html_single(CNJ, sessao, BASE, str(tmp_path), 0.2, extrair) == str(diretorio)
    assert sessao.get.call_count == 5
    assert pausa.call_args_list == [call(0.2)] * 6
    assert list(diretorio.iterdir()) == []
    extrair.assert_not_called()


def test_falha_parcial_repete_busca_e_sobrescreve_arquivo(tmp_path, contexto):
    sessao, resposta, extrair, pausa, diretorio = contexto
    extrair.return_value = LINKS
    sessao.get.side_effect = [
        resposta, Mock(text="Antigo", status_code=200), Mock(status_code=500),
        resposta, Mock(text="Atualizado", status_code=200), Mock(text="Segundo", status_code=200),
    ]
    cpopg_download_html_single(CNJ, sessao, BASE, str(tmp_path), 0.2, extrair)
    assert [chamada.args[0] for chamada in sessao.get.call_args_list] == [
        BASE + "cpopg/search.do", BASE + LINKS[0], BASE + LINKS[1],
    ] * 2
    assert (diretorio / f"{CNJ_LIMPO}_PRIMEIRO.html").read_text() == "Atualizado"
    assert (diretorio / f"{CNJ_LIMPO}_SEGUNDO.html").read_text() == "Segundo"
    assert pausa.call_args_list == [call(0.2)] * 2


def test_codigos_validados_antes_de_baixar_documentos(tmp_path, contexto):
    sessao, _, extrair, _, diretorio = contexto
    extrair.return_value = [LINKS[0], "sem-codigo"]
    with pytest.raises(RuntimeError, match="Link sem"):
        cpopg_download_html_single(CNJ, sessao, BASE, str(tmp_path), 0, extrair)
    assert sessao.get.call_count == 1
    assert list(diretorio.iterdir()) == []
