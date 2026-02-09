"""
Tests for TJSP CJPG functionality.
Includes both integration and unit tests.
"""
import sys
import os
import tempfile
from unittest.mock import MagicMock, patch, call
import pytest
import pandas as pd

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

try:
    import juscraper
except ImportError:
    from src.juscraper import scraper as juscraper_scraper
    juscraper = type('Module', (), {'scraper': juscraper_scraper})()

from src.juscraper.courts.tjsp.cjpg_parse import cjpg_n_pags, cjpg_parse_single, cjpg_parse_manager
from src.juscraper.courts.tjsp.cjpg_download import cjpg_download
from tests.tjsp.test_utils import load_sample_html


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
            classes=['Procedimento Comum Cível'],
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
            data_inicio='01/01/2023',
            data_fim='31/12/2023',
            paginas=range(1, 2)
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
        """Test extracting page count from CJPG HTML."""
        html = load_sample_html('cjpg_results.html')
        n_pags = cjpg_n_pags(html)
        # 25 results / 10 per page = 3 pages (rounded up)
        assert n_pags == 3
    
    def test_cjpg_n_pags_missing_selector(self):
        """Test that missing pagination selector raises ValueError."""
        html = "<html><body><p>No pagination</p></body></html>"
        with pytest.raises(ValueError, match="Não foi possível encontrar"):
            cjpg_n_pags(html)
    
    def test_cjpg_parse_single(self):
        """Test parsing a single CJPG results page."""
        html = load_sample_html('cjpg_results.html')
        
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
            os.unlink(temp_path)
    
    def test_cjpg_parse_manager_directory(self):
        """Test parsing multiple CJPG files from directory."""
        html = load_sample_html('cjpg_results.html')
        
        with tempfile.TemporaryDirectory() as temp_dir:
            file1 = os.path.join(temp_dir, 'page1.html')
            file2 = os.path.join(temp_dir, 'page2.html')
            
            with open(file1, 'w', encoding='utf-8') as f:
                f.write(html)
            with open(file2, 'w', encoding='utf-8') as f:
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
            os.unlink(temp_path)


class TestCJPGDownload1Based:
    """Unit tests for CJPG download with 1-based pagination using mocks."""

    def _make_mock_response(self, text="<html>page</html>"):
        mock = MagicMock()
        mock.text = text
        mock.content = text.encode('utf-8')
        return mock

    def _run_download(self, n_pags, paginas=None, sleep_time=0):
        """Helper: runs cjpg_download with mocked session and callbacks."""
        mock_session = MagicMock()
        r0_response = self._make_mock_response("<html>page1</html>")
        page_response = self._make_mock_response("<html>other</html>")
        mock_session.get.side_effect = [r0_response] + [page_response] * (n_pags + 10)

        def get_n_pags_callback(r0):
            return n_pags

        with tempfile.TemporaryDirectory() as tmp:
            path = cjpg_download(
                pesquisa="teste",
                session=mock_session,
                u_base="https://esaj.tjsp.jus.br/",
                download_path=tmp,
                sleep_time=sleep_time,
                paginas=paginas,
                get_n_pags_callback=get_n_pags_callback,
            )
            saved_files = sorted(os.listdir(path))
            # Collect URLs from session.get calls (skip first which is pesquisar.do)
            get_calls = mock_session.get.call_args_list
            trocar_urls = [c[0][0] for c in get_calls[1:] if 'trocarDePagina' in c[0][0]]
            return saved_files, trocar_urls

    def test_default_all_pages(self):
        """Default (None) downloads all 3 pages: saves 00001, 00002, 00003."""
        files, urls = self._run_download(n_pags=3, paginas=None)
        assert files == ["cjpg_00001.html", "cjpg_00002.html", "cjpg_00003.html"]
        assert len(urls) == 2  # trocarDePagina for pages 2 and 3

    def test_single_page(self):
        """range(1, 2) downloads only page 1."""
        files, urls = self._run_download(n_pags=3, paginas=range(1, 2))
        assert files == ["cjpg_00001.html"]
        assert len(urls) == 0  # no trocarDePagina calls

    def test_three_pages(self):
        """range(1, 4) downloads pages 1, 2, 3."""
        files, urls = self._run_download(n_pags=5, paginas=range(1, 4))
        assert files == ["cjpg_00001.html", "cjpg_00002.html", "cjpg_00003.html"]
        assert len(urls) == 2

    def test_custom_range(self):
        """range(6, 11) downloads pages 6-10 (no page 1)."""
        files, urls = self._run_download(n_pags=20, paginas=range(6, 11))
        assert files == [f"cjpg_{p:05d}.html" for p in range(6, 11)]
        assert len(urls) == 5  # all via trocarDePagina

    def test_exceeds_available(self):
        """range(1, 101) with only 3 pages available: downloads only 1, 2, 3."""
        files, urls = self._run_download(n_pags=3, paginas=range(1, 101))
        assert files == ["cjpg_00001.html", "cjpg_00002.html", "cjpg_00003.html"]
        assert len(urls) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
