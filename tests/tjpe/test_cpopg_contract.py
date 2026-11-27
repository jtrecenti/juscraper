"""Contratos offline do ``cpopg`` do TJPE (PJe ConsultaPública + AWS WAF).

O fluxo de busca, detalhe e parse é o da família ``_trf``, também coberto
pelos contratos do TRF1/TRF5; aqui ficam o que o TJPE tem de próprio: o host,
os IDs JSF do formulário do TJPE e o cookie do AWS WAF obtido só quando o
desafio aparece. Todas as respostas são do PJe de 1º grau do TJPE, gravadas
por ``tests/fixtures/capture/tjpe_cpopg.py``: o processo encontrado é uma
execução fiscal pública de um município contra uma pessoa jurídica.
"""
from __future__ import annotations

import errno
import itertools
from pathlib import Path
from urllib.parse import parse_qsl

import pandas as pd
import pytest
import responses

import juscraper as jus
from juscraper.core.exceptions import BloqueioAntiBotWarning
from juscraper.core.waf import USER_AGENT, WAF_COOKIE
from juscraper.courts._trf.download import extract_documento_urls
from juscraper.courts.tjpe.consulta_publica import TJPEConsultaPublicaScraper
from tests._helpers import load_sample, load_sample_bytes

BASE = "https://pje.cloud.tjpe.jus.br/1g/"
LIST_URL = BASE + "ConsultaPublica/listView.seam"
DETAIL_URL = BASE + "ConsultaPublica/DetalheProcessoConsultaPublica/listView.seam"
DOC_URL = BASE + "ConsultaPublica/DetalheProcessoConsultaPublica/documentoSemLoginHTML.seam"
# Corpo da peça: o download só grava os bytes, sem ler o conteúdo, então
# qualquer HTML serve.
DOCUMENTO = b"<html><body><p>Despacho</p></body></html>"
# O processo de ``search_one_result.html`` e ``detail_normal.html``
# (``FOUND_CNJ`` do script de captura).
CNJ = "00147006920218172370"
CNJ_FORMATADO = "0014700-69.2021.8.17.2370"
# Segundo CNJ dos lotes; a busca devolve o mesmo sample.
OUTRO_CNJ = "00000021220248170001"


@pytest.fixture
def tjpe(mocker):
    """``TJPEScraper`` com a consulta pública sem pausa entre requisições."""
    scraper = jus.scraper("tjpe")
    mocker.patch.object(scraper, "_consulta_publica", TJPEConsultaPublicaScraper(sleep_time=0))
    return scraper


@pytest.fixture
def obter(mocker):
    return mocker.patch(
        "juscraper.courts.tjpe.consulta_publica.obter_waf_token", return_value="token-novo"
    )


def _form(status: int = 200):
    responses.add(
        responses.GET,
        LIST_URL,
        body=load_sample_bytes("tjpe", "cpopg/form_initial.html"),
        status=status,
        content_type="text/html;charset=ISO-8859-1",
    )


def _desafio(method: str = responses.GET, url: str = LIST_URL):
    responses.add(
        method,
        url,
        body=load_sample("tjpe", "cpopg/waf_challenge.html"),
        status=202,
        content_type="text/html; charset=UTF-8",
    )


def _busca(sample: str = "cpopg/search_one_result.html"):
    responses.add(
        responses.POST,
        LIST_URL,
        body=load_sample("tjpe", sample),
        content_type="text/xml; charset=utf-8",
    )


def _detalhe():
    responses.add(
        responses.GET,
        DETAIL_URL,
        body=load_sample_bytes("tjpe", "cpopg/detail_normal.html"),
        content_type="text/html",
    )


@responses.activate
def test_cpopg_sem_desafio_nao_chama_o_playwright(tjpe, obter):
    _form()
    _busca()
    _detalhe()

    df = tjpe.cpopg(CNJ)

    obter.assert_not_called()
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["id_cnj"] == CNJ
    assert row["processo"] == CNJ_FORMATADO
    assert row["documentos"]
    assert {"classe", "polo_ativo", "movimentacoes", "documentos"} <= set(df.columns)
    enviado = dict(parse_qsl(responses.calls[1].request.body, keep_blank_values=True))
    assert enviado[
        "fPP:numProcesso-inputNumeroProcessoDecoration:numProcesso-inputNumeroProcesso"
    ] == CNJ_FORMATADO
    # IDs JSF do formulário do TJPE, não os do TRF1; ao recapturar, conferir se mudaram.
    assert enviado["fPP:j_id245"] == "fPP:j_id245"
    assert "fPP:j_id163:processoReferenciaInput" in enviado


@responses.activate
def test_processo_ausente_ou_em_segredo_vira_linha_so_com_id_cnj(tjpe, obter):
    _form()
    _busca("cpopg/search_no_results.html")

    df = tjpe.cpopg(CNJ)

    assert len(df) == 1
    assert df.iloc[0]["id_cnj"] == CNJ
    assert pd.isna(df.iloc[0].get("processo")) or df.iloc[0].get("processo") is None


@responses.activate
def test_desafio_renova_o_cookie_e_repete_a_requisicao(tjpe, obter):
    _desafio()
    _form()
    _busca()
    _detalhe()

    df = tjpe.cpopg(CNJ)

    obter.assert_called_once_with(LIST_URL, tribunal="TJPE")
    assert df.iloc[0]["processo"] is not None
    assert "Cookie" not in responses.calls[0].request.headers
    assert responses.calls[1].request.headers["Cookie"] == f"{WAF_COOKIE}=token-novo"
    assert responses.calls[1].request.url == LIST_URL


@responses.activate
def test_desafio_no_meio_da_conversa_repete_o_mesmo_post(tjpe, obter):
    _form()
    _desafio(responses.POST)
    _busca()
    _detalhe()

    df = tjpe.cpopg(CNJ)

    obter.assert_called_once()
    assert df.iloc[0]["processo"] is not None
    posts = [c.request for c in responses.calls if c.request.method == "POST"]
    assert len(posts) == 2
    assert posts[0].body == posts[1].body


@responses.activate
def test_desafio_repetido_depois_da_renovacao_interrompe_o_lote(tjpe, obter):
    _desafio()
    _desafio()

    with pytest.warns(UserWarning, match=r"TJPEScraper\.cpopg: 2 consulta\(s\) de processo falharam"):
        df = tjpe.cpopg([CNJ, CNJ])

    assert list(df["motivo_falha"]) == ["bloqueio_anti_bot", "bloqueio_anti_bot"]
    obter.assert_called_once()
    assert len(responses.calls) == 2


@responses.activate
def test_desafio_no_meio_do_lote_preserva_as_linhas_anteriores(tjpe, obter):
    _form()
    _busca()
    _detalhe()
    _desafio(responses.POST)
    _desafio(responses.POST)

    with pytest.warns(UserWarning, match="bloqueio_anti_bot"):
        df = tjpe.cpopg([CNJ, CNJ, CNJ])

    assert df.iloc[0]["processo"] is not None
    assert list(df["motivo_falha"]) == [None, "bloqueio_anti_bot", "bloqueio_anti_bot"]
    obter.assert_called_once()
    # form + busca + detalhe + busca desafiada + a mesma busca com o cookie novo.
    assert len(responses.calls) == 5


@responses.activate
def test_sem_playwright_o_erro_chega_ao_usuario(tjpe, mocker):
    mocker.patch(
        "juscraper.courts.tjpe.consulta_publica.obter_waf_token",
        side_effect=ImportError("Instale com `pip install 'juscraper[waf]'`"),
    )
    _desafio()

    # Sem a propagação, o ImportError viraria linha só com id_cnj, como processo ausente.
    with pytest.raises(ImportError, match=r"juscraper\[waf\]"):
        tjpe.cpopg(CNJ)


@responses.activate
def test_sem_playwright_no_download_das_pecas_o_erro_chega_ao_usuario(tjpe, mocker, tmp_path):
    mocker.patch(
        "juscraper.courts.tjpe.consulta_publica.obter_waf_token",
        side_effect=ImportError("Instale com `pip install 'juscraper[waf]'`"),
    )
    _form()
    _busca()
    _detalhe()
    _desafio(url=DOC_URL)

    # Sem a propagação, cada peça viraria warning e ``pecas`` sairia vazia.
    with pytest.raises(ImportError, match=r"juscraper\[waf\]"):
        tjpe.cpopg(CNJ, download_pecas=True, diretorio=str(tmp_path))


@responses.activate
def test_falha_do_navegador_interrompe_o_lote_sem_relancar(tjpe, mocker):
    obter = mocker.patch(
        "juscraper.courts.tjpe.consulta_publica.obter_waf_token",
        side_effect=RuntimeError("O portal do TJPE nao emitiu o cookie aws-waf-token em 60s."),
    )
    _desafio()
    _desafio()

    with pytest.warns(UserWarning, match="bloqueio_anti_bot"):
        df = tjpe.cpopg([CNJ, CNJ])

    assert list(df["motivo_falha"]) == ["bloqueio_anti_bot", "bloqueio_anti_bot"]
    obter.assert_called_once()


@responses.activate
def test_cookie_fica_restrito_ao_host_do_pje(tjpe, obter):
    _desafio()
    _form()
    _busca("cpopg/search_no_results.html")

    tjpe.cpopg(CNJ)

    (cookie,) = [c for c in tjpe._consulta().session.cookies if c.name == WAF_COOKIE]
    assert cookie.domain == "pje.cloud.tjpe.jus.br"


def test_sessao_usa_o_user_agent_do_navegador_que_resolve_o_desafio():
    scraper = TJPEConsultaPublicaScraper(sleep_time=0)
    assert scraper.session.headers["User-Agent"] == USER_AGENT


def test_cjsg_continua_em_sessao_propria():
    # Instância sem a fixture: ela já troca a consulta pública por outra.
    tjpe = jus.scraper("tjpe")
    consulta = tjpe._consulta()
    assert isinstance(consulta, TJPEConsultaPublicaScraper)
    assert tjpe._consulta() is consulta
    assert tjpe.session is not consulta.session
    assert tjpe.session.headers["User-Agent"] != USER_AGENT


@pytest.mark.parametrize(
    "falha",
    [
        pytest.param(1, id="1a_peca-as-seguintes-nao-sao-pedidas"),
        pytest.param(2, id="2a_peca-a-anterior-fica"),
    ],
)
@pytest.mark.usefixtures("obter")
@responses.activate
def test_erro_ao_gravar_peca_vira_falha_do_processo_e_o_lote_segue(tjpe, mocker, tmp_path, caplog, falha):
    """Disco cheio na peça ``falha`` do 1º CNJ: ele sai com o detalhe, as peças já gravadas e o motivo.

    O 2º CNJ sai completo. O processo do sample tem duas peças: falhar na 1ª
    mostra que a 2ª não é pedida; falhar na 2ª, que a 1ª continua em ``pecas``.
    """
    detalhe = load_sample_bytes("tjpe", "cpopg/detail_normal.html")
    ids = [doc_id for _, doc_id in extract_documento_urls(detalhe.decode("latin-1"))]
    assert len(ids) >= 2
    _form()
    for _ in range(2):
        _busca()
        _detalhe()
    for _ in range(falha + len(ids)):
        responses.add(responses.GET, DOC_URL, body=DOCUMENTO, content_type="text/html")
    # Cópia de uma coleta anterior, que a gravação que falha não pode apagar.
    anterior = tmp_path / CNJ / f"{ids[falha - 1]}.html"
    anterior.parent.mkdir()
    anterior.write_bytes(b"coleta anterior")

    gravar = Path.write_bytes
    gravacao = itertools.count(1)

    def disco_cheio(caminho, conteudo):
        if next(gravacao) == falha:
            gravar(caminho, conteudo[:10])  # o disco enche no meio da escrita
            raise OSError(errno.ENOSPC, "No space left on device")
        return gravar(caminho, conteudo)

    mocker.patch.object(Path, "write_bytes", autospec=True, side_effect=disco_cheio)

    with (
        caplog.at_level("WARNING", logger="juscraper._trf"),
        pytest.warns(UserWarning, match="resposta_inesperada") as avisos,
    ):
        df = tjpe.cpopg([CNJ, OUTRO_CNJ], download_pecas=True, diretorio=str(tmp_path))

    primeiro, segundo = df.iloc[0], df.iloc[1]
    assert primeiro["processo"] is not None
    assert primeiro["motivo_falha"] == "resposta_inesperada"
    assert [Path(p).stem for p in primeiro["pecas"]] == ids[: falha - 1]
    assert primeiro["pecas_falhas"] == [
        {"id": i, "motivo_falha": "resposta_inesperada"} for i in ids[falha - 1 :]
    ]
    assert anterior.read_bytes() == b"coleta anterior"
    assert not list(anterior.parent.glob("*.tmp"))
    assert segundo["motivo_falha"] is None
    assert [Path(p).stem for p in segundo["pecas"]] == ids
    assert segundo["pecas_falhas"] == []
    # As peças seguintes do 1º CNJ não são pedidas.
    assert sum(c.request.url.startswith(DOC_URL) for c in responses.calls) == falha + len(ids)
    assert "No space left on device" in caplog.text
    # Um aviso só, o dos processos: as peças que o erro encerrou não se repetem no das peças.
    (aviso,) = avisos
    assert "consulta(s) de processo" in str(aviso.message)
    assert f"processo {CNJ}: resposta_inesperada" in str(aviso.message)


@responses.activate
def test_cpopg_download_devolve_o_html_e_cpopg_parse_monta_a_linha_do_cpopg(tjpe, obter):
    """Baixar e parsear em duas etapas dá a mesma tabela do ``cpopg``, sem ``motivo_falha``."""
    _form()
    _busca()
    _detalhe()
    _busca("cpopg/search_no_results.html")

    htmls = tjpe.cpopg_download([CNJ, OUTRO_CNJ])

    obter.assert_not_called()
    assert htmls[1] is None
    assert CNJ_FORMATADO in htmls[0]
    assert htmls[0] == load_sample_bytes("tjpe", "cpopg/detail_normal.html").decode("latin-1")
    df = tjpe.cpopg_parse(htmls, [CNJ, OUTRO_CNJ])
    assert "motivo_falha" not in df.columns
    assert list(df["id_cnj"]) == [CNJ, OUTRO_CNJ]
    assert df.iloc[0]["processo"] == CNJ_FORMATADO
    assert df.iloc[0]["documentos"]
    assert df.iloc[1].drop("id_cnj").isna().all()

    responses.reset()
    _form()
    _busca()
    _detalhe()
    _busca("cpopg/search_no_results.html")
    completo = tjpe.cpopg([CNJ, OUTRO_CNJ])
    pd.testing.assert_frame_equal(df, completo.drop(columns="motivo_falha"))


@responses.activate
def test_cpopg_download_bloqueado_pelo_waf_sai_none_com_aviso_do_metodo(tjpe, obter):
    _desafio()
    _desafio()

    with pytest.warns(BloqueioAntiBotWarning, match=r"TJPEScraper\.cpopg_download: 2 consulta"):
        htmls = tjpe.cpopg_download([CNJ, OUTRO_CNJ])

    assert htmls == [None, None]
    obter.assert_called_once()


@responses.activate
def test_cpopg_download_sem_playwright_o_erro_chega_ao_usuario(tjpe, mocker):
    mocker.patch(
        "juscraper.courts.tjpe.consulta_publica.obter_waf_token",
        side_effect=ImportError("Instale com `pip install 'juscraper[waf]'`"),
    )
    _desafio()

    with pytest.raises(ImportError, match=r"juscraper\[waf\]"):
        tjpe.cpopg_download(CNJ)


def test_cpopg_download_rejeita_kwarg_desconhecido(tjpe):
    with pytest.raises(TypeError, match=r"^TJPEScraper\.cpopg_download got unexpected keyword"):
        tjpe.cpopg_download(CNJ, filtro_inexistente="x")


def test_cpopg_parse_recusa_listas_de_tamanhos_diferentes(tjpe):
    with pytest.raises(ValueError, match="same length"):
        tjpe.cpopg_parse([None], [CNJ, OUTRO_CNJ])


def test_cpopg_rejeita_kwarg_desconhecido(tjpe):
    with pytest.raises(TypeError, match=r"^TJPEScraper\.cpopg got unexpected keyword"):
        tjpe.cpopg(CNJ, filtro_inexistente="x")


def test_mensagem_de_formulario_inesperado_cita_o_tribunal():
    from juscraper.courts._trf.download import extract_form_field_ids

    with pytest.raises(RuntimeError, match=r"^TJPE: could not locate"):
        extract_form_field_ids("<html></html>", tribunal="TJPE")
