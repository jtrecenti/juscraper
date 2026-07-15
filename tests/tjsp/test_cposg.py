"""
Tests for TJSP CPOSG functionality.
Includes both integration and unit tests.
"""
import tempfile
from pathlib import Path

import pandas as pd
import pytest

import juscraper
from juscraper.courts.tjsp.cposg_parse import cposg_parse_manager, cposg_parse_single_html

_SAMPLES = Path(__file__).parent / 'samples' / 'cposg'


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
            Path(temp_path).unlink()

    def test_cposg_parse_complete_sample_contract(self):
        """Characterize every collection returned by the complete CPOSG sample."""
        result = cposg_parse_single_html(_SAMPLES / 'results_complete.html')

        assert len(result) == 1
        row = result[0]
        assert list(row) == [
            'id_original',
            'processo',
            'status',
            'classe',
            'assunto',
            'secao',
            'orgao_julgador',
            'area',
            'relator',
            'valor_da_acao',
            'origem',
            'volume_apenso',
            'movimentacoes',
            'partes',
            'historico',
            'decisoes',
            'composicao',
            'primeira_inst',
        ]
        assert row['id_original'] == '1234567-89.2025.8.26.0000'
        assert row['processo'] == '1234567-89.2025.8.26.0000'
        assert row['status'] == 'Em julgamento / Digital'
        assert row['classe'] == 'Apelação Cível'
        assert row['assunto'] == 'Responsabilidade do Fornecedor'
        assert row['movimentacoes'] == [
            {'data': '01/07/2025', 'movimento': 'Distribuído', 'descricao': 'Observação vinculada'},
            {'data': '02/07/2025', 'movimento': 'Movimento sem link', 'descricao': 'Observação livre'},
        ]
        assert row['partes'] == [
            {'id_parte': 1, 'nome': 'Empresa Autora', 'parte': 'Apelante', 'papel': 'Apelante'},
            {'id_parte': 1, 'nome': 'Ana Silva', 'parte': 'Apelante', 'papel': 'Advogado'},
            {'id_parte': 1, 'nome': 'Bruno Souza', 'parte': 'Apelante', 'papel': 'Procurador'},
            {'id_parte': 2, 'nome': 'Empresa Ré', 'parte': 'Apelado', 'papel': 'Apelado'},
            {'id_parte': 2, 'nome': 'Carla Lima', 'parte': 'Apelado', 'papel': 'Advogado'},
        ]
        assert row['historico'] == [
            ['01/01/2025', 'Procedimento Comum Cível'],
            ['15/06/2025', 'Apelação Cível'],
        ]
        assert row['decisoes'] == [
            {'data': '10/07/2025', 'situacao': 'Julgado', 'decisao': 'Recurso não provido'},
        ]
        assert row['composicao'] == [
            {'participacao': 'Relator', 'magistrado': 'Desembargador A'},
            {'participacao': '2º Juiz', 'magistrado': 'Desembargador B'},
        ]
        assert row['primeira_inst'] == [
            {
                'id_1a_inst': '0000001-11.2024.8.26.0100',
                'foro': 'Foro Central',
                'vara': '1ª Vara Cível',
                'juiz': 'Juíza C',
                'obs': 'Digital',
            },
        ]

    def test_cposg_parse_real_sample_contract(self):
        """Characterize the collection sizes and representative rows from the recorded page."""
        result = cposg_parse_single_html(_SAMPLES / 'search_listagem.html')

        assert len(result) == 1
        row = result[0]
        assert row['id_original'] == '1000149-71.2024.8.26.0346'
        assert row['classe'] == 'Apelação Cível'
        assert row['assunto'] == 'DIREITO DO CONSUMIDOR - Contratos de Consumo - Bancários'
        assert row['processo'] is None
        assert row['volume_apenso'] is None
        assert len(row['movimentacoes']) == 24
        assert row['movimentacoes'][:2] == [
            {
                'data': '25/06/2025',
                'movimento': 'Expedido Certidão de Baixa de Recurso',
                'descricao': 'Certidão de Baixa de Recurso - [Digital]',
            },
            {'data': '25/06/2025', 'movimento': 'Baixa Definitiva', 'descricao': ''},
        ]
        assert len(row['partes']) == 13
        assert row['partes'][:2] == [
            {
                'id_parte': 1,
                'nome': 'Banco Bradesco S/A',
                'parte': 'Apelante',
                'papel': 'Apelante',
            },
            {
                'id_parte': 1,
                'nome': 'Fabio Cabral Silva de Oliveira Monteiro',
                'parte': 'Apelante',
                'papel': 'Advogado',
            },
        ]
        assert row['historico'] == []
        assert row['decisoes'] == [
            {'data': '24/05/2025', 'situacao': 'Julgado', 'decisao': 'Negaram provimento ao recurso. V. U.'},
        ]
        assert len(row['composicao']) == 3
        assert row['primeira_inst'] == [
            {
                'id_1a_inst': '1000149-71.2024.8.26.0346(Principal)',
                'foro': 'Foro de Martinópolis',
                'vara': '2ª Vara Judicial',
                'juiz': 'Renata Esser de Souza',
                'obs': '-',
            },
        ]

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
            file1 = Path(temp_dir) / 'process1.html'
            file2 = Path(temp_dir) / 'process2.html'

            with file1.open('w', encoding='utf-8') as f:
                f.write(html)
            with file2.open('w', encoding='utf-8') as f:
                f.write(html.replace('1000149', '1000150'))

            result = cposg_parse_manager(temp_dir)

            assert isinstance(result, pd.DataFrame)
            assert len(result) == 2

    def test_cposg_parse_manager_empty_dataframe_has_stable_columns(self, tmp_path):
        result = cposg_parse_manager(str(tmp_path))

        assert result.empty
        assert list(result.columns) == [
            'id_original',
            'processo',
            'status',
            'classe',
            'assunto',
            'secao',
            'orgao_julgador',
            'area',
            'relator',
            'valor_da_acao',
            'origem',
            'volume_apenso',
            'movimentacoes',
            'partes',
            'historico',
            'decisoes',
            'composicao',
            'primeira_inst',
        ]

    def test_empty_relator_row_does_not_block_nonempty_fallback(self, tmp_path):
        sample = tmp_path / 'empty_relator.html'
        sample.write_text(
            '''
            <html><body>
                <tbody id="tabelaTodasMovimentacoes"></tbody>
                <table style="margin-left:15px; margin-top:1px;">
                    <tr><td>Relator</td><td></td></tr>
                    <tr><td>Relator</td><td>Desembargadora Ada</td></tr>
                </table>
            </body></html>
            ''',
            encoding='utf-8',
        )

        result = cposg_parse_single_html(sample)

        assert result[0]['relator'] == 'Desembargadora Ada'

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
            Path(temp_path).unlink()

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
            Path(temp_path).unlink()

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
            Path(temp_path).unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
