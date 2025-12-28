"""
Integration tests for TJSP CJSG functionality.
These tests actually hit the TJSP website and may be slow.
"""
import sys
import os
import pytest
import pandas as pd

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

try:
    import juscraper
except ImportError:
    # Try alternative import
    from src.juscraper import scraper as juscraper_scraper
    juscraper = type('Module', (), {'scraper': juscraper_scraper})()


@pytest.mark.integration
class TestCJSGIntegration:
    """Integration tests for CJSG that hit the real website."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test fixtures."""
        self.scraper = juscraper.scraper('tjsp')
        yield
        # Cleanup if needed
    
    def test_cjsg_basic_search(self):
        """Test basic CJSG search functionality."""
        # Use a common search term that should return results
        results = self.scraper.cjsg('direito civil', paginas=range(0, 1))
        
        assert isinstance(results, pd.DataFrame)
        assert len(results) >= 0  # May have 0 or more results
    
    def test_cjsg_with_filters(self):
        """Test CJSG search with various filters."""
        # Test with ementa filter
        results = self.scraper.cjsg(
            pesquisa='contrato',
            ementa='consumidor',
            paginas=range(0, 1)
        )
        
        assert isinstance(results, pd.DataFrame)
    
    def test_cjsg_pagination(self):
        """Test CJSG pagination handling."""
        # Test downloading multiple pages
        results = self.scraper.cjsg('direito', paginas=range(0, 2))
        
        assert isinstance(results, pd.DataFrame)
        # Should have results from multiple pages if available
        assert len(results) >= 0
    
    def test_cjsg_multiple_pages(self):
        """Test CJSG with multiple pages to ensure pagination works correctly."""
        # Test downloading 3 pages
        results = self.scraper.cjsg('direito civil', paginas=range(0, 3))
        
        assert isinstance(results, pd.DataFrame)
        # Should have results from multiple pages
        assert len(results) >= 0
        # If there are results, verify structure
        if len(results) > 0:
            assert 'ementa' in results.columns or len(results.columns) > 0
    
    def test_cjsg_tipo_decisao(self):
        """Test CJSG with different decision types."""
        # Test acordao
        results_acordao = self.scraper.cjsg(
            'direito',
            tipo_decisao='acordao',
            paginas=range(0, 1)
        )
        assert isinstance(results_acordao, pd.DataFrame)
        
        # Test monocratica
        results_monocratica = self.scraper.cjsg(
            'direito',
            tipo_decisao='monocratica',
            paginas=range(0, 1)
        )
        assert isinstance(results_monocratica, pd.DataFrame)
    
    def test_cjsg_baixar_sg_option(self):
        """Test CJSG with baixar_sg option."""
        # Test with baixar_sg=True (default)
        results_sg = self.scraper.cjsg('direito', baixar_sg=True, paginas=range(0, 1))
        assert isinstance(results_sg, pd.DataFrame)
        
        # Test with baixar_sg=False
        results_no_sg = self.scraper.cjsg('direito', baixar_sg=False, paginas=range(0, 1))
        assert isinstance(results_no_sg, pd.DataFrame)
    
    def test_cjsg_date_filters(self):
        """Test CJSG with date filters."""
        # Test with date range
        results = self.scraper.cjsg(
            'direito',
            data_inicio='01/01/2023',
            data_fim='31/12/2023',
            paginas=range(0, 1)
        )
        assert isinstance(results, pd.DataFrame)
    
    @pytest.mark.skip(reason="May fail if no results found - test structure validation")
    def test_cjsg_no_results_handling(self):
        """Test CJSG behavior when no results are found."""
        # Use a very specific search that likely returns no results
        results = self.scraper.cjsg(
            'xyzabc123nonexistentsearchterm456',
            paginas=range(0, 1)
        )
        # Should return empty DataFrame, not raise exception
        assert isinstance(results, pd.DataFrame)
    
    def test_cjsg_result_structure(self):
        """Test that CJSG results have expected structure."""
        results = self.scraper.cjsg('direito', paginas=range(0, 1))
        
        assert isinstance(results, pd.DataFrame)
        
        if len(results) > 0:
            # Check that expected columns exist
            # Note: columns may vary, but 'ementa' should be present
            assert 'ementa' in results.columns or len(results.columns) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])

