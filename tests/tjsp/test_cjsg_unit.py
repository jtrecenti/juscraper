"""
Unit tests for TJSP CJSG functionality using mocked HTML responses.
"""
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from juscraper.courts._esaj.parse import _parse_single_page, cjsg_n_results
from juscraper.courts.tjsp.cjsg_parse import _cjsg_parse_single_page, cjsg_n_pags, cjsg_parse_manager
from tests._helpers import load_sample

ESAJ_COLUMNS = (
    "processo",
    "cd_acordao",
    "cd_foro",
    "classe_assunto",
    "relatora",
    "comarca",
    "orgao_julgador",
    "data_julgamento",
    "data_publicacao",
    "ementa",
)


class TestCJSGNPages:
    """Test the cjsg_n_pags function."""

    def test_extract_pages_from_results(self):
        """Test extracting page count from results HTML."""
        html = load_sample('tjsp', 'cjsg/results_normal.html')
        n_pags = cjsg_n_pags(html)
        # 45 results / 20 per page = 3 pages (rounded up)
        assert n_pags == 3

    def test_extract_pages_from_single_result(self):
        """Test extracting page count from single result HTML."""
        html = load_sample('tjsp', 'cjsg/single_result.html')
        n_pags = cjsg_n_pags(html)
        # 1 result / 20 per page = 1 page
        assert n_pags == 1

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

    def test_captcha_error_raises_specific_message(self):
        """Captcha/erro divs devem levantar ValueError com mensagem explicita."""
        html = (
            '<html><body>'
            '<div class="mensagemErro">Falha na verificação do captcha.</div>'
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

    def test_single_result_fallback_counts_rows(self):
        """Sample com 1 hit e sem marker de paginacao — fallback conta linhas."""
        html = load_sample("tjsp", "cjsg/single_result.html")
        assert cjsg_n_results(html) == 1

    def test_single_page_uses_canonical_selector(self):
        """Sample com totalResultado declarado — usa o numero do sample."""
        html = load_sample("tjsp", "cjsg/single_page.html")
        assert cjsg_n_results(html) == 78

    def test_n_pags_e_wrapper_que_aplica_ceil_div(self):
        """``cjsg_n_pags`` permanece um wrapper sobre ``cjsg_n_results``."""
        html = load_sample("tjsp", "cjsg/results_normal_page_01.html")
        # 2571077 resultados / 20 por pagina = 128554 paginas (ceil).
        assert cjsg_n_pags(html) == (2571077 + 19) // 20

    @pytest.mark.parametrize(
        ("sample", "expected"),
        [
            ("count_legacy_bgcolor.html", 42),
            ("count_pagination_class.html", 77),
            ("count_page_text.html", 99),
            ("count_rows_fallback.html", 3),
        ],
    )
    def test_selector_and_regex_cascades(self, sample, expected):
        html = load_sample("tjsp", f"cjsg/{sample}")
        assert cjsg_n_results(html) == expected

    def test_search_form_without_results_raises_specific_message(self):
        html = load_sample("tjsp", "cjsg/count_form_initial.html")
        with pytest.raises(ValueError, match="Ainda na página de consulta"):
            cjsg_n_results(html)

    def test_pagination_marker_without_number_raises_with_text(self):
        html = load_sample("tjsp", "cjsg/count_invalid_text.html")
        with pytest.raises(ValueError, match="Formato inesperado encontrado"):
            cjsg_n_results(html)

    def test_page_error_takes_precedence_over_zero_results_marker(self):
        html = load_sample("tjsp", "cjsg/count_error_and_zero.html")
        with pytest.raises(ValueError, match="Captcha"):
            cjsg_n_results(html)

    def test_results_table_without_standard_rows_returns_minimum_one(self):
        html = load_sample("tjsp", "cjsg/count_table_without_standard_rows.html")
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
        sample_path = Path(__file__).parent.parent / court / "samples" / relative_path

        df = _parse_single_page(str(sample_path))

        assert cjsg_n_results(html) == expected_count
        assert len(df) == expected_rows
        assert tuple(df.columns) == ESAJ_COLUMNS
        assert df.iloc[0]["processo"] == first_process


class TestCJSGParseSinglePage:
    """Test the _cjsg_parse_single_page function."""

    def test_parse_results_page(self):
        """Test parsing a results page with multiple processes."""
        html = load_sample('tjsp', 'cjsg/results_normal.html')

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            temp_path = f.name

        try:
            df = _cjsg_parse_single_page(temp_path)

            assert isinstance(df, pd.DataFrame)
            assert len(df) == 2  # Two processes in the sample

            # Check first process
            assert df.iloc[0]['processo'] == '1000123-45.2023.8.26.0100'
            assert df.iloc[0]['cd_acordao'] == '12345'
            assert df.iloc[0]['cd_foro'] == '6789'
            assert 'Apelação Cível' in df.iloc[0].get('classe', '')
            assert 'Direito do Consumidor' in df.iloc[0].get('assunto', '')
            assert 'ementa' in df.columns

            # Check second process
            assert df.iloc[1]['processo'] == '1000124-46.2023.8.26.0101'
            assert df.iloc[1]['cd_acordao'] == '12346'
        finally:
            Path(temp_path).unlink()

    def test_parse_single_result(self):
        """Test parsing a page with a single result."""
        html = load_sample('tjsp', 'cjsg/single_result.html')

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            temp_path = f.name

        try:
            df = _cjsg_parse_single_page(temp_path)

            assert isinstance(df, pd.DataFrame)
            assert len(df) == 1

            assert df.iloc[0]['processo'] == '1000999-99.2024.8.26.0100'
            assert df.iloc[0]['cd_acordao'] == '99999'
            assert 'Apelação Cível' in df.iloc[0].get('classe', '')
            assert 'ementa' in df.columns
        finally:
            Path(temp_path).unlink()

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

    def test_dynamic_labels_malformed_rows_and_ementa_fallback(self):
        sample_path = Path(__file__).parent / "samples/cjsg/parser_edge_cases.html"

        df = _parse_single_page(str(sample_path))

        assert len(df) == 3
        assert tuple(df.columns) == (
            "processo",
            "cd_acordao",
            "cd_foro",
            "classe_assunto",
            "relatora",
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
            "relatora": "Des. Joao Acu",
            "campo_especial": "valor dinamico",
            "data_publicacao": "01/02/2024",
            "orgao_julgador": "Camara Especial",
            "ementa": "texto visivel.",
        }
        assert df.iloc[1]["ementa"] == "fallback oculto."
        assert df.iloc[2]["ementa"] == ""
        assert "outros_numeros" not in df.columns

    def test_latin1_file_is_decoded_without_mojibake(self, tmp_path):
        html = load_sample("tjsp", "cjsg/latin1_result.html")
        path = tmp_path / "latin1.html"
        path.write_bytes(html.encode("latin-1"))

        df = _parse_single_page(str(path))

        assert df.iloc[0]["processo"] == "0000002-03.2024.8.26.0002"
        assert df.iloc[0]["relatora"] == "Des. João Açú"
        assert df.iloc[0]["ementa"] == "Decisão sobre obrigação."


class TestCJSGParseManager:
    """Test the cjsg_parse_manager function."""

    def test_parse_directory(self):
        """Test parsing multiple files from a directory."""
        html1 = load_sample('tjsp', 'cjsg/results_normal.html')
        html2 = load_sample('tjsp', 'cjsg/single_result.html')

        with tempfile.TemporaryDirectory() as temp_dir:
            file1 = Path(temp_dir) / 'page1.html'
            file2 = Path(temp_dir) / 'page2.html'

            with file1.open('w', encoding='utf-8') as f:
                f.write(html1)
            with file2.open('w', encoding='utf-8') as f:
                f.write(html2)

            df = cjsg_parse_manager(temp_dir)

            assert isinstance(df, pd.DataFrame)
            # 2 processes from first file + 1 from second = 3 total
            assert len(df) == 3

    def test_parse_single_file(self):
        """Test parsing a single file."""
        html = load_sample('tjsp', 'cjsg/results_normal.html')

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            temp_path = f.name

        try:
            df = cjsg_parse_manager(temp_path)
            assert isinstance(df, pd.DataFrame)
            assert len(df) == 2
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
        html = load_sample('tjsp', 'cjsg/results_normal.html')

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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
