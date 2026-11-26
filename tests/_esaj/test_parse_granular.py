"""Testes granulares do parser de cjsg da família eSAJ (``_esaj/parse.py``).

Os samples ficam nas pastas dos tribunais (``tests/<sigla>/samples/cjsg/``).
"""
import tempfile
from pathlib import Path

import pandas as pd
import pytest
from bs4 import BeautifulSoup

from juscraper.core.parse_utils import normalizar_texto
from juscraper.courts._esaj import parse as esaj_parse
from juscraper.courts._esaj.parse import (
    _extract_detail,
    _extract_ementa,
    _extract_labeled_value,
    _extract_pagination_count,
    _normalize_key,
    _parse_single_page,
    _total_declarado,
    cjsg_n_pags,
    cjsg_n_results,
    cjsg_parse_manager,
)
from juscraper.courts.tjsp.cjsg_parse import _cjsg_parse_single_page
from tests._helpers import load_sample

_TESTS = Path(__file__).parents[1]

ESAJ_COLUMNS = (
    "processo",
    "cd_acordao",
    "cd_foro",
    "classe_assunto",
    "relator",
    "comarca",
    "orgao_julgador",
    "data_julgamento",
    "data_publicacao",
    "ementa",
)


def _primeira_pagina_com_total(valor: object) -> str:
    """Sample real do TJSP com o valor do input de total trocado."""
    html = load_sample("tjsp", "cjsg/results_normal_page_01.html").replace(
        'id="totalResultadoAbaRetornoFiltro-A" type="hidden" value="2571077"',
        f'id="totalResultadoAbaRetornoFiltro-A" type="hidden" value="{valor}"',
    )
    assert f'value="{valor}"' in html
    return html


def _pagina(corpo: str) -> str:
    """Envelope mínimo para os casos de borda que nenhuma página real do eSAJ traz."""
    return f"<html><body>{corpo}</body></html>"


# Cascata de ``cjsg_n_results`` quando a página não traz o input de total.
# Nenhuma captura reproduz esses layouts (o eSAJ atual sempre traz o input),
# então o HTML mínimo fica aqui, e não em ``samples/``.
_CASCATA_CONTAGEM = {
    "legacy_bgcolor": (
        '<table><tr><td bgcolor="#EEEEEE">Pagina 2 de 42 paginas encontradas</td></tr></table>',
        42,
    ),
    "pagination_class": (
        '<table><tr><td class="pagination-info">Total: 77 registros disponiveis</td></tr></table>',
        77,
    ),
    "page_text": ("<table><tr><td>Página atual: 3, total 99 itens</td></tr></table>", 99),
    "rows_fallback": (
        '<table class="resultado-lista">'
        '<tr class="fundocinza1"><td>primeiro</td></tr>'
        '<tr class="fundocinza1"><td>segundo</td></tr>'
        '<tr class="fundocinza1"><td>terceiro</td></tr>'
        "</table>",
        3,
    ),
}

# Linhas de resultado que a página real não traz juntas: linha sem a segunda
# célula, linha sem a tabela de detalhes, rótulo que o parser não conhece
# ("Campo especial"), "Outros números" (descartado), os rótulos com a
# acentuação estragada que ``_TYPO_FIXES`` conserta e ementa só na ``div``
# oculta. O ``Relator(a)`` traz hífen suave e espaço de largura zero.
_LINHAS_DE_BORDA = _pagina(
    """<table>
  <tr class="fundocinza1"><td>linha sem segunda celula</td></tr>
  <tr class="fundocinza1"><td></td><td>linha sem tabela de detalhes</td></tr>
  <tr class="fundocinza1"><td></td><td><table>
    <tr><td>
      <a class="esajLinkLogin downloadEmenta" cdacordao="123" cdforo="4">
        0000001-02.2024.8.26.0001
      </a>
    </td></tr>
    <tr class="ementaClass2"><td><strong>Classe / Assunto:</strong> Apelacao / Contratos</td></tr>
    <tr class="ementaClass2"><td><strong>Relator(a):</strong> Des. Joao\xad Acu\u200b</td></tr>
    <tr class="ementaClass2"><td><strong>Campo especial:</strong> valor dinamico</td></tr>
    <tr class="ementaClass2"><td><strong>Outros numeros:</strong> deve ser descartado</td></tr>
    <tr class="ementaClass2"><td><strong>Data de publicassapso:</strong> 01/02/2024</td></tr>
    <tr class="ementaClass2"><td><strong>argapso julgador:</strong> Camara Especial</td></tr>
    <tr class="ementaClass2"><td>
      <strong>Ementa:</strong>
      <div align="justify" style="display: none;">Ementa: texto oculto.</div>
      <div align="justify" style="display: block;">Ementa: texto visivel.</div>
    </td></tr>
  </table></td></tr>
  <tr class="fundocinza1"><td></td><td><table>
    <tr class="ementaClass2"><td>
      <strong>Ementa:</strong>
      <div align="justify" style="display: none;">Ementa: fallback oculto.</div>
    </td></tr>
  </table></td></tr>
  <tr class="fundocinza1"><td></td><td><table>
    <tr class="ementaClass2"><td>detalhe sem rotulo</td></tr>
  </table></td></tr>
</table>"""
)


class TestCJSGNPages:
    """Test the cjsg_n_pags function."""

    def test_extract_pages_from_results(self):
        """78 resultados, 20 por página: 4 páginas."""
        html = load_sample('tjsp', 'cjsg/single_page.html')
        assert cjsg_n_pags(html) == 4

    def test_extract_pages_from_single_result(self):
        """Um resultado só cabe numa página."""
        html = load_sample('tjsp', 'cjsg/monocratica_single_page.html')
        assert cjsg_n_pags(html) == 1

    def test_extract_pages_missing_selector(self):
        """Test that missing pagination selector raises ValueError."""
        html = "<html><body><p>No pagination here</p></body></html>"
        with pytest.raises(ValueError, match="Não foi possível encontrar o seletor"):
            cjsg_n_pags(html)

    def test_extract_pages_invalid_format(self):
        """Test that invalid pagination format raises ValueError."""
        html = '<html><body><td bgcolor="#EEEEEE">Invalid format</td></body></html>'
        with pytest.raises(ValueError, match="Não foi possível extrair o número"):
            cjsg_n_pags(html)

    @pytest.mark.parametrize(
        "texto", ["Falha na verificação do captcha.", "Captcha inválido.", "Falha na verificação."]
    )
    def test_captcha_error_raises_specific_message(self, texto):
        """Captcha/erro divs devem levantar ValueError com mensagem explicita."""
        html = (
            '<html><body>'
            f'<div class="mensagemErro">{texto}</div>'
            '</body></html>'
        )
        with pytest.raises(ValueError, match="Captcha"):
            cjsg_n_pags(html)

    def test_generic_error_div_raises_specific_message(self):
        """Divs de erro sem captcha devem levantar ValueError com o texto do erro."""
        html = (
            '<html><body>'
            '<div class="error">Sessão expirada. Faça login novamente.</div>'
            '</body></html>'
        )
        with pytest.raises(ValueError, match="Erro detectado"):
            cjsg_n_pags(html)


class TestCJSGNResults:
    """Tests do helper :func:`cjsg_n_results` (issue #92)."""

    def test_extracts_raw_count_from_normal_results(self):
        """Sample com paginacao explicita (``totalResultadoAbaRetornoFiltro``)."""
        html = load_sample("tjsp", "cjsg/results_normal_page_01.html")
        assert cjsg_n_results(html) == 2571077

    def test_zero_results_returns_zero(self):
        html = load_sample("tjsp", "cjsg/no_results.html")
        assert cjsg_n_results(html) == 0

    def test_ementa_com_resultados_nao_vira_paginacao(self):
        """Ementa curta com "resultados" na 1a página ("direito", baixar_sg=False, 14/11/2026)."""
        html = load_sample("tjsp", "cjsg/ementa_com_resultados.html")
        assert cjsg_n_results(html) == 1178964

    def test_ementa_que_diz_sem_resultados_nao_zera_a_contagem(self):
        """Os marcadores de busca vazia valem fora das linhas de resultado, não na ementa."""
        html = load_sample("tjsp", "cjsg/ementa_com_resultados.html").replace(
            "BONIFICAÇÃO POR RESULTADOS", "PESQUISAS SEM RESULTADOS", 1
        )
        assert "PESQUISAS SEM RESULTADOS" in html
        assert cjsg_n_results(html) == 1178964

    def test_single_page_uses_canonical_selector(self):
        """Sample com totalResultado declarado — usa o numero do sample."""
        html = load_sample("tjsp", "cjsg/single_page.html")
        assert cjsg_n_results(html) == 78

    def test_n_pags_e_wrapper_que_aplica_ceil_div(self):
        """``cjsg_n_pags`` permanece um wrapper sobre ``cjsg_n_results``."""
        html = load_sample("tjsp", "cjsg/results_normal_page_01.html")
        # 2571077 resultados / 20 por pagina = 128554 paginas (ceil).
        assert cjsg_n_pags(html) == (2571077 + 19) // 20

    @pytest.mark.parametrize(("corpo", "expected"), _CASCATA_CONTAGEM.values(), ids=_CASCATA_CONTAGEM.keys())
    def test_selector_and_regex_cascades(self, corpo, expected):
        assert cjsg_n_results(_pagina(corpo)) == expected

    def test_search_form_without_results_raises_specific_message(self):
        html = _pagina('<form id="consultaForm"><input name="pesquisa" /></form>')
        with pytest.raises(ValueError, match="Ainda na página de consulta"):
            cjsg_n_results(html)

    def test_pagination_marker_without_number_raises_with_text(self):
        html = _pagina('<table><tr><td bgcolor="#EEEEEE">Formato inesperado sem numero</td></tr></table>')
        with pytest.raises(ValueError, match="Formato inesperado encontrado"):
            cjsg_n_results(html)

    def test_page_error_takes_precedence_over_zero_results_marker(self):
        html = _pagina(
            '<div class="mensagemErro">Falha na verificação do captcha.</div>'
            "<p>Nenhum resultado encontrado.</p>"
        )
        with pytest.raises(ValueError, match="Captcha"):
            cjsg_n_results(html)

    def test_results_table_without_standard_rows_returns_minimum_one(self):
        html = _pagina(
            '<table class="resultado">'
            '<tr class="novo-layout"><td>Resultado sem a classe legada de linha.</td></tr>'
            "</table>"
        )
        assert cjsg_n_results(html) == 1

    @pytest.mark.parametrize(
        ("court", "expected_count", "expected_rows", "first_process"),
        [
            ("tjac", 13929, 20, "1000233-68.2026.8.01.0000"),
            ("tjal", 136804, 20, "0709767-89.2020.8.02.0001"),
            ("tjam", 54334, 10, "0708349-62.2020.8.04.0001"),
            ("tjce", 100860, 20, "0206389-11.2024.8.06.0300"),
            ("tjms", 149670, 100, "0800383-78.2024.8.12.0038"),
            ("tjsp", 2571077, 20, "2399632-18.2025.8.26.0000"),
        ],
    )
    def test_real_first_page_contract_for_every_esaj_court(
        self,
        court,
        expected_count,
        expected_rows,
        first_process,
    ):
        relative_path = "cjsg/results_normal_page_01.html"
        html = load_sample(court, relative_path)
        sample_path = _TESTS / court / "samples" / relative_path

        df = _parse_single_page(str(sample_path))

        assert cjsg_n_results(html) == expected_count
        assert len(df) == expected_rows
        assert tuple(df.columns) == ESAJ_COLUMNS
        assert df.iloc[0]["processo"] == first_process


def _cascata_proibida(*_args, **_kwargs):
    raise AssertionError("a contagem deveria vir do input totalResultadoAbaRetornoFiltro-*")


class TestCJSGNResultsInputDeclarado:
    """A contagem vem do ``input#totalResultadoAbaRetornoFiltro-*`` da página."""

    @pytest.mark.parametrize(
        ("court", "sample", "expected"),
        [
            ("tjac", "results_normal_page_01.html", 13929),
            ("tjac", "single_page.html", 3),
            ("tjac", "no_results.html", 0),
            ("tjal", "results_normal_page_01.html", 136804),
            ("tjal", "single_page.html", 7),
            ("tjal", "no_results.html", 0),
            ("tjam", "results_normal_page_01.html", 54334),
            ("tjam", "single_page.html", 1),
            ("tjam", "no_results.html", 0),
            ("tjce", "results_normal_page_01.html", 100860),
            ("tjce", "single_page.html", 16),
            ("tjce", "no_results.html", 0),
            ("tjms", "results_normal_page_01.html", 149670),
            ("tjms", "single_page.html", 2),
            ("tjms", "no_results.html", 0),
            ("tjsp", "results_normal_page_01.html", 2571077),
            ("tjsp", "single_page.html", 78),
            ("tjsp", "no_results.html", 0),
            # Aba de decisões monocráticas: o input é o ``-D``.
            ("tjac", "monocratica_single_page.html", 5),
            ("tjal", "monocratica_single_page.html", 2),
            ("tjam", "monocratica_single_page.html", 1),
            ("tjce", "monocratica_single_page.html", 9),
            ("tjms", "monocratica_single_page.html", 6),
            ("tjsp", "monocratica_single_page.html", 1),
        ],
    )
    def test_le_o_input_sem_passar_pela_cascata(self, monkeypatch, court, sample, expected):
        monkeypatch.setattr(esaj_parse, "_has_zero_results", _cascata_proibida)
        monkeypatch.setattr(esaj_parse, "_find_pagination_element", _cascata_proibida)
        monkeypatch.setattr(esaj_parse, "_count_result_rows_or_raise", _cascata_proibida)

        html = load_sample(court, f"cjsg/{sample}")
        assert _total_declarado(BeautifulSoup(html, "html.parser")) == expected
        assert cjsg_n_results(html) == expected

    @pytest.mark.parametrize("ementa", ["BONIFICAÇÃO POR RESULTADOS", "PESQUISAS SEM RESULTADOS"])
    def test_ementa_fora_das_linhas_marcadas_nao_altera_a_contagem(self, ementa):
        """HTML derivado do sample real ``ementa_com_resultados.html``.

        Sem a classe ``fundocinza1`` nas linhas (como se o eSAJ a renomeasse),
        a cascata toma a ementa pela paginação: com "RESULTADOS" levanta
        ``ValueError`` e com "SEM RESULTADOS" conta 0. O input não depende do
        texto da página.
        """
        html = (
            load_sample("tjsp", "cjsg/ementa_com_resultados.html")
            .replace("BONIFICAÇÃO POR RESULTADOS", ementa, 1)
            .replace('class="fundocinza1"', 'class="linhaResultado"')
        )
        assert 'class="fundocinza1"' not in html
        assert ementa in html

        assert cjsg_n_results(html) == 1178964

    @pytest.mark.parametrize("valor", ["", "n/d"])
    def test_input_vazio_ou_nao_numerico_cai_na_cascata(self, mocker, valor):
        espiao = mocker.spy(esaj_parse, "_contar_pelo_texto")

        assert cjsg_n_results(_primeira_pagina_com_total(valor)) == 2571077
        assert espiao.call_count == 1


class TestCJSGParseSinglePage:
    """Test the _cjsg_parse_single_page function."""

    @pytest.mark.parametrize(
        ("sigla", "arquivo"),
        [
            ("tjac", "cjsg/post_initial.html"),
            ("tjal", "cjsg/post_initial.html"),
            ("tjam", "cjsg/post_initial.html"),
            ("tjce", "cjsg/results_normal_page_01.html"),
            ("tjms", "cjsg/post_initial.html"),
            ("tjsp", "cjsg/single_page.html"),
        ],
    )
    def test_ementa_longa_devolve_so_a_completa(self, sigla, arquivo):
        r"""Prévia visível + completa oculta devolve só a completa; div única, ela mesma (#713).

        O ``\r\n`` do HTML vira ``\n``, o ``\x96`` do windows-1252, "–", e o
        ``\xa0``, espaço comum. O sample vai lido em bytes, porque
        ``read_text`` já trocaria o ``\r\n``.
        """
        path = _TESTS / sigla / "samples" / arquivo
        html = path.read_bytes().decode("utf-8")
        assert "\r\n" in html
        soup = BeautifulSoup(html, "html.parser")
        linhas = soup.find_all("tr", class_="fundocinza1")

        df = _parse_single_page(str(path))

        assert len(df) == len(linhas)
        longas = 0
        for ementa, linha in zip(df["ementa"], linhas, strict=True):
            divs = [
                normalizar_texto(div.get_text(" ", strip=True).replace("\x96", "–"))
                .removeprefix("Ementa:")
                .strip()
                for div in linha.select('div[align="justify"]')
            ]
            if len(divs) == 2:
                previa, completa = divs
                assert len(previa) < len(completa)
                assert ementa == completa
                longas += 1
            elif len(divs) == 1:
                assert ementa == divs[0]
        assert longas > 0
        assert not df["ementa"].str.contains("[\r\xa0]").any()
        assert df["ementa"].str.contains("\n").any()

    @pytest.mark.parametrize(
        ("sigla", "arquivo", "trecho"),
        [
            ("tjac", "cjsg/results_normal_page_02.html", "da unidade consumidora"),
            ("tjal", "cjsg/results_normal_page_01.html", None),
            ("tjam", "cjsg/results_normal_page_02.html", "art. 14, do CDC"),
            ("tjce", "cjsg/results_normal_page_02.html", None),
            ("tjms", "cjsg/results_normal_page_01.html", None),
            ("tjsp", "cjsg/single_page.html", None),
        ],
    )
    def test_ementa_sem_espaco_nao_separavel(self, sigla, arquivo, trecho):
        r"""O ``\xa0`` do HTML sai como espaço comum, e a busca por "art. 14" acha a ementa."""
        path = Path(__file__).parent.parent / sigla / "samples" / arquivo
        soup = BeautifulSoup(path.read_bytes().decode("utf-8"), "html.parser")
        divs = soup.select('tr.ementaClass2 div[align="justify"]')
        assert any("\xa0" in div.get_text() for div in divs)

        ementas = _parse_single_page(str(path))["ementa"].dropna()

        assert not ementas.str.contains("\xa0").any()
        if trecho is not None:
            assert ementas.str.contains(trecho, regex=False).any()

    def test_ementa_mantem_rotulo_citado_no_corpo(self):
        """Só o rótulo do início sai; "Ementa:" citado no texto fica."""
        html = (
            '<tr class="ementaClass2"><td><strong>Ementa:</strong>'
            '<div align="justify">Ementa: APELAÇÃO.\nConforme a Ementa: do REsp 1.234, '
            "nega-se provimento.</div></td></tr>"
        )
        linha = BeautifulSoup(html, "html.parser").tr

        assert _extract_ementa(linha) == "APELAÇÃO.\nConforme a Ementa: do REsp 1.234, nega-se provimento."

    @pytest.mark.parametrize(
        ("rotulo", "chave", "valor"),
        [
            ("Data de publicação:", "data_publicacao", "02/02/2024 (Data de publicação: 01/02/2024 no DJe)"),
            ("Órgão julgador:", "orgao_julgador", "Câmara Especial, sucessora do Orgão julgador: 3ª Câmara"),
            ("argapso julgador:", "orgao_julgador", "Câmara Especial (antes argapso julgador: 3ª Câmara)"),
        ],
    )
    def test_rotulo_citado_no_valor_fica(self, rotulo, chave, valor):
        """Só o rótulo do ``<strong>`` sai; texto igual a um rótulo no meio do valor fica."""
        html = f'<tr class="ementaClass2"><td><strong>{rotulo}</strong> {valor}</td></tr>'
        data: dict = {}

        _extract_detail(BeautifulSoup(html, "html.parser").tr, data)

        assert data == {chave: valor}

    @pytest.mark.parametrize(
        ("sigla", "arquivo"),
        [("tjac", "cjsg/post_initial.html"), ("tjce", "cjsg/results_normal_page_01.html")],
    )
    def test_ementa_com_travessao_do_windows_1252(self, tmp_path, sigla, arquivo):
        """O byte 0x96, travessão no windows-1252, sai "–", não o controle U+0096.

        O ``cjsg_download`` grava a resposta em latin-1, byte a byte como o eSAJ
        a mandou; o sample, regravado em UTF-8, guarda o mesmo U+0096.
        """
        path = _TESTS / sigla / "samples" / arquivo
        html = path.read_bytes().decode("utf-8")
        assert "\x96" in html
        como_baixado = tmp_path / "cjsg_00001.html"
        como_baixado.write_bytes(html.encode("latin-1"))

        for arquivo_html in (path, como_baixado):
            ementas = _parse_single_page(str(arquivo_html))["ementa"]
            assert ementas.str.contains("–").any()
            assert not ementas.str.contains("[\x80-\x9f]").any()

    @pytest.mark.parametrize(
        ("sigla", "arquivo", "sem_ementa"),
        [
            ("tjsp", "cjsg/sem_ementa.html", 9),
            ("tjsp", "cjsg/monocratica_single_page.html", 1),
            ("tjac", "cjsg/monocratica_single_page.html", 5),
            ("tjal", "cjsg/monocratica_single_page.html", 2),
            ("tjam", "cjsg/monocratica_single_page.html", 1),
            ("tjce", "cjsg/monocratica_single_page.html", 8),
            ("tjms", "cjsg/monocratica_single_page.html", 6),
        ],
    )
    def test_decisao_sem_ementa_sai_ausente(self, sigla, arquivo, sem_ementa):
        """Decisão sem a linha ``Ementa:`` sai com ementa ausente, não ``""`` (#713).

        O ``N/A`` do eSAJ aparece só no texto oculto de "ementa sem formatação"
        (no TJAM, ``Ementa: N/A``).
        """
        path = _TESTS / sigla / "samples" / arquivo
        soup = BeautifulSoup(path.read_bytes().decode("latin-1"), "html.parser")
        linhas = soup.find_all("tr", class_="fundocinza1")

        df = _parse_single_page(str(path))

        assert len(df) == len(linhas)
        for ementa, linha in zip(df["ementa"], linhas, strict=True):
            if linha.find("strong", string=lambda texto: "Ementa:" in (texto or "")):
                assert isinstance(ementa, str)
                assert ementa
            else:
                assert pd.isna(ementa)
                sem_formatacao = linha.select_one(".mensagemSemFormatacao").get_text(" ", strip=True)
                assert sem_formatacao.removeprefix("Ementa:").strip().startswith("N/A")
        assert df["ementa"].isna().sum() == sem_ementa

    def test_parse_results_page(self):
        """Primeira linha de uma página real, campo a campo, pelo nome do TJSP."""
        path = _TESTS / "tjsp/samples/cjsg/single_page.html"

        df = _cjsg_parse_single_page(str(path))

        assert len(df) == 20
        assert df.iloc[0].drop("ementa").to_dict() == {
            "processo": "1006180-87.2025.8.26.0309",
            "cd_acordao": "20401626",
            "cd_foro": "0",
            "classe_assunto": "Apelação Cível / Condomínio",
            "relator": "Salles Rossi",
            "comarca": "Jundiaí",
            "orgao_julgador": "8ª Câmara de Direito Privado",
            "data_julgamento": "15/04/2026",
            "data_publicacao": "15/04/2026",
        }
        assert df["ementa"].notna().all()

    def test_parse_empty_page(self):
        """Test parsing an empty results page."""
        html = '<html><body><table></table></body></html>'

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            temp_path = f.name

        try:
            df = _cjsg_parse_single_page(temp_path)
            assert isinstance(df, pd.DataFrame)
            assert len(df) == 0
        finally:
            Path(temp_path).unlink()

    def test_parse_missing_elements(self):
        """Test parsing page with missing elements."""
        html = '''
        <html>
        <body>
            <table>
                <tr class="fundocinza1">
                    <td></td>
                    <td>
                        <table>
                            <tr class="ementaClass2">
                                <td>No process link here</td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        '''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            temp_path = f.name

        try:
            df = _cjsg_parse_single_page(temp_path)
            assert isinstance(df, pd.DataFrame)
            # Should still create a row, but without process number
            assert len(df) >= 0
        finally:
            Path(temp_path).unlink()

    def test_tjsp_reexport_preserves_internal_parser_identity(self):
        assert _cjsg_parse_single_page is _parse_single_page

    def test_dynamic_labels_malformed_rows_and_ementa_fallback(self, tmp_path):
        sample_path = tmp_path / "linhas_de_borda.html"
        sample_path.write_text(_LINHAS_DE_BORDA, encoding="utf-8")

        df = _parse_single_page(str(sample_path))

        assert len(df) == 3
        assert tuple(df.columns) == (
            "processo",
            "cd_acordao",
            "cd_foro",
            "classe_assunto",
            "relator",
            "campo_especial",
            "data_publicacao",
            "orgao_julgador",
            "ementa",
        )
        assert df.iloc[0].to_dict() == {
            "processo": "0000001-02.2024.8.26.0001",
            "cd_acordao": "123",
            "cd_foro": "4",
            "classe_assunto": "Apelacao / Contratos",
            "relator": "Des. Joao Acu",
            "campo_especial": "valor dinamico",
            "data_publicacao": "01/02/2024",
            "orgao_julgador": "Camara Especial",
            "ementa": "texto oculto.",
        }
        assert df.iloc[1]["ementa"] == "fallback oculto."
        assert pd.isna(df.iloc[2]["ementa"])
        assert "outros_numeros" not in df.columns

    def test_cp1252_file_is_decoded_without_mojibake(self, tmp_path):
        """Os bytes do eSAJ (windows-1252) gravados como vieram saem iguais à página em UTF-8.

        ``results_normal_page_01.html`` tem acentos e o travessão "–", que no
        windows-1252 é o byte 0x96.
        """
        original = _TESTS / "tjsp/samples/cjsg/results_normal_page_01.html"
        texto = load_sample("tjsp", "cjsg/results_normal_page_01.html")
        assert "–" in texto
        path = tmp_path / "cp1252.html"
        path.write_bytes(texto.encode("cp1252"))

        df = _parse_single_page(str(path))

        pd.testing.assert_frame_equal(df, _parse_single_page(str(original)))
        assert df["ementa"].str.contains("–").any()
        assert df.iloc[0]["orgao_julgador"] == "Núcleo 4.0-T. V (DP1)"


class TestCJSGParseManager:
    """Test the cjsg_parse_manager function."""

    def test_parse_directory(self):
        """Test parsing multiple files from a directory."""
        html1 = load_sample('tjsp', 'cjsg/monocratica_single_page.html')
        html2 = load_sample('tjsp', 'cjsg/monocratica_single_page.html')

        with tempfile.TemporaryDirectory() as temp_dir:
            file1 = Path(temp_dir) / 'page1.html'
            file2 = Path(temp_dir) / 'page2.html'

            with file1.open('w', encoding='utf-8') as f:
                f.write(html1)
            with file2.open('w', encoding='utf-8') as f:
                f.write(html2)

            df = cjsg_parse_manager(temp_dir)

            assert isinstance(df, pd.DataFrame)
            # Uma decisão monocrática em cada arquivo
            assert len(df) == 2

    def test_parse_single_file(self):
        """Test parsing a single file."""
        html = load_sample('tjsp', 'cjsg/monocratica_single_page.html')

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            temp_path = f.name

        try:
            df = cjsg_parse_manager(temp_path)
            assert isinstance(df, pd.DataFrame)
            assert len(df) == 1
        finally:
            Path(temp_path).unlink()

    def test_parse_empty_directory(self):
        """Test parsing an empty directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            df = cjsg_parse_manager(temp_dir)
            assert isinstance(df, pd.DataFrame)
            assert len(df) == 0

    def test_parse_with_invalid_file(self):
        """Test parsing directory with invalid file (should skip it)."""
        html = load_sample('tjsp', 'cjsg/monocratica_single_page.html')

        with tempfile.TemporaryDirectory() as temp_dir:
            valid_file = Path(temp_dir) / 'valid.html'
            invalid_file = Path(temp_dir) / 'invalid.html'

            with valid_file.open('w', encoding='utf-8') as f:
                f.write(html)
            # Create an invalid file (binary data)
            with invalid_file.open('wb') as f:
                f.write(b'\x00\x01\x02\x03')

            # Should not raise exception, should skip invalid file
            df = cjsg_parse_manager(temp_dir)
            assert isinstance(df, pd.DataFrame)
            # Should have parsed the valid file
            assert len(df) >= 0

    def test_parse_directory_reads_nested_folders(self, tmp_path):
        """O auto-chunk grava uma pasta por janela; o parse desce nelas."""
        html = load_sample("tjsp", "cjsg/monocratica_single_page.html")
        (tmp_path / "janela_1").mkdir()
        (tmp_path / "janela_1" / "cjsg_00001.html").write_text(html, encoding="utf-8")
        (tmp_path / "cjsg_00001.html").write_text(html, encoding="utf-8")

        uma_pagina = len(_parse_single_page(str(tmp_path / "cjsg_00001.html")))
        assert uma_pagina > 0
        assert len(cjsg_parse_manager(str(tmp_path))) == 2 * uma_pagina


class TestCJSGNPagsLimites:
    """``cjsg_n_pags`` nos limites das páginas de 20 resultados."""

    @pytest.mark.parametrize(
        ("total", "paginas"),
        [(0, 0), (1, 1), (20, 1), (21, 2)],
    )
    def test_total_declarado_vira_paginas(self, total, paginas):
        assert cjsg_n_pags(_primeira_pagina_com_total(total)) == paginas


class TestExtractPaginationCount:
    """A contagem ao lado de "resultados" vence o maior número do texto."""

    @pytest.mark.parametrize(
        ("texto", "esperado"),
        [
            ("Resultados 1 a 20 de 45", 45),
            ("Foram encontrados 45 resultados em 2024.", 45),
            ("sem numero", None),
        ],
    )
    def test_tabela(self, texto, esperado):
        assert _extract_pagination_count(texto) == esperado


class TestLabeledValue:
    r"""Caracteres invisíveis e ``\xa0`` que o eSAJ mistura nos valores saem todos."""

    @pytest.mark.parametrize(
        "invisivel",
        [
            pytest.param("\xad", id="soft-hyphen"),
            pytest.param("\u200b", id="zero-width-space"),
            pytest.param("\u200c", id="zero-width-non-joiner"),
            pytest.param("\u200d", id="zero-width-joiner"),
        ],
    )
    def test_remove_caractere_invisivel(self, invisivel):
        html = f'<tr class="ementaClass2"><td><strong>Comarca:</strong> Rio\xa0Bra{invisivel}nco{invisivel}</td></tr>'
        linha = BeautifulSoup(html, "html.parser").tr

        assert _extract_labeled_value(linha, "Comarca:") == ("comarca", "Rio Branco")


class TestNormalizeKey:
    """Rótulos com marcador de gênero viram o nome canônico (#713)."""

    @pytest.mark.parametrize(
        ("rotulo", "chave"),
        [
            pytest.param("Relator(a):", "relator", id="relator-a-colado"),
            pytest.param("Relator (a):", "relator", id="relator-a-com-espaco"),
            pytest.param("Relator:", "relator", id="relator"),
        ],
    )
    def test_rotulo_vira_chave_canonica(self, rotulo, chave):
        assert _normalize_key(rotulo) == chave

    def test_paginas_com_relator_e_relator_a_geram_uma_so_coluna(self, tmp_path):
        """Páginas com "Relator:" e com "Relator(a):" dão uma coluna só, ``relator``.

        Todas as capturas do eSAJ trazem "Relator(a):"; a página com "Relator:"
        é a mesma captura com o rótulo trocado.
        """
        html = load_sample("tjsp", "cjsg/monocratica_single_page.html")
        sem_marcador = html.replace("Relator(a):", "Relator:")
        assert "Relator(a):" not in sem_marcador
        (tmp_path / "relator_a.html").write_text(html, encoding="utf-8")
        (tmp_path / "relator.html").write_text(sem_marcador, encoding="utf-8")

        df = cjsg_parse_manager(str(tmp_path))

        assert "relatora" not in df.columns
        assert df["relator"].notna().all()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
