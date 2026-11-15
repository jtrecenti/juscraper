"""Primitivas de ``juscraper.courts._esaj.pasta`` sobre HTML real do TJSP."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from bs4 import BeautifulSoup

from juscraper.courts._esaj.pasta import (
    DocumentoNaoPdfError,
    PastaInesperadaError,
    documento_vinculado,
    documentos_vinculados,
    gravar_pdf,
    pdf_pela_pasta,
)
from juscraper.courts.tjsp.cpopg_download import caminho_do_documento
from juscraper.courts.tjsp.cpopg_parse import cpopg_parse_single_html
from tests._helpers import PDF_FALSO, load_sample

_SAMPLES = Path(__file__).parent / "samples"


def _link(html):
    return BeautifulSoup(html, "html.parser").a


def test_layout_antigo_separa_publicos_dos_sob_senha():
    """No ``search.html`` (layout com a lista inteira na página), 11 abrem sem senha e 23 pedem senha."""
    documentos = documentos_vinculados(load_sample("tjsp", "cpopg/search.html"))

    assert len(documentos) == 34
    assert sum(d.publico for d in documentos) == 11
    assert len({d.cd_documento for d in documentos}) == 34
    for documento in documentos:
        if documento.url is not None:
            assert documento.url.startswith("cpopg/abrirDocumentoVinculadoMovimentacao.do?")
            assert f"cdDocumento={documento.cd_documento}" in documento.url


def test_parser_e_primitiva_concordam_no_layout_antigo():
    movimentacoes = cpopg_parse_single_html(str(_SAMPLES / "cpopg" / "search.html"))["movimentacoes"]
    com_documento = movimentacoes.dropna(subset=["cd_documento"])

    assert len(movimentacoes) == 118
    assert com_documento["cd_documento"].nunique() == 34
    assert com_documento.drop_duplicates("cd_documento")["documento_publico"].sum() == 11
    assert movimentacoes["caminho_documento"].isna().all()


@pytest.mark.parametrize(
    ("html", "esperado"),
    [
        (
            '<a class="linkMovVincProc" id="linkMovVincProc-2-123" '
            'href="/cpopg/abrirDocumentoVinculadoMovimentacao.do?processo.codigo=X&cdDocumento=123">',
            ("123", "cpopg/abrirDocumentoVinculadoMovimentacao.do?processo.codigo=X&cdDocumento=123"),
        ),
        ('<a class="linkMovVincProc" id="linkMovVincProc-123" href="#liberarAutoPorSenha">', ("123", None)),
        ('<a class="linkMovVincProc" id="linkMovVincProc-123" href="/cpopg/outraRota.do?x=1">', ("123", None)),
        ('<a class="linkMovVincProc" id="linkMovVincProc-123">', ("123", None)),
    ],
)
def test_documento_vinculado_le_codigo_do_id_e_publico_pela_rota(html, esperado):
    documento = documento_vinculado(_link(html))

    assert documento is not None
    assert (documento.cd_documento, documento.url) == esperado


@pytest.mark.parametrize(
    "id_",
    ["linkMovVincProc", "linkMovVincProc-../../x", "linkMovVincProc-12a", "outro-123", None],
)
def test_documento_vinculado_ignora_id_sem_codigo_numerico(id_):
    atributo = f' id="{id_}"' if id_ else ""
    assert documento_vinculado(_link(f'<a class="linkMovVincProc"{atributo} href="#">')) is None


@pytest.mark.parametrize("cd_documento", ["../segredo", "a/b", "..", ""])
def test_caminho_do_documento_recusa_componente_inseguro(tmp_path, cd_documento):
    with pytest.raises(ValueError, match="cdDocumento inválido"):
        caminho_do_documento(tmp_path, cd_documento)


def _get(respostas):
    """``get`` que devolve as respostas em ordem e guarda as URLs pedidas."""
    pedidas = []

    def get(url):
        pedidas.append(url)
        texto, conteudo = respostas.pop(0)
        return SimpleNamespace(text=texto, content=conteudo, url=url, headers={"Content-Type": "text/html"})

    return get, pedidas


def test_pdf_pela_pasta_pede_getpdf_na_raiz_com_os_parametros():
    pasta = load_sample("tjsp", "documentos/pasta_186579563.html")
    get, pedidas = _get([(pasta, b""), ("", PDF_FALSO)])

    assert pdf_pela_pasta(get, "https://h/cpopg/x.do", "https://h/", "186579563") == PDF_FALSO
    assert pedidas[1].startswith("https://h/pastadigital/getPDF.do?")
    assert "cdDocumento=186579563" in pedidas[1]


def test_pdf_pela_pasta_explica_a_recusa_de_acesso():
    get, pedidas = _get([(load_sample("tjsp", "documentos/acesso_nao_validado.html"), b"")])

    with pytest.raises(PastaInesperadaError, match="recusou o acesso") as erro:
        pdf_pela_pasta(get, "https://h/x", "https://h/", "1")

    assert erro.value.motivo == "resposta_inesperada"
    assert len(pedidas) == 1


def test_pdf_pela_pasta_sem_parametros():
    get, _ = _get([("<html>outra coisa</html>", b"")])

    with pytest.raises(PastaInesperadaError, match="não traz 'parametros'"):
        pdf_pela_pasta(get, "https://h/x", "https://h/", "1")


def test_pdf_pela_pasta_recusa_corpo_sem_pdf():
    pasta = load_sample("tjsp", "documentos/pasta_175634201.html")
    get, _ = _get([(pasta, b""), ("", b"<html>erro</html>")])

    with pytest.raises(DocumentoNaoPdfError) as erro:
        pdf_pela_pasta(get, "https://h/x", "https://h/", "175634201")

    assert erro.value.motivo == "nao_pdf"
    assert erro.value.documento == "175634201"


def test_gravar_pdf_nao_deixa_temporario_quando_a_troca_falha(tmp_path, mocker):
    destino = tmp_path / "documentos" / "1.pdf"
    mocker.patch.object(Path, "replace", side_effect=OSError("disco cheio"))

    with pytest.raises(OSError, match="disco cheio"):
        gravar_pdf(PDF_FALSO, destino)

    assert list(destino.parent.iterdir()) == []


def test_gravar_pdf_substitui_o_destino(tmp_path):
    destino = tmp_path / "1.pdf"
    destino.write_bytes(b"velho")

    assert gravar_pdf(PDF_FALSO, destino) == destino
    assert destino.read_bytes() == PDF_FALSO
    assert list(tmp_path.iterdir()) == [destino]
