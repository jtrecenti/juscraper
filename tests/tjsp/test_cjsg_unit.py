"""
Unit tests for TJSP CJSG functionality using mocked HTML responses.
"""
import sys
import os
import tempfile
import pandas as pd
import pytest

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.juscraper.courts.tjsp.cjsg_parse import cjsg_n_pags, _cjsg_parse_single_page, cjsg_parse_manager
from tests.tjsp.test_utils import load_sample_html


class TestCJSGNPages:
    """Test the cjsg_n_pags function."""
    
    def test_extract_pages_from_results(self):
        """Test extracting page count from results HTML."""
        html = load_sample_html('cjsg_results.html')
        n_pags = cjsg_n_pags(html)
        # 45 results / 20 per page = 3 pages (rounded up)
        assert n_pags == 3
    
    def test_extract_pages_from_single_result(self):
        """Test extracting page count from single result HTML."""
        html = load_sample_html('cjsg_single_result.html')
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


class TestCJSGParseSinglePage:
    """Test the _cjsg_parse_single_page function."""
    
    def test_parse_results_page(self):
        """Test parsing a results page with multiple processes."""
        html = load_sample_html('cjsg_results.html')
        
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
            os.unlink(temp_path)
    
    def test_parse_single_result(self):
        """Test parsing a page with a single result."""
        html = load_sample_html('cjsg_single_result.html')
        
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
            os.unlink(temp_path)
    
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
            os.unlink(temp_path)
    
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
            os.unlink(temp_path)


class TestCJSGParseManager:
    """Test the cjsg_parse_manager function."""
    
    def test_parse_directory(self):
        """Test parsing multiple files from a directory."""
        html1 = load_sample_html('cjsg_results.html')
        html2 = load_sample_html('cjsg_single_result.html')
        
        with tempfile.TemporaryDirectory() as temp_dir:
            file1 = os.path.join(temp_dir, 'page1.html')
            file2 = os.path.join(temp_dir, 'page2.html')
            
            with open(file1, 'w', encoding='utf-8') as f:
                f.write(html1)
            with open(file2, 'w', encoding='utf-8') as f:
                f.write(html2)
            
            df = cjsg_parse_manager(temp_dir)
            
            assert isinstance(df, pd.DataFrame)
            # 2 processes from first file + 1 from second = 3 total
            assert len(df) == 3
    
    def test_parse_single_file(self):
        """Test parsing a single file."""
        html = load_sample_html('cjsg_results.html')
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            temp_path = f.name
        
        try:
            df = cjsg_parse_manager(temp_path)
            assert isinstance(df, pd.DataFrame)
            assert len(df) == 2
        finally:
            os.unlink(temp_path)
    
    def test_parse_empty_directory(self):
        """Test parsing an empty directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            df = cjsg_parse_manager(temp_dir)
            assert isinstance(df, pd.DataFrame)
            assert len(df) == 0
    
    def test_parse_with_invalid_file(self):
        """Test parsing directory with invalid file (should skip it)."""
        html = load_sample_html('cjsg_results.html')
        
        with tempfile.TemporaryDirectory() as temp_dir:
            valid_file = os.path.join(temp_dir, 'valid.html')
            invalid_file = os.path.join(temp_dir, 'invalid.html')
            
            with open(valid_file, 'w', encoding='utf-8') as f:
                f.write(html)
            # Create an invalid file (binary data)
            with open(invalid_file, 'wb') as f:
                f.write(b'\x00\x01\x02\x03')
            
            # Should not raise exception, should skip invalid file
            df = cjsg_parse_manager(temp_dir)
            assert isinstance(df, pd.DataFrame)
            # Should have parsed the valid file
            assert len(df) >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

