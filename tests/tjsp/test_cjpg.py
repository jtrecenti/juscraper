"""
Tests for TJSP CJPG functionality.
Includes both integration and unit tests.
"""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, call

import pandas as pd
import pytest

import juscraper
from juscraper.courts.tjsp.cjpg_download import cjpg_download
from juscraper.courts.tjsp.cjpg_parse import cjpg_n_pags, cjpg_n_results, cjpg_parse_manager, cjpg_parse_single
from tests._helpers import load_sample


@pytest.mark.integration
class TestCJPGIntegration:
    """Integration tests for CJPG that hit the real website."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test fixtures."""
        self.scraper = juscraper.scraper('tjsp')
        yield

    def test_cjpg_basic_search(self):
        """Test basic CJPG search functionality."""
        results = self.scraper.cjpg('golpe do pix', paginas=range(1, 2))

        assert isinstance(results, pd.DataFrame)
        assert len(results) >= 0

    def test_cjpg_with_filters(self):
        """Test CJPG search with filters."""
        results = self.scraper.cjpg(
            pesquisa='direito',
            classe=['Procedimento Comum Cível'],
            paginas=range(1, 2)
        )

        assert isinstance(results, pd.DataFrame)

    def test_cjpg_pagination(self):
        """Test CJPG pagination."""
        results = self.scraper.cjpg('direito', paginas=range(1, 3))

        assert isinstance(results, pd.DataFrame)
        assert len(results) >= 0

    def test_cjpg_date_filters(self):
        """Test CJPG with date filters."""
        results = self.scraper.cjpg(
            'direito',
            data_julgamento_inicio='01/01/2023',
            data_julgamento_fim='31/12/2023',
            paginas=range(1, 2),
        )
        assert isinstance(results, pd.DataFrame)

    def test_cjpg_result_structure(self):
        """Test that CJPG results have expected structure."""
        results = self.scraper.cjpg('direito', paginas=range(1, 2))

        assert isinstance(results, pd.DataFrame)

        if len(results) > 0:
            # Check for expected columns
            assert len(results.columns) > 0


class TestCJPGUnit:
    """Unit tests for CJPG parsing functions."""

    def test_cjpg_n_pags_extraction(self):
        """Test extracting page count from CJPG HTML (legacy format)."""
        html = load_sample('tjsp', 'cjpg/results_legacy.html')
        n_pags = cjpg_n_pags(html)
        # "Mostrando 1 a 10 de 25 resultados" → 25/10 = 3 pages (ceil)
        assert n_pags == 3

    def test_cjpg_n_pags_novo_formato(self):
        """Test extracting page count from current TJSP CJPG HTML.

        Regression for the bug where TJSP changed the pagination text from
        "Mostrando 1 a 10 de N resultados" to "Resultados 1 a 10 de N",
        breaking the original regex (which required "resultado" after the
        number).
        """
        html = load_sample('tjsp', 'cjpg/results_novo_formato.html')
        n_pags = cjpg_n_pags(html)
        # "Resultados 1 a 10 de 39764" → ceil(39764/10) = 3977
        assert n_pags == 3977

    @pytest.mark.parametrize("n_results,expected_pags", [
        (1, 1),       # 1 result -> 1 page
        (10, 1),      # exact multiple: 1 page (was incorrectly 2 in old code)
        (11, 2),      # 2 pages
        (20, 2),      # exact multiple
        (25, 3),      # legacy fixture value
        (39764, 3977),  # current TJSP real value
    ])
    def test_cjpg_n_pags_ceiling(self, n_results, expected_pags):
        """Ceiling division: results / 10 rounded up. Covers exact multiples."""
        html = (
            '<html><body><table><tr><td>'
            f'Resultados 1 a 10 de {n_results}'
            '</td></tr></table></body></html>'
        )
        assert cjpg_n_pags(html) == expected_pags

    def test_cjpg_n_pags_missing_selector(self):
        """Test that missing pagination selector raises ValueError."""
        html = "<html><body><p>No pagination</p></body></html>"
        with pytest.raises(ValueError, match="Não foi possível encontrar"):
            cjpg_n_pags(html)

    def test_cjpg_parse_single(self):
        """Test parsing a single CJPG results page."""
        html = load_sample('tjsp', 'cjpg/results_legacy.html')

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            temp_path = f.name

        try:
            df = cjpg_parse_single(temp_path)

            assert isinstance(df, pd.DataFrame)
            assert len(df) == 2  # Two processes in sample

            # Check first process
            assert df.iloc[0]['id_processo'] == '1001796-12.2024.8.26.0699'
            assert df.iloc[0]['cd_processo'] == 'JF0004W7G0000'
            assert 'Procedimento do Juizado Especial Cível' in df.iloc[0].get('classe', '')
            assert 'decisao' in df.columns
        finally:
            Path(temp_path).unlink()

    def test_cjpg_parse_manager_directory(self):
        """Test parsing multiple CJPG files from directory."""
        html = load_sample('tjsp', 'cjpg/results_legacy.html')

        with tempfile.TemporaryDirectory() as temp_dir:
            file1 = Path(temp_dir) / 'page1.html'
            file2 = Path(temp_dir) / 'page2.html'

            with file1.open('w', encoding='utf-8') as f:
                f.write(html)
            with file2.open('w', encoding='utf-8') as f:
                f.write(html)

            df = cjpg_parse_manager(temp_dir)

            assert isinstance(df, pd.DataFrame)
            # 2 processes per file * 2 files = 4 total
            assert len(df) == 4

    def test_cjpg_parse_empty_page(self):
        """Test parsing an empty CJPG page."""
        html = '<html><body><div id="divDadosResultado"></div></body></html>'

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            temp_path = f.name

        try:
            df = cjpg_parse_single(temp_path)
            assert isinstance(df, pd.DataFrame)
            assert len(df) == 0
        finally:
            Path(temp_path).unlink()


class TestCJPGNResults:
    """Tests do helper :func:`cjpg_n_results` (issue #92)."""

    def test_extracts_raw_count_legacy_format(self):
        """Legacy 'Mostrando 1 a 10 de 25 resultados' -> 25."""
        html = load_sample("tjsp", "cjpg/results_legacy.html")
        assert cjpg_n_results(html) == 25

    def test_extracts_raw_count_novo_formato(self):
        """Novo formato 'Resultados 1 a 10 de 39764' -> 39764."""
        html = load_sample("tjsp", "cjpg/results_novo_formato.html")
        assert cjpg_n_results(html) == 39764

    def test_zero_results_returns_zero(self):
        html = load_sample("tjsp", "cjpg/no_results.html")
        assert cjpg_n_results(html) == 0

    def test_n_pags_e_wrapper_que_aplica_ceil_div(self):
        """``cjpg_n_pags`` permanece um wrapper sobre ``cjpg_n_results``."""
        html = load_sample("tjsp", "cjpg/results_novo_formato.html")
        assert cjpg_n_pags(html) == (39764 + 9) // 10


class TestCJPGDownload1Based:
    """Unit tests for CJPG download with 1-based pagination using mocks."""

    def _make_mock_response(self, text="<html>page</html>"):
        mock = MagicMock()
        mock.text = text
        mock.content = text.encode('utf-8')
        return mock

    def _download_with_mocks(self, tmp_path, mocker, *, n_pags, paginas=None, sleep_time=0):
        """Run the internal downloader while retaining its collaborators."""
        mock_session = MagicMock()
        r0_response = self._make_mock_response("<html>page1</html>")
        page_response = self._make_mock_response("<html>page2+</html>")
        mock_session.get.side_effect = [r0_response] + [page_response] * (n_pags + 10)
        count_pages = mocker.patch(
            "juscraper.courts.tjsp.cjpg_download.cjpg_n_pags",
            return_value=n_pags,
        )

        path = cjpg_download(
            pesquisa="teste",
            session=mock_session,
            u_base="https://esaj.tjsp.jus.br/",
            download_path=str(tmp_path),
            sleep_time=sleep_time,
            paginas=paginas,
        )

        saved_files = sorted(file.name for file in Path(path).iterdir())
        trocar_urls = [
            item.args[0]
            for item in mock_session.get.call_args_list[1:]
            if "trocarDePagina" in item.args[0]
        ]
        return path, saved_files, trocar_urls, mock_session, r0_response, count_pages

    def test_default_all_pages(self, tmp_path, mocker):
        """Default (None) downloads all 3 pages: saves 00001, 00002, 00003."""
        _, files, urls, _, _, _ = self._download_with_mocks(tmp_path, mocker, n_pags=3)
        assert files == ["cjpg_00001.html", "cjpg_00002.html", "cjpg_00003.html"]
        assert len(urls) == 2  # trocarDePagina for pages 2 and 3

    def test_single_page(self, tmp_path, mocker):
        """range(1, 2) downloads only page 1."""
        _, files, urls, _, _, _ = self._download_with_mocks(
            tmp_path,
            mocker,
            n_pags=3,
            paginas=range(1, 2),
        )
        assert files == ["cjpg_00001.html"]
        assert len(urls) == 0  # no trocarDePagina calls

    def test_three_pages(self, tmp_path, mocker):
        """range(1, 4) downloads pages 1, 2, 3."""
        _, files, urls, _, _, _ = self._download_with_mocks(
            tmp_path,
            mocker,
            n_pags=5,
            paginas=range(1, 4),
        )
        assert files == ["cjpg_00001.html", "cjpg_00002.html", "cjpg_00003.html"]
        assert len(urls) == 2

    def test_custom_range(self, tmp_path, mocker):
        """range(6, 11) downloads pages 6-10 (no page 1)."""
        _, files, urls, _, _, _ = self._download_with_mocks(
            tmp_path,
            mocker,
            n_pags=20,
            paginas=range(6, 11),
        )
        assert files == [f"cjpg_{p:05d}.html" for p in range(6, 11)]
        assert len(urls) == 5  # all via trocarDePagina

    def test_exceeds_available(self, tmp_path, mocker):
        """range(1, 101) with only 3 pages available: downloads only 1, 2, 3."""
        _, files, urls, _, _, _ = self._download_with_mocks(
            tmp_path,
            mocker,
            n_pags=3,
            paginas=range(1, 101),
        )
        assert files == ["cjpg_00001.html", "cjpg_00002.html", "cjpg_00003.html"]
        assert len(urls) == 2

    def test_counter_receives_first_page_content_and_return_is_str(self, tmp_path, mocker):
        path, _, _, _, r0_response, count_pages = self._download_with_mocks(
            tmp_path,
            mocker,
            n_pags=1,
            paginas=[1],
        )

        assert isinstance(path, str)
        count_pages.assert_called_once_with(r0_response.content)

    def test_zero_pages_still_saves_first_page(self, tmp_path, mocker):
        path, files, _, mock_session, _, _ = self._download_with_mocks(
            tmp_path,
            mocker,
            n_pags=0,
            paginas=[3],
        )

        assert files == ["cjpg_00001.html"]
        assert Path(path, "cjpg_00001.html").read_text(encoding="utf-8") == "<html>page1</html>"
        assert mock_session.get.call_count == 1

    def test_sparse_page_list_discards_unavailable_pages(self, tmp_path, mocker):
        sleep = mocker.patch("juscraper.courts.tjsp.cjpg_download.time.sleep")

        _, files, _, mock_session, _, _ = self._download_with_mocks(
            tmp_path,
            mocker,
            n_pags=3,
            paginas=[1, 3, 99],
            sleep_time=0.25,
        )

        assert files == ["cjpg_00001.html", "cjpg_00003.html"]
        assert mock_session.get.call_args_list[1:] == [
            call("https://esaj.tjsp.jus.br/cjpg/trocarDePagina.do?pagina=3&conversationId=")
        ]
        sleep.assert_called_once_with(0.25)

    def test_range_step_preserves_page_order_and_request_urls(self, tmp_path, mocker):
        sleep = mocker.patch("juscraper.courts.tjsp.cjpg_download.time.sleep")

        _, files, _, mock_session, _, _ = self._download_with_mocks(
            tmp_path,
            mocker,
            n_pags=5,
            paginas=range(1, 8, 2),
            sleep_time=0.4,
        )

        assert files == [
            "cjpg_00001.html",
            "cjpg_00003.html",
            "cjpg_00005.html",
        ]
        assert mock_session.get.call_args_list[1:] == [
            call("https://esaj.tjsp.jus.br/cjpg/trocarDePagina.do?pagina=3&conversationId="),
            call("https://esaj.tjsp.jus.br/cjpg/trocarDePagina.do?pagina=5&conversationId="),
        ]
        assert sleep.call_args_list == [call(0.4), call(0.4)]

    def test_count_error_saves_debug_html_and_preserves_cause(self, tmp_path, mocker):
        mock_session = MagicMock()
        mock_session.get.return_value = self._make_mock_response("<html>diagnostico</html>")
        upstream_error = RuntimeError("falha ao contar páginas")
        mocker.patch(
            "juscraper.courts.tjsp.cjpg_download.cjpg_n_pags",
            side_effect=upstream_error,
        )

        with pytest.raises(ValueError, match="falha ao contar páginas") as exc_info:
            cjpg_download(
                pesquisa="teste",
                session=mock_session,
                u_base="https://esaj.tjsp.jus.br/",
                download_path=str(tmp_path),
            )

        assert exc_info.value.__cause__ is upstream_error
        debug_files = list(Path(tmp_path, "cjpg_debug").glob("cjpg_primeira_pagina_*.html"))
        assert len(debug_files) == 1
        assert debug_files[0].read_text(encoding="utf-8") == "<html>diagnostico</html>"


class TestCJPGDateRangeValidation:
    """Pre-request date-range validation for the eSAJ 1-year limit (#91)."""

    def _patched_scraper(self):
        """Build a TJSPScraper whose session.get would fail the test if called."""
        scraper = juscraper.scraper('tjsp')
        # Replace session with a MagicMock that records calls — if validation
        # fails to short-circuit, .get() would be invoked and we can detect it.
        scraper.session = MagicMock()
        return scraper

    def test_range_over_one_year_raises_before_request(self):
        scraper = self._patched_scraper()
        with pytest.raises(ValueError, match="no máximo 366 dias"):
            scraper.cjpg_download(
                pesquisa="direito",
                data_julgamento_inicio="01/01/2020",
                data_julgamento_fim="31/12/2021",
            )
        # Crucially, nothing hit the network.
        scraper.session.get.assert_not_called()
        scraper.session.post.assert_not_called()

    def test_invalid_format_raises_before_request(self):
        # ISO + BR mixed are both accepted (coerced to backend format, refs #173).
        # Use a format the coercer cannot recognize (e.g. dotted) so the
        # downstream validate_intervalo_datas raises the expected error.
        scraper = self._patched_scraper()
        with pytest.raises(ValueError, match="Formato esperado"):
            scraper.cjpg_download(
                pesquisa="direito",
                data_julgamento_inicio="01.01.2020",
                data_julgamento_fim="31.12.2020",
            )
        scraper.session.get.assert_not_called()

    def test_inicio_after_fim_raises_before_request(self):
        scraper = self._patched_scraper()
        with pytest.raises(ValueError, match="posterior"):
            scraper.cjpg_download(
                pesquisa="direito",
                data_julgamento_inicio="31/12/2023",
                data_julgamento_fim="01/01/2023",
            )
        scraper.session.get.assert_not_called()

    def test_valid_one_year_window_proceeds_to_request(self):
        """A valid 1-year window should NOT short-circuit; the download
        proceeds and the mocked session receives the first GET."""
        scraper = self._patched_scraper()
        # Make the mock raise after the first .get() so we don't actually
        # exercise the parsing flow — we only care that validation passed.
        scraper.session.get.side_effect = RuntimeError("short-circuit after validate")
        with pytest.raises(RuntimeError, match="short-circuit"):
            scraper.cjpg_download(
                pesquisa="direito",
                data_julgamento_inicio="01/01/2023",
                data_julgamento_fim="31/12/2023",
            )
        assert scraper.session.get.called


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
