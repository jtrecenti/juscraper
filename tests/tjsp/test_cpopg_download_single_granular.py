"""Caracterização offline da busca HTML CPOPG e das tentativas de download."""
import logging
import os
from pathlib import Path
from unittest.mock import Mock, call

import pytest
import requests

from juscraper.courts.tjsp.cpopg_download import cpopg_download_html, cpopg_download_html_single

CNJ = "1000000-00.2024.8.26.0001"
CNJ_LIMPO = "10000000020248260001"
BASE = "https://esaj.tjsp.jus.br/"
LINKS = [
    "/cpopg/show.do?localPesquisa.cdLocal=346&processo.codigo=PRIMEIRO&processo.foro=346",
    "/cpopg/show.do?localPesquisa.cdLocal=346&processo.codigo=SEGUNDO&processo.foro=346",
]
# A barra dupla é o comportamento atual: a base termina em barra e o href começa com barra.
URLS_DOCUMENTOS = [
    "https://esaj.tjsp.jus.br//cpopg/show.do?localPesquisa.cdLocal=346&processo.codigo=PRIMEIRO&processo.foro=346",
    "https://esaj.tjsp.jus.br//cpopg/show.do?localPesquisa.cdLocal=346&processo.codigo=SEGUNDO&processo.foro=346",
]


@pytest.fixture
def contexto(tmp_path, mocker):
    pausa = mocker.patch("juscraper.courts.tjsp.cpopg_download.time.sleep")
    sessao = Mock()
    resposta = Mock(text="<html>Busca com acentuação</html>", status_code=200)
    sessao.get.return_value = resposta
    extrair = Mock(return_value=LINKS[:1])
    diretorio = tmp_path / "cpopg" / CNJ_LIMPO
    return sessao, resposta, extrair, pausa, diretorio


def test_link_unico_salva_busca_sem_requisicao_adicional(tmp_path, contexto):
    sessao, resposta, extrair, pausa, diretorio = contexto
    resultado = cpopg_download_html_single(CNJ, sessao, BASE, str(tmp_path), 0.2, extrair)
    assert resultado == str(diretorio)
    assert (diretorio / f"{CNJ_LIMPO}_PRIMEIRO.html").read_text(encoding="utf-8") == resposta.text
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


def test_status_da_busca_nao_e_verificado(tmp_path, contexto):
    sessao, resposta, extrair, pausa, diretorio = contexto
    resposta.status_code = 503
    cpopg_download_html_single(CNJ, sessao, BASE, str(tmp_path), 0.2, extrair)
    assert (diretorio / f"{CNJ_LIMPO}_PRIMEIRO.html").read_text(encoding="utf-8") == resposta.text
    assert sessao.get.call_count == 1
    pausa.assert_called_once_with(0.2)


def test_cache_html_e_respeitado_antes_da_busca(tmp_path, contexto):
    sessao, _, extrair, pausa, diretorio = contexto
    diretorio.mkdir(parents=True)
    (diretorio / "existente.html").write_text("cache", encoding="utf-8")
    assert cpopg_download_html_single(CNJ, sessao, BASE, str(tmp_path), 0.2, extrair) == str(diretorio)
    sessao.get.assert_not_called()
    extrair.assert_not_called()
    pausa.assert_not_called()


def test_cache_html_vazio_nao_e_considerado_download_concluido(tmp_path, contexto):
    sessao, resposta, extrair, pausa, diretorio = contexto
    diretorio.mkdir(parents=True)
    arquivo = diretorio / f"{CNJ_LIMPO}_PRIMEIRO.html"
    arquivo.touch()

    cpopg_download_html_single(CNJ, sessao, BASE, str(tmp_path), 0.2, extrair)

    assert arquivo.read_text(encoding="utf-8") == resposta.text
    sessao.get.assert_called_once()
    extrair.assert_called_once_with(resposta)
    pausa.assert_called_once_with(0.2)


def test_resposta_html_vazia_no_link_unico_falha_sem_arquivo(tmp_path, contexto):
    sessao, _, extrair, pausa, diretorio = contexto
    sessao.get.return_value = Mock(text="", status_code=200)

    with pytest.raises(ValueError, match="Conteúdo HTML vazio"):
        cpopg_download_html_single(CNJ, sessao, BASE, str(tmp_path), 0.2, extrair)

    assert sessao.get.call_count == 5
    assert pausa.call_args_list == [call(0.2)] * 6
    assert list(diretorio.iterdir()) == []


def test_resposta_html_vazia_em_multiplos_links_falha_sem_arquivos(
    tmp_path, contexto,
):
    sessao, resposta, extrair, pausa, diretorio = contexto
    extrair.return_value = LINKS
    sessao.get.side_effect = [
        resposta if indice % 2 == 0 else Mock(text="", status_code=200)
        for indice in range(10)
    ]

    with pytest.raises(ValueError, match="Conteúdo HTML vazio"):
        cpopg_download_html_single(CNJ, sessao, BASE, str(tmp_path), 0.2, extrair)

    assert sessao.get.call_count == 10
    assert pausa.call_args_list == [call(0.2)] * 6
    assert list(diretorio.iterdir()) == []


def test_varios_links_baixam_html_individual_em_ordem(tmp_path, contexto):
    sessao, resposta, extrair, _, diretorio = contexto
    extrair.return_value = LINKS
    sessao.get.side_effect = [resposta, Mock(text="Decisão", status_code=200), Mock(text="Petição", status_code=200)]
    cpopg_download_html_single(CNJ, sessao, BASE, str(tmp_path), 0, extrair)
    assert sessao.get.call_args_list[1:] == [call(url) for url in URLS_DOCUMENTOS]
    assert (diretorio / f"{CNJ_LIMPO}_PRIMEIRO.html").read_text(encoding="utf-8") == "Decisão"
    assert (diretorio / f"{CNJ_LIMPO}_SEGUNDO.html").read_text(encoding="utf-8") == "Petição"


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


@pytest.mark.parametrize("erro", [
    requests.ConnectionError("rede"), ValueError("valor"), OSError("disco"), AttributeError("atributo"),
    UnicodeDecodeError("utf-8", b"\xe9", 0, 1, "byte inválido"),
])
def test_cinco_falhas_propagam_erro_e_nao_retornam_sucesso(tmp_path, contexto, erro):
    sessao, _, extrair, pausa, diretorio = contexto
    sessao.get.side_effect = erro
    with pytest.raises(type(erro)):
        cpopg_download_html_single(CNJ, sessao, BASE, str(tmp_path), 0.2, extrair)
    assert sessao.get.call_count == 5
    assert pausa.call_args_list == [call(0.2)] * 6
    assert list(diretorio.iterdir()) == []
    extrair.assert_not_called()


def test_falha_durante_write_nao_deixa_html_parcial(tmp_path, contexto, mocker):
    sessao, resposta, extrair, pausa, diretorio = contexto
    fdopen_original = os.fdopen

    def fdopen_com_write_falho(fd, *args, **kwargs):
        arquivo_real = fdopen_original(fd, *args, **kwargs)

        class ArquivoComFalha:
            def __enter__(self):
                arquivo_real.__enter__()
                return self

            def __exit__(self, tipo, valor, traceback):
                return arquivo_real.__exit__(tipo, valor, traceback)

            def write(self, conteudo):
                arquivo_real.write(conteudo[:1])
                arquivo_real.flush()
                raise ValueError("falha durante write")

        return ArquivoComFalha()

    mocker.patch("juscraper.courts.tjsp.cpopg_download.os.fdopen", side_effect=fdopen_com_write_falho)

    with pytest.raises(ValueError, match="falha durante write"):
        cpopg_download_html_single(CNJ, sessao, BASE, str(tmp_path), 0.2, extrair)

    assert sessao.get.call_count == 5
    assert pausa.call_args_list == [call(0.2)] * 6
    assert list(diretorio.iterdir()) == []
    assert resposta.text


def test_falha_ao_substituir_html_limpa_temporario(tmp_path, contexto, mocker):
    sessao, _, extrair, pausa, diretorio = contexto
    mocker.patch.object(Path, "replace", side_effect=OSError("falha durante replace"))

    with pytest.raises(OSError, match="falha durante replace"):
        cpopg_download_html_single(CNJ, sessao, BASE, str(tmp_path), 0.2, extrair)

    assert sessao.get.call_count == 5
    assert pausa.call_args_list == [call(0.2)] * 6
    assert list(diretorio.iterdir()) == []


def test_falha_no_fdopen_fecha_descritor_e_limpa_temporario(tmp_path, contexto, mocker):
    sessao, _, extrair, pausa, diretorio = contexto
    fechar_original = os.close
    mocker.patch(
        "juscraper.courts.tjsp.cpopg_download.os.fdopen",
        side_effect=OSError("falha durante fdopen"),
    )
    fechar = mocker.patch(
        "juscraper.courts.tjsp.cpopg_download.os.close",
        wraps=fechar_original,
    )

    with pytest.raises(OSError, match="falha durante fdopen"):
        cpopg_download_html_single(CNJ, sessao, BASE, str(tmp_path), 0.2, extrair)

    assert fechar.call_count == 5
    assert pausa.call_args_list == [call(0.2)] * 6
    assert list(diretorio.iterdir()) == []


def test_lote_continua_apos_cnj_esgotar_tentativas(tmp_path, contexto, caplog):
    sessao, resposta, extrair, _, primeiro_diretorio = contexto
    segundo_cnj = "1000000-00.2024.8.26.0002"
    segundo_limpo = "10000000020248260002"
    segundo_diretorio = tmp_path / "cpopg" / segundo_limpo
    extrair.side_effect = [
        ["/cpopg/show.do?processo.codigo=SEGUNDO"],
    ]
    sessao.get.side_effect = [
        requests.ConnectionError("rede") for _ in range(5)
    ] + [resposta]

    with caplog.at_level(logging.ERROR, logger="juscraper.cpopg_download"):
        cpopg_download_html(
            [CNJ, segundo_cnj],
            sessao,
            BASE,
            str(tmp_path),
            0,
            extrair,
        )

    assert f"Erro ao baixar o processo {CNJ}" in caplog.text
    assert (segundo_diretorio / f"{segundo_limpo}_SEGUNDO.html").exists()
    assert not list(primeiro_diretorio.glob("*.html"))
    assert sessao.get.call_count == 6


def test_falha_parcial_repete_busca_e_sobrescreve_arquivo(tmp_path, contexto):
    sessao, resposta, extrair, pausa, diretorio = contexto
    extrair.return_value = LINKS
    sessao.get.side_effect = [
        resposta, Mock(text="Versão antiga", status_code=200), Mock(status_code=500),
        resposta, Mock(text="Versão atualizada", status_code=200), Mock(text="Petição", status_code=200),
    ]
    cpopg_download_html_single(CNJ, sessao, BASE, str(tmp_path), 0.2, extrair)
    assert [chamada.args[0] for chamada in sessao.get.call_args_list] == [
        BASE + "cpopg/search.do", *URLS_DOCUMENTOS,
    ] * 2
    assert (diretorio / f"{CNJ_LIMPO}_PRIMEIRO.html").read_text(encoding="utf-8") == "Versão atualizada"
    assert (diretorio / f"{CNJ_LIMPO}_SEGUNDO.html").read_text(encoding="utf-8") == "Petição"
    assert pausa.call_args_list == [call(0.2)] * 2


def test_codigos_validados_antes_de_baixar_documentos(tmp_path, contexto):
    sessao, _, extrair, _, diretorio = contexto
    extrair.return_value = [LINKS[0], "sem-codigo"]
    with pytest.raises(RuntimeError, match="Link sem"):
        cpopg_download_html_single(CNJ, sessao, BASE, str(tmp_path), 0, extrair)
    assert sessao.get.call_count == 1
    assert list(diretorio.iterdir()) == []
