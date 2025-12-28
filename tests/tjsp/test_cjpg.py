"""
Tests for TJSP CJPG functionality.
Includes both integration and unit tests.
"""
import sys
import os
import tempfile
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
        results = self.scraper.cjpg('golpe do pix', paginas=range(0, 1))
        
        assert isinstance(results, pd.DataFrame)
        assert len(results) >= 0
    
    def test_cjpg_with_filters(self):
        """Test CJPG search with filters."""
        results = self.scraper.cjpg(
            pesquisa='direito',
            classes=['Procedimento Comum Cível'],
            paginas=range(0, 1)
        )
        
        assert isinstance(results, pd.DataFrame)
    
    def test_cjpg_pagination(self):
        """Test CJPG pagination."""
        results = self.scraper.cjpg('direito', paginas=range(0, 2))
        
        assert isinstance(results, pd.DataFrame)
        assert len(results) >= 0
    
    def test_cjpg_date_filters(self):
        """Test CJPG with date filters."""
        results = self.scraper.cjpg(
            'direito',
            data_inicio='01/01/2023',
            data_fim='31/12/2023',
            paginas=range(0, 1)
        )
        assert isinstance(results, pd.DataFrame)
    
    def test_cjpg_result_structure(self):
        """Test that CJPG results have expected structure."""
        results = self.scraper.cjpg('direito', paginas=range(0, 1))
        
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
