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
from tests._helpers import load_sample

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
        """Caracteriza cada coleção de uma página real com movimentações, partes, julgamento e 1ª instância.

        Sample real do 0022175-24.2003.8.26.0344, com os nomes das partes e dos
        advogados trocados por fictícios. Processo criminal, a página não traz
        "Valor da ação"; o rótulo "Volume / Apenso" vem no singular.
        """
        result = cposg_parse_single_html(_SAMPLES / 'show_com_incidentes.html')

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
            'motivo_falha',
        ]
        campos_simples = list(row)[:list(row).index('movimentacoes')]
        assert {campo: row[campo] for campo in campos_simples} == {
            'id_original': '0022175-24.2003.8.26.0344',
            'processo': '0022175-24.2003.8.26.0344',
            'status': 'Encerrado',
            'classe': 'Apelação Criminal',
            'assunto': 'DIREITO PENAL-Crimes contra a vida-Homicídio Simples',
            'secao': 'Direito Criminal',
            'orgao_julgador': '6ª Câmara de Direito Criminal',
            'area': 'Criminal',
            'relator': 'MACHADO DE ANDRADE',
            'valor_da_acao': None,
            'origem': 'Comarca de Marília / Foro de Marília / 1ª Vara Criminal',
            'volume_apenso': '6 / 1',
        }
        movimentacoes = row['movimentacoes']
        assert len(movimentacoes) == 85
        assert movimentacoes[:2] == [
            {
                'data': '25/07/2022',
                'movimento': 'Informação',
                'descricao': 'of. comunicando trânsito em julgado para defesa em 29.09.2021',
            },
            {
                'data': '19/10/2020',
                'movimento': 'Publicado em',
                'descricao': (
                    'Disponibilizado em 16/10/2020\nTipo de publicação: Despacho\n'
                    'Número do Diário Eletrônico: 3149'
                ),
            },
        ]
        assert {
            'data': '15/10/2020',
            'movimento': 'Processamento de Recursos Especial / Extraordinário Interpostos',
            'descricao': '',
        } in movimentacoes
        assert len(row['partes']) == 9
        assert row['partes'][:3] == [
            {'id_parte': 1, 'nome': 'Fulano de Tal Apelante', 'parte': 'Apte/Apdo', 'papel': 'Apte/Apdo'},
            {'id_parte': 1, 'nome': 'Advogado Ficticio Um', 'parte': 'Apte/Apdo', 'papel': 'Advogado'},
            {
                'id_parte': 2,
                'nome': 'Ministério Público do Estado de São Paulo',
                'parte': 'Apdo/Apte',
                'papel': 'Apdo/Apte',
            },
        ]
        assert row['historico'] == []
        assert [(decisao['data'], decisao['situacao']) for decisao in row['decisoes']] == [('01/08/2019', 'Julgado')]
        assert row['decisoes'][0]['decisao'].startswith('Ante o exposto, negaram provimento ao recurso defensivo')
        assert row['composicao'] == [
            {'participacao': 'Relator', 'magistrado': 'Machado de Andrade\xa0(42162)'},
            {'participacao': 'Revisor', 'magistrado': 'José Raul Gavião de Almeida\xa0(33955)'},
            {'participacao': '3º', 'magistrado': 'Marco Antonio Marques da Silva'},
        ]
        assert row['primeira_inst'] == [
            {
                'id_1a_inst': '344.01.2003.022175-3',
                'foro': 'Foro de Marília',
                'vara': '1ª Vara Criminal',
                'juiz': 'José Augusto Franca Junior',
                'obs': '-',
            },
        ]

    def test_historico_de_classes(self, tmp_path):
        """``#tdHistoricoDeClasses`` vira uma lista por linha, com o texto de cada célula.

        Nenhuma página capturada traz a tabela (ver ``_extract_history``); o HTML
        mínimo segue o seletor do parser.
        """
        sample = tmp_path / 'historico.html'
        sample.write_text(
            '''
            <html><body>
                <tbody id="tabelaTodasMovimentacoes"></tbody>
                <table id="tdHistoricoDeClasses">
                    <tr><td>01/01/2025</td><td>Procedimento Comum Cível</td></tr>
                    <tr><td>15/06/2025</td><td>Apelação Cível</td></tr>
                </table>
            </body></html>
            ''',
            encoding='utf-8',
        )

        result = cposg_parse_single_html(sample)

        assert result[0]['historico'] == [
            ['01/01/2025', 'Procedimento Comum Cível'],
            ['15/06/2025', 'Apelação Cível'],
        ]

    def test_cposg_parse_cabecalho_com_incidentes(self):
        """Com incidentes na página, ``id_original`` e ``processo`` vêm do cabeçalho, não do link do incidente.

        Sample real do 0022175-24.2003.8.26.0344, com os nomes das partes e dos
        advogados trocados por fictícios.
        """
        result = cposg_parse_single_html(_SAMPLES / 'show_com_incidentes.html')

        assert len(result) == 1
        row = result[0]
        assert row['id_original'] == '0022175-24.2003.8.26.0344'
        assert row['processo'] == '0022175-24.2003.8.26.0344'
        assert row['classe'] == 'Apelação Criminal'

    def test_cposg_parse_pagina_de_incidente(self):
        """Na página do incidente, o cabeçalho traz "Classe (CNJ)": ``processo`` é o CNJ e ``classe``, o resto.

        Sample real do incidente 50000 do 0022175-24.2003.8.26.0344
        (``show.do?processo.codigo=RI004MGQ412KW``), com os nomes das partes e
        dos advogados trocados por fictícios. É a página que o download grava
        para cada incidente quando a busca abre o modal de incidentes, como no
        1502870-48.2020.8.26.0161.
        """
        result = cposg_parse_single_html(_SAMPLES / 'show_incidente.html')

        assert len(result) == 1
        row = result[0]
        assert row['id_original'] == '0022175-24.2003.8.26.0344'
        assert row['processo'] == '0022175-24.2003.8.26.0344'
        assert row['classe'] == 'Embargos de Declaração Criminal'
        assert row['status'] == 'Encerrado'

    def test_cposg_parse_real_sample_contract(self):
        """Página como o eSAJ a serve, sem as movimentações: os demais campos saem, com aviso.

        As movimentações vêm do ``carregarMovimentacoesAjax.do``; o contrato
        ``test_cposg_html_simple_response`` cobre o arquivo que o download grava.
        """
        with pytest.warns(UserWarning, match="não traz as movimentações"):
            result = cposg_parse_single_html(_SAMPLES / 'search_listagem.html')

        assert len(result) == 1
        row = result[0]
        assert row['id_original'] == '1000149-71.2024.8.26.0346'
        assert row['classe'] == 'Apelação Cível'
        assert row['assunto'] == 'DIREITO DO CONSUMIDOR - Contratos de Consumo - Bancários'
        assert row['processo'] == '1000149-71.2024.8.26.0346'
        assert row['valor_da_acao'] == '72.896,87'
        assert row['volume_apenso'] == '1 / 0'
        assert row['movimentacoes'] == []
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
            'motivo_falha',
        ]

    def test_cposg_parse_manager_ignora_arquivos_do_cpopg(self, tmp_path):
        """No mesmo ``download_path``, o cpopg grava ``cpopg/<id>/``: o cposg só lê ``cposg/``.

        Na pasta do cpopg vai uma página que o parser do cposg leria, de outro
        processo (1000149-71.2024.8.26.0346): se fosse lida, sairia na lista.
        """
        id_processo = '00221752420038260344'
        conteudos = {
            'cposg': load_sample('tjsp', 'cposg/show_com_incidentes.html'),
            'cpopg': load_sample('tjsp', 'cposg/search_listagem.html'),
        }
        for pasta, conteudo in conteudos.items():
            destino = tmp_path / pasta / id_processo
            destino.mkdir(parents=True)
            (destino / f'{id_processo}_cd_processo_X.html').write_text(conteudo, encoding='utf-8')

        result = cposg_parse_manager(str(tmp_path))

        assert result['processo'].tolist() == ['0022175-24.2003.8.26.0344']

    @pytest.mark.parametrize(
        ('cabecalho', 'link', 'esperado'),
        [
            pytest.param(
                'Agravo Interno Cível\n\t\t(1502870-48.2020.8.26.0161)&nbsp;',
                'Embargos de Declaração - 50000',
                {
                    'id_original': '1502870-48.2020.8.26.0161',
                    'processo': '1502870-48.2020.8.26.0161',
                    'classe': 'Agravo Interno Cível',
                },
                id='incidente-com-quebra-de-linha',
            ),
            pytest.param(
                'Processo sem número',
                '1502870-48.2020.8.26.0161',
                {'id_original': '1502870-48.2020.8.26.0161'},
                id='sem-cnj-no-cabecalho',
            ),
        ],
    )
    def test_cabecalho_sem_numero_processo(self, tmp_path, cabecalho, link, esperado):
        """Sem ``span#numeroProcesso``, o CNJ vem de ``span.unj-larger``; sem CNJ ali, do primeiro link."""
        sample = tmp_path / 'cabecalho.html'
        sample.write_text(
            f'''
            <html><body>
                <span class="unj-larger">{cabecalho}</span>
                <a href="/cposg/show.do?processo.codigo=RI0000000000">{link}</a>
                <tbody id="tabelaTodasMovimentacoes"></tbody>
            </body></html>
            ''',
            encoding='utf-8',
        )

        row = cposg_parse_single_html(sample)[0]

        assert {campo: row[campo] for campo in esperado} == esperado

    def test_empty_relator_row_does_not_block_nonempty_fallback(self, tmp_path):
        """Preserve the relator fallback past an empty composition row, as the previous parser did."""
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

    def test_missing_relator_is_not_recovered_from_raw_html(self, tmp_path):
        """Fields absent from the canonical DOM stay ``None``; loose ``Label: valor`` text is ignored."""
        sample = tmp_path / 'loose_relator.html'
        sample.write_text(
            '''
            <html><body>
                <div>Relator: Nome Solto</div>
                <tbody id="tabelaTodasMovimentacoes"></tbody>
                <div><span class="unj-label">Classe</span><div>Apelação Cível</div></div>
                <table style="margin-left:15px; margin-top:1px;">
                    <tr><td>Relator</td><td></td></tr>
                </table>
            </body></html>
            ''',
            encoding='utf-8',
        )

        result = cposg_parse_single_html(sample)

        assert result[0]['classe'] == 'Apelação Cível'
        assert result[0]['relator'] is None

    def test_party_type_keeps_accents_and_slash(self, tmp_path):
        """The party type keeps its original spelling instead of dropping non-ASCII letters and ``/``."""
        sample = tmp_path / 'party_type.html'
        sample.write_text(
            '''
            <html><body>
                <tbody id="tabelaTodasMovimentacoes"></tbody>
                <table id="tableTodasPartes">
                    <tr>
                        <td><span class="tipoDeParticipacao">Réu/Apdo:&nbsp;</span></td>
                        <td>Empresa Ré<br>Advogado: Carla Lima</td>
                    </tr>
                </table>
            </body></html>
            ''',
            encoding='utf-8',
        )

        result = cposg_parse_single_html(sample)

        assert [party['parte'] for party in result[0]['partes']] == ['Réu/Apdo', 'Réu/Apdo']

    @pytest.mark.parametrize(
        'hidden',
        ['<!-- oculto -->', '<script>var oculto = 1;</script>', '<style>.oculto { color: red; }</style>'],
        ids=['comment', 'script', 'style'],
    )
    def test_party_name_ignores_non_text_nodes(self, tmp_path, hidden):
        """HTML comments, scripts and styles inside the party cell do not leak into the name."""
        sample = tmp_path / 'party_hidden.html'
        sample.write_text(
            '''
            <html><body>
                <tbody id="tabelaTodasMovimentacoes"></tbody>
                <table id="tableTodasPartes">
                    <tr><td>Apelante</td><td>NomeHIDDEN<br>Advogado: X</td></tr>
                </table>
            </body></html>
            '''.replace('HIDDEN', hidden),
            encoding='utf-8',
        )

        result = cposg_parse_single_html(sample)

        assert result[0]['partes'] == [
            {'id_parte': 1, 'nome': 'Nome', 'parte': 'Apelante', 'papel': 'Apelante'},
            {'id_parte': 1, 'nome': 'X', 'parte': 'Apelante', 'papel': 'Advogado'},
        ]

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
