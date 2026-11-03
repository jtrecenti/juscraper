"""Contratos offline de ``TJSPScraper.baixar_sentenca`` e ``baixar_sentencas``.

As linhas vêm do parser do cjpg sobre a captura real
``samples/cjpg/results_normal_page_01.html``. ``cjpg/obterArquivo.do``
redireciona (302) para a pasta gravada em
``samples/documentos/pasta_167379827.html``, e ``getPDF.do`` sai com os
``parametros`` dela.
"""

import json
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import pandas as pd
import pytest
import responses
from responses.matchers import query_param_matcher

import juscraper as jus
from juscraper.core.base import _texto_ausente_como_none
from juscraper.courts._esaj.acordao import EntradaInvalidaError
from juscraper.courts._esaj.pasta import DocumentoNaoPdfError, parse_parametros_pasta
from juscraper.courts.tjsp.cjpg_parse import _codigos_inteiro_teor, cjpg_parse_single
from tests._helpers import PDF_FALSO, load_sample, load_sample_bytes

ESAJ = "https://esaj.tjsp.jus.br"
CD_PROCESSO, CD_FORO, CD_DOCUMENTO = "3I0006RUY0000", "126", "167379827"
_PASTA = json.loads(load_sample("tjsp", "documentos/redirecionamentos.json"))[f"sentenca_{CD_DOCUMENTO}"]


def _cjpg():
    """A tabela como ``cjpg()`` a devolve: o embrulho público troca o ausente por ``None``."""
    return _texto_ausente_como_none(
        cjpg_parse_single(Path(__file__).parent / "samples" / "cjpg" / "results_normal_page_01.html")
    )


def _registrar_sentenca(cd_documento=CD_DOCUMENTO, pdf=PDF_FALSO):
    responses.add(
        responses.GET,
        f"{ESAJ}/cjpg/obterArquivo.do",
        status=302,
        headers={"Location": _PASTA},
        match=[query_param_matcher({"cdDocumento": cd_documento}, strict_match=False)],
    )
    responses.add(
        responses.GET,
        _PASTA.split("?")[0],
        body=load_sample_bytes("tjsp", f"documentos/pasta_{CD_DOCUMENTO}.html"),
        content_type="text/html;charset=UTF-8",
        match=[query_param_matcher(dict(parse_qsl(urlsplit(_PASTA).query, keep_blank_values=True)))],
    )
    parametros = parse_parametros_pasta(load_sample("tjsp", f"documentos/pasta_{CD_DOCUMENTO}.html"))
    responses.add(
        responses.GET,
        f"{ESAJ}/pastadigital/getPDF.do",
        body=pdf,
        match=[query_param_matcher(dict(parse_qsl(parametros, keep_blank_values=True)))],
    )


def _pedidos(rota):
    return [c.request for c in responses.calls if c.request.url.split("?")[0].endswith(rota)]


def test_cjpg_traz_os_quatro_codigos_do_inteiro_teor():
    linha = _cjpg().iloc[0]

    assert (linha.cd_processo, linha.cd_foro, linha.nm_alias, linha.cd_documento) == (
        CD_PROCESSO,
        CD_FORO,
        None,
        CD_DOCUMENTO,
    )


@pytest.mark.parametrize(
    ("nome", "esperado"),
    [
        ("A1-2-PG5-3", ("A1", "2", "PG5", "3")),
        ("A1-2--3", ("A1", "2", None, "3")),
        ("A1-2", ("A1", None, None, None)),
        (None, (None, None, None, None)),
        ("", (None, None, None, None)),
    ],
)
def test_codigos_inteiro_teor(nome, esperado):
    codigos = _codigos_inteiro_teor(nome)

    assert tuple(codigos.values()) == esperado
    assert list(codigos) == ["cd_processo", "cd_foro", "nm_alias", "cd_documento"]


@responses.activate
def test_baixar_sentenca_pede_obter_arquivo_com_os_quatro_codigos(tmp_path, mocker):
    mocker.patch("time.sleep")
    _registrar_sentenca()
    linha = _cjpg().iloc[0]

    caminho = jus.scraper("tjsp", download_path=str(tmp_path / "padrao")).baixar_sentenca(
        linha.cd_processo, linha.cd_foro, linha.cd_documento, linha.nm_alias, diretorio=str(tmp_path / "destino")
    )

    assert caminho == str(tmp_path / "destino" / "sentencas" / f"{CD_PROCESSO}_{CD_DOCUMENTO}.pdf")
    assert Path(caminho).read_bytes() == PDF_FALSO
    (pedido,) = _pedidos("obterArquivo.do")
    assert dict(parse_qsl(urlsplit(pedido.url).query, keep_blank_values=True)) == {
        "cdProcesso": CD_PROCESSO,
        "cdForo": CD_FORO,
        "nmAlias": "",
        "cdDocumento": CD_DOCUMENTO,
    }
    assert len(_pedidos("getPDF.do")) == 1
    assert not (tmp_path / "padrao").exists()


@responses.activate
def test_baixar_sentenca_usa_download_path_sem_diretorio(tmp_path, mocker):
    mocker.patch("time.sleep")
    _registrar_sentenca()

    caminho = jus.scraper("tjsp", download_path=str(tmp_path)).baixar_sentenca(CD_PROCESSO, CD_FORO, CD_DOCUMENTO)

    assert caminho == str(tmp_path / "sentencas" / f"{CD_PROCESSO}_{CD_DOCUMENTO}.pdf")


@responses.activate
def test_baixar_sentenca_espaca_os_pedidos(tmp_path, mocker):
    """Os dois pedidos da sentença respeitam ``sleep_time``, como os do acórdão."""
    sleep = mocker.patch("juscraper.courts._esaj.base.time.sleep")
    _registrar_sentenca()
    scraper = jus.scraper("tjsp", download_path=str(tmp_path), sleep_time=3)

    scraper.baixar_sentenca(CD_PROCESSO, CD_FORO, CD_DOCUMENTO)

    assert sleep.call_count == 1
    assert 0 < sleep.call_args.args[0] <= 3


@responses.activate
def test_baixar_sentenca_recusa_corpo_sem_pdf(tmp_path, mocker):
    mocker.patch("time.sleep")
    _registrar_sentenca(pdf=b"<html>erro</html>")

    with pytest.raises(DocumentoNaoPdfError):
        jus.scraper("tjsp", download_path=str(tmp_path)).baixar_sentenca(CD_PROCESSO, CD_FORO, CD_DOCUMENTO)

    assert not list(tmp_path.rglob("*.pdf"))


@pytest.mark.parametrize(
    ("campo", "valores"),
    [
        ("cd_processo", ("../x", CD_FORO, CD_DOCUMENTO, None)),
        ("cd_foro", (CD_PROCESSO, "12a", CD_DOCUMENTO, None)),
        ("cd_documento", (CD_PROCESSO, CD_FORO, "", None)),
        ("cd_documento", (CD_PROCESSO, CD_FORO, float("nan"), None)),
        ("nm_alias", (CD_PROCESSO, CD_FORO, CD_DOCUMENTO, "PG5&x=1")),
    ],
)
@responses.activate
def test_baixar_sentenca_recusa_codigo_fora_do_formato_sem_pedido(tmp_path, campo, valores):
    with pytest.raises(EntradaInvalidaError, match=f"{campo} inválido"):
        jus.scraper("tjsp", download_path=str(tmp_path)).baixar_sentenca(*valores)

    assert len(responses.calls) == 0


@responses.activate
def test_baixar_sentencas_por_linha_com_falhas_num_aviso(tmp_path, mocker):
    mocker.patch("time.sleep")
    _registrar_sentenca()
    cjpg = _cjpg().head(3).copy()
    # Linha 2: a pasta não abre. Linha 3: código adulterado, sem pedido.
    responses.add(
        responses.GET,
        f"{ESAJ}/cjpg/obterArquivo.do",
        body="<html>sem pasta</html>",
        match=[query_param_matcher({"cdDocumento": cjpg.iloc[1].cd_documento}, strict_match=False)],
    )
    cjpg.loc[cjpg.index[2], "cd_foro"] = "x"

    with pytest.warns(UserWarning, match="download\\(s\\) de sentença") as avisos:
        resultado = jus.scraper("tjsp", download_path=str(tmp_path)).baixar_sentencas(cjpg)

    assert list(resultado.columns) == [*cjpg.columns, "caminho_sentenca", "motivo_falha"]
    assert resultado["caminho_sentenca"].tolist() == [
        str(tmp_path / "sentencas" / f"{CD_PROCESSO}_{CD_DOCUMENTO}.pdf"),
        None,
        None,
    ]
    assert resultado["motivo_falha"].tolist() == [None, "resposta_inesperada", "entrada_invalida"]
    assert len(_pedidos("obterArquivo.do")) == 2
    mensagem = str(avisos[0].message)
    assert f"{cjpg.iloc[1].cd_processo}/{cjpg.iloc[1].cd_documento}: resposta_inesperada" in mensagem
    pd.testing.assert_frame_equal(resultado[cjpg.columns], cjpg)


@responses.activate
def test_baixar_sentencas_erro_de_rede_vira_motivo(tmp_path, mocker):
    mocker.patch("time.sleep")
    cjpg = _cjpg().head(1)
    responses.add(responses.GET, f"{ESAJ}/cjpg/obterArquivo.do", status=404)

    with pytest.warns(UserWarning, match="http_404"):
        resultado = jus.scraper("tjsp", download_path=str(tmp_path)).baixar_sentencas(cjpg)

    assert resultado["motivo_falha"].tolist() == ["http_404"]


def test_baixar_sentencas_exige_as_colunas_dos_codigos(tmp_path):
    cjpg = _cjpg().drop(columns=["cd_foro", "nm_alias"])

    with pytest.raises(ValueError, match="cd_foro"):
        jus.scraper("tjsp", download_path=str(tmp_path)).baixar_sentencas(cjpg)
