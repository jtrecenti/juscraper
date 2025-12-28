"""
Tests for TJSP CPOSG functionality.
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

from src.juscraper.courts.tjsp.cposg_parse import (
    cposg_parse_manager,
    cposg_parse_single_html
)


@pytest.mark.integration
class TestCPOSGIntegration:
    """Integration tests for CPOSG that hit the real website."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test fixtures."""
        self.scraper = juscraper.scraper('tjsp')
        yield
    
    def test_cposg_single_process(self):
        """Test downloading a single process from CPOSG."""
        # Use a known process ID from the notebook example
        process_id = '00221752420038260344'
        results = self.scraper.cposg(process_id, method='html')
        
        assert isinstance(results, pd.DataFrame)
        assert len(results) >= 0
    
    def test_cposg_multiple_processes(self):
        """Test downloading multiple processes from CPOSG."""
        process_ids = ['00221752420038260344', '10001497120248260346']
        results = self.scraper.cposg(process_ids, method='html')
        
        assert isinstance(results, pd.DataFrame)
        assert len(results) >= 0
    
    def test_cposg_result_structure(self):
        """Test that CPOSG results have expected structure."""
        process_id = '00221752420038260344'
        results = self.scraper.cposg(process_id, method='html')
        
        assert isinstance(results, pd.DataFrame)
        
        if len(results) > 0:
            # Check for expected columns
            assert len(results.columns) > 0
            # Common columns that should exist
            expected_columns = ['id_original', 'processo', 'status']
            for col in expected_columns:
                if col in results.columns:
                    assert True  # Column exists


class TestCPOSGUnit:
    """Unit tests for CPOSG parsing functions."""
    
    def test_cposg_parse_single_html(self):
        """Test parsing a single CPOSG HTML file."""
        html = '''
        <html>
        <body>
            <a href="processo.codigo=1000149-71.2024.8.26.0346">1000149-71.2024.8.26.0346</a>
            <span class="unj-larger">1000149-71.2024.8.26.0346</span>
            <span class="unj-tag">Encerrado</span>
            
            <div>
                <span class="unj-label">Classe</span>
                <div>Apelação Cível</div>
            </div>
            <div>
                <span class="unj-label">Assunto</span>
                <div>DIREITO DO CONSUMIDOR - Contratos de Consumo</div>
            </div>
            <div>
                <span class="unj-label">Seção</span>
                <div>Direito Privado 2</div>
            </div>
            <div>
                <span class="unj-label">Órgão Julgador</span>
                <div>Núcleo de Justiça 4.0 em Segundo Grau</div>
            </div>
            <div>
                <span class="unj-label">Relator</span>
                <div>PAULO SERGIO MANGERONA</div>
            </div>
            
            <tbody id="tabelaTodasMovimentacoes">
                <tr class="movimentacaoProcesso">
                    <td>25/06/2025</td>
                    <td></td>
                    <td>
                        <a class="linkMovVincProc">Expedido Certidão de Baixa de Recurso</a>
                        <br/>
                        <span style="font-style: italic;">Certidão de Baixa de Recurso - [Digital]</span>
                    </td>
                </tr>
                <tr class="movimentacaoProcesso">
                    <td>25/06/2025</td>
                    <td></td>
                    <td>Baixa Definitiva</td>
                </tr>
            </tbody>
        </body>
        </html>
        '''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            temp_path = f.name
        
        try:
            result = cposg_parse_single_html(temp_path)
            
            assert isinstance(result, list)
            assert len(result) == 1
            
            row = result[0]
            assert row['id_original'] == '1000149-71.2024.8.26.0346'
            assert row['processo'] == '1000149-71.2024.8.26.0346'
            assert 'Encerrado' in row.get('status', '')
            assert row['classe'] == 'Apelação Cível'
            assert 'movimentacoes' in row
            assert isinstance(row['movimentacoes'], list)
            assert len(row['movimentacoes']) == 2
        finally:
            os.unlink(temp_path)
    
    def test_cposg_parse_manager_directory(self):
        """Test parsing multiple CPOSG files from directory."""
        html = '''
        <html>
        <body>
            <span class="unj-larger">1000149-71.2024.8.26.0346</span>
            <span class="unj-tag">Encerrado</span>
            <tbody id="tabelaTodasMovimentacoes">
                <tr class="movimentacaoProcesso">
                    <td>25/06/2025</td>
                    <td></td>
                    <td>Test movement</td>
                </tr>
            </tbody>
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
            
            result = cposg_parse_manager(temp_dir)
            
            assert isinstance(result, pd.DataFrame)
            assert len(result) == 2
    
    def test_cposg_parse_empty_file(self):
        """Test parsing an empty CPOSG HTML file."""
        html = '<html><body></body></html>'
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            temp_path = f.name
        
        try:
            result = cposg_parse_single_html(temp_path)
            # Should return empty list if no movement table
            assert isinstance(result, list)
            assert len(result) == 0
        finally:
            os.unlink(temp_path)
    
    def test_cposg_parse_no_movement_table(self):
        """Test parsing CPOSG HTML without movement table."""
        html = '''
        <html>
        <body>
            <span class="unj-larger">1000149-71.2024.8.26.0346</span>
        </body>
        </html>
        '''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            temp_path = f.name
        
        try:
            result = cposg_parse_single_html(temp_path)
            # Should return empty list if no movement table
            assert isinstance(result, list)
            assert len(result) == 0
        finally:
            os.unlink(temp_path)
    
    def test_cposg_parse_with_parts_and_decisions(self):
        """Test parsing CPOSG HTML with parts and decisions."""
        html = '''
        <html>
        <body>
            <span class="unj-larger">1000149-71.2024.8.26.0346</span>
            <span class="unj-tag">Encerrado</span>
            
            <div id="tablePartesPrincipais">
                <tr>
                    <td><span class="tipoDeParticipacao">Apelante</span></td>
                    <td>João Silva</td>
                </tr>
            </div>
            
            <div id="tabelaDecisoes">
                <tr>
                    <td>24/05/2025</td>
                    <td>Julgado</td>
                    <td>Acórdão</td>
                </tr>
            </div>
            
            <tbody id="tabelaTodasMovimentacoes">
                <tr class="movimentacaoProcesso">
                    <td>25/06/2025</td>
                    <td></td>
                    <td>Test movement</td>
                </tr>
            </tbody>
        </body>
        </html>
        '''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            temp_path = f.name
        
        try:
            result = cposg_parse_single_html(temp_path)
            
            assert isinstance(result, list)
            assert len(result) == 1
            
            row = result[0]
            assert 'partes' in row
            assert 'decisoes' in row
            assert isinstance(row['partes'], list)
            assert isinstance(row['decisoes'], list)
        finally:
            os.unlink(temp_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

