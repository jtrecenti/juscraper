"""
Tests for TJSP CPOPG functionality.
Includes both integration and unit tests.
"""
import os
import tempfile

import pandas as pd
import pytest

import juscraper
from juscraper.courts.tjsp.cpopg_parse import cpopg_parse_manager, cpopg_parse_single_html, get_cpopg_download_links
from tests._helpers import load_sample

from .test_utils import create_mock_response


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


    def test_parse_alternative_template(self):
        """Test parsing incidente template (unj-larger with CNJ, no id=numeroProcesso)."""
        html = '''
        <html><body>
        <div class="unj-entity-header__summary__barra">
            <div id="containerDadosPrincipaisProcesso" class="container">
                <div class="row">
                    <div class="col-lg-12 col-xl-13">
                        <span class="unj-label">Execução de Sentença</span>
                        <div>
                            <span class="unj-larger">
                                Cumprimento de Sentença contra a Fazenda Pública&nbsp;(0015615-74.2025.8.26.0577)
                            </span>
                        </div>
                    </div>
                </div>
                <div class="row">
                    <div class="col-lg-2 col-xl-3 mb-3">
                        <span class="unj-label">Assunto</span>
                        <div><span id="assuntoProcesso">Reajuste de Prestações</span></div>
                    </div>
                    <div class="col-lg-2 col-xl-2 mb-2">
                        <span class="unj-label">Foro</span>
                        <div><span id="foroProcesso">Foro de São José dos Campos</span></div>
                    </div>
                    <div class="col-lg-3 col-xl-2 mb-2">
                        <span class="unj-label">Vara</span>
                        <div><span id="varaProcesso">Anexo do Juizado Especial</span></div>
                    </div>
                </div>
            </div>
        </div>
        </body></html>
        '''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            temp_path = f.name

        try:
            result = cpopg_parse_single_html(temp_path)
            basicos = result['basicos'].iloc[0]

            assert basicos['id_processo'] == '0015615-74.2025.8.26.0577'
            assert basicos['classe'] == 'Cumprimento de Sentença contra a Fazenda Pública'
            assert basicos['assunto'] == 'Reajuste de Prestações'
            assert basicos['foro'] == 'Foro de São José dos Campos'
            assert basicos['vara'] == 'Anexo do Juizado Especial'
        finally:
            os.unlink(temp_path)

    def test_parse_extra_fields_standard_template(self):
        """Test extra fields (Outros assuntos, Controle) are captured in standard template."""
        html = '''
        <html><body>
        <div class="unj-entity-header__summary__barra">
            <div id="containerDadosPrincipaisProcesso" class="container">
                <div class="row">
                    <div class="col-lg-12">
                        <span id="numeroProcesso" class="unj-larger-1">1009367-76.2017.8.26.0344</span>
                    </div>
                </div>
                <div class="row">
                    <div class="col-lg-3">
                        <span class="unj-label">Classe</span>
                        <div><span id="classeProcesso">Procedimento Comum Cível</span></div>
                    </div>
                    <div class="col-lg-2">
                        <span class="unj-label">Foro</span>
                        <div><span id="foroProcesso">Foro de Marília</span></div>
                    </div>
                </div>
            </div>
        </div>
        <div id="maisDetalhes" class="collapse">
            <div class="row">
                <div class="col-lg-3 mb-2">
                    <span class="unj-label">Controle</span>
                    <div id="numeroControleProcesso">2017/006364</div>
                </div>
                <div class="col-lg-2 mb-2">
                    <span class="unj-label">Área</span>
                    <div id="areaProcesso"><span>Cível</span></div>
                </div>
                <div class="col-lg-2 mb-2">
                    <span class="unj-label">Outros assuntos</span>
                    <div><span>ICMS/ Imposto sobre Circulação de Mercadorias</span></div>
                </div>
            </div>
        </div>
        </body></html>
        '''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            temp_path = f.name

        try:
            result = cpopg_parse_single_html(temp_path)
            basicos = result['basicos'].iloc[0]

            assert basicos['id_processo'] == '1009367-76.2017.8.26.0344'
            assert basicos['classe'] == 'Procedimento Comum Cível'
            assert basicos['foro'] == 'Foro de Marília'
            assert basicos['controle'] == '2017/006364'
            assert basicos['area'] == 'Cível'
            assert basicos['outros_assuntos'] == 'ICMS/ Imposto sobre Circulação de Mercadorias'
        finally:
            os.unlink(temp_path)

    def test_parse_alternative_template_with_processo_principal(self):
        """Test incidente template captures Processo principal field."""
        html = '''
        <html><body>
        <div class="unj-entity-header__summary__barra">
            <div id="containerDadosPrincipaisProcesso" class="container">
                <div class="row">
                    <div class="col-lg-12 col-xl-13">
                        <span class="unj-label">Execução de Sentença</span>
                        <div>
                            <span class="unj-larger">
                                Cumprimento de Sentença contra a Fazenda Pública&nbsp;(0000384-69.2025.8.26.0136)
                            </span>
                            <span class="unj-tag">Extinto</span>
                        </div>
                    </div>
                </div>
                <div class="row">
                    <div class="col-lg-2 col-xl-3 mb-3">
                        <span class="unj-label">Assunto</span>
                        <div><span id="assuntoProcesso">Gratificações e Adicionais</span></div>
                    </div>
                    <div class="col-lg-2 col-xl-2 mb-2">
                        <span class="unj-label">Foro</span>
                        <div><span id="foroProcesso">Foro de Cerqueira César</span></div>
                    </div>
                    <div class="col-lg-3 col-xl-2 mb-2">
                        <span class="unj-label">Vara</span>
                        <div><span id="varaProcesso">Juizado Especial Cível e Criminal</span></div>
                    </div>
                    <div class="col-lg-4 col-xl-3 mb-2">
                        <span class="unj-label">Processo principal</span>
                        <div><a class="processoPrinc" href="#">1002742-24.2024.8.26.0136</a></div>
                    </div>
                </div>
            </div>
        </div>
        <div id="maisDetalhes" class="collapse">
            <div class="row">
                <div class="col-lg-3 mb-2">
                    <span class="unj-label">Recebido em </span>
                    <div id="dataHoraDistribuicaoProcesso">28/02/2025 às 12:15</div>
                </div>
                <div class="col-lg-3 mb-2">
                    <span class="unj-label">Controle</span>
                    <div id="numeroControleProcesso">2024/001363</div>
                </div>
                <div class="col-lg-2 mb-2">
                    <span class="unj-label">Área</span>
                    <div id="areaProcesso"><span>Cível</span></div>
                </div>
            </div>
        </div>
        </body></html>
        '''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            temp_path = f.name

        try:
            result = cpopg_parse_single_html(temp_path)
            basicos = result['basicos'].iloc[0]

            assert basicos['id_processo'] == '0000384-69.2025.8.26.0136'
            assert basicos['classe'] == 'Cumprimento de Sentença contra a Fazenda Pública'
            assert basicos['assunto'] == 'Gratificações e Adicionais'
            assert basicos['foro'] == 'Foro de Cerqueira César'
            assert basicos['vara'] == 'Juizado Especial Cível e Criminal'
            assert basicos['processo_principal'] == '1002742-24.2024.8.26.0136'
            assert basicos['data_distribuicao'] == '28/02/2025 às 12:15'
            assert basicos['controle'] == '2024/001363'
            assert basicos['area'] == 'Cível'
        finally:
            os.unlink(temp_path)

    def test_parse_alternative_template_from_sample(self):
        """Test parsing the alternative template sample HTML file."""
        html = load_sample('tjsp', 'cpopg/show_alternative.html')

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            temp_path = f.name

        try:
            result = cpopg_parse_single_html(temp_path)
            basicos = result['basicos'].iloc[0]

            assert basicos['id_processo'] == '0015615-74.2025.8.26.0577'
            assert basicos['classe'] == 'Cumprimento de Sentença contra a Fazenda Pública'
            assert basicos['assunto'] == 'Reajuste de Prestações'
            assert basicos['foro'] == 'Foro de São José dos Campos'
            assert basicos['processo_principal'] == '1010658-13.2025.8.26.0577'
            assert basicos['area'] == 'Cível'
            assert basicos['data_distribuicao'] == '28/02/2025 às 12:15'

            # Partes and movimentacoes should also be parsed
            assert len(result['partes']) == 1
            assert len(result['movimentacoes']) == 1
        finally:
            os.unlink(temp_path)

    def test_parse_standard_template_from_sample(self):
        """Test parsing the standard template sample HTML file with extra fields."""
        html = load_sample('tjsp', 'cpopg/show_standard.html')

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            temp_path = f.name

        try:
            result = cpopg_parse_single_html(temp_path)
            basicos = result['basicos'].iloc[0]

            # Standard ID-based fields
            assert basicos['id_processo'] == '1009367-76.2017.8.26.0344'
            assert basicos['classe'] == 'Procedimento Comum Cível'
            assert basicos['valor_acao'] == 'R$         10.000,00'
            assert basicos['juiz'] == 'WALMIR IDALENCIO DOS SANTOS CRUZ'

            # Extra fields from maisDetalhes
            assert basicos['controle'] == '2017/006364'
            assert basicos['area'] == 'Cível'
            assert basicos['outros_assuntos'] == 'ICMS/ Imposto sobre Circulação de Mercadorias'
        finally:
            os.unlink(temp_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
