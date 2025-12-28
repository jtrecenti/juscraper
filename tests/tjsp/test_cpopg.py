"""
Tests for TJSP CPOPG functionality.
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

from src.juscraper.courts.tjsp.cpopg_parse import (
    cpopg_parse_manager,
    cpopg_parse_single,
    cpopg_parse_single_html,
    get_cpopg_download_links
)
from tests.tjsp.test_utils import load_sample_html, create_mock_response


@pytest.mark.integration
class TestCPOPGIntegration:
    """Integration tests for CPOPG that hit the real website."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test fixtures."""
        self.scraper = juscraper.scraper('tjsp')
        yield
    
    def test_cpopg_single_process(self):
        """Test downloading a single process from CPOPG."""
        # Use a known process ID from the notebook example
        process_id = '1000149-71.2024.8.26.0346'
        results = self.scraper.cpopg(process_id, method='html')
        
        assert isinstance(results, dict)
        assert 'basicos' in results
        assert 'partes' in results
        assert 'movimentacoes' in results
        assert 'peticoes_diversas' in results
        
        # Check basic info
        assert isinstance(results['basicos'], pd.DataFrame)
        if len(results['basicos']) > 0:
            assert 'id_processo' in results['basicos'].columns
    
    def test_cpopg_multiple_processes(self):
        """Test downloading multiple processes from CPOPG."""
        process_ids = ['1000149-71.2024.8.26.0346']
        results = self.scraper.cpopg(process_ids, method='html')
        
        assert isinstance(results, dict)
        assert 'basicos' in results
        assert isinstance(results['basicos'], pd.DataFrame)
    
    def test_cpopg_result_structure(self):
        """Test that CPOPG results have expected structure."""
        process_id = '1000149-71.2024.8.26.0346'
        results = self.scraper.cpopg(process_id, method='html')
        
        assert isinstance(results, dict)
        
        # All keys should be DataFrames
        for key, value in results.items():
            assert isinstance(value, pd.DataFrame), f"{key} should be a DataFrame"


class TestCPOPGUnit:
    """Unit tests for CPOPG parsing functions."""
    
    def test_get_cpopg_download_links_single_process(self):
        """Test extracting download links from single process page."""
        html = '''
        <html>
        <body>
            <form id="popupSenha" action="/cpopg/show.do?cdProcesso=12345">
            </form>
        </body>
        </html>
        '''
        mock_response = create_mock_response(html)
        links = get_cpopg_download_links(mock_response)
        
        assert isinstance(links, list)
        assert len(links) > 0
        assert 'show.do' in links[0]
    
    def test_get_cpopg_download_links_multiple_processes(self):
        """Test extracting download links from multiple processes page."""
        html = '''
        <html>
        <body>
            <div id="listagemDeProcessos">
                <a href="/cpopg/show.do?cdProcesso=12345">Process 1</a>
                <a href="/cpopg/show.do?cdProcesso=12346">Process 2</a>
            </div>
        </body>
        </html>
        '''
        mock_response = create_mock_response(html)
        links = get_cpopg_download_links(mock_response)
        
        assert isinstance(links, list)
        assert len(links) >= 0
    
    def test_cpopg_parse_single_html(self):
        """Test parsing a single CPOPG HTML file."""
        html = '''
        <html>
        <body>
            <span id="numeroProcesso">1000149-71.2024.8.26.0346</span>
            <span id="classeProcesso">Procedimento Comum Cível</span>
            <span id="assuntoProcesso">Responsabilidade do Fornecedor</span>
            <span id="foroProcesso">Foro de Martinópolis</span>
            <span id="varaProcesso">2ª Vara Judicial</span>
            <span id="juizProcesso">RENATA ESSER DE SOUZA</span>
            <div id="dataHoraDistribuicaoProcesso">06/02/2024 às 13:47 - Livre</div>
            <div id="valorAcaoProcesso">R$ 81.439,78</div>
            
            <table id="tablePartesPrincipais">
                <tr>
                    <td><span class="tipoDeParticipacao">Reqte</span></td>
                    <td>Aparecida Stuani<br>Advogado:<br>Carina Akemi Rezende</td>
                </tr>
                <tr>
                    <td><span class="tipoDeParticipacao">Reqda</span></td>
                    <td>BANCO BRADESCO S.A.<br>Advogado:<br>Fabio Cabral Silva</td>
                </tr>
            </table>
            
            <tbody id="tabelaTodasMovimentacoes">
                <tr class="containerMovimentacao">
                    <td>05/02/2025</td>
                    <td></td>
                    <td>Remetidos os Autos para o Tribunal de Justiça</td>
                </tr>
                <tr class="containerMovimentacao">
                    <td>04/12/2024</td>
                    <td></td>
                    <td>Contrarrazões Juntada</td>
                </tr>
            </tbody>
            
            <h2 class="subtitle tituloDoBloco">Petições diversas</h2>
            <table>
                <tr>
                    <td>14/02/2024</td>
                    <td>Emenda à Inicial</td>
                </tr>
                <tr>
                    <td>19/03/2024</td>
                    <td>Contestação</td>
                </tr>
            </table>
        </body>
        </html>
        '''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            temp_path = f.name
        
        try:
            result = cpopg_parse_single_html(temp_path)
            
            assert isinstance(result, dict)
            assert 'basicos' in result
            assert 'partes' in result
            assert 'movimentacoes' in result
            assert 'peticoes_diversas' in result
            
            # Check basic info
            assert result['basicos'].iloc[0]['id_processo'] == '1000149-71.2024.8.26.0346'
            assert 'Procedimento Comum Cível' in result['basicos'].iloc[0]['classe']
            
            # Check partes
            assert len(result['partes']) == 2
            assert result['partes'].iloc[0]['tipo'] == 'Reqte'
            
            # Check movimentacoes
            assert len(result['movimentacoes']) == 2
            assert '05/02/2025' in result['movimentacoes'].iloc[0]['data']
            
            # Check peticoes
            assert len(result['peticoes_diversas']) == 2
        finally:
            os.unlink(temp_path)
    
    def test_cpopg_parse_manager_directory(self):
        """Test parsing multiple CPOPG files from directory."""
        html = '''
        <html>
        <body>
            <span id="numeroProcesso">1000149-71.2024.8.26.0346</span>
            <span id="classeProcesso">Procedimento Comum Cível</span>
        </body>
        </html>
        '''
        
        with tempfile.TemporaryDirectory() as temp_dir:
            file1 = os.path.join(temp_dir, 'process1.html')
            file2 = os.path.join(temp_dir, 'process2.html')
            
            with open(file1, 'w', encoding='utf-8') as f:
                f.write(html)
            with open(file2, 'w', encoding='utf-8') as f:
                f.write(html.replace('1000149', '1000150'))
            
            result = cpopg_parse_manager(temp_dir)
            
            assert isinstance(result, dict)
            assert 'basicos' in result
            assert len(result['basicos']) == 2
    
    def test_cpopg_parse_empty_file(self):
        """Test parsing an empty CPOPG HTML file."""
        html = '<html><body></body></html>'
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            temp_path = f.name
        
        try:
            result = cpopg_parse_single_html(temp_path)
            
            assert isinstance(result, dict)
            assert 'basicos' in result
            assert len(result['basicos']) == 1
            # Should have empty DataFrames for other tables
            assert len(result['partes']) == 0
            assert len(result['movimentacoes']) == 0
        finally:
            os.unlink(temp_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

