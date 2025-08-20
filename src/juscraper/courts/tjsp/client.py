"""
Scraper principal para o Tribunal de Justiça de São Paulo (TJSP).

Este módulo implementa a interface principal para extração de dados do sistema ESAJ
do TJSP, suportando consultas a processos de primeiro e segundo grau, bem como
buscas na jurisprudência.

Sistemas suportados:
    - CPOPG: Consulta Processual de Primeiro Grau
    - CPOSG: Consulta Processual de Segundo Grau
    - CJPG: Consulta de Jurisprudência de Primeiro Grau
    - CJSG: Consulta de Jurisprudência de Segundo Grau

Cada sistema suporta dois métodos de acesso:
    - 'html': Scraping tradicional das páginas web (mais estável)
    - 'api': Acesso via API REST (mais rápido, mas pode ser instável)

PARA NOVOS COLABORADORES:
    - Sempre teste com sleep_time >= 0.5s em produção
    - Use método 'html' para maior estabilidade
    - Verifique rate limiting antes de fazer muitas requisições
    - CNJ deve seguir formato: NNNNNNN-DD.AAAA.J.TR.OOOO
    - Todos os métodos limpam arquivos temporários automaticamente

FLUXO ARQUITETURAL:
    1. client.py (esta interface) → 2. *_download.py → 3. *_parse.py → 4. dados estruturados
"""
import logging
import os
import shutil
import tempfile
import warnings
from typing import List, Literal, Union

import requests
import urllib3

from ...core.base import BaseScraper

# CJPG: Consulta de Jurisprudência de Primeiro Grau
from .cjpg_download import cjpg_download as cjpg_download_mod
from .cjpg_parse import cjpg_n_pags, cjpg_parse_manager

# CJSG: Consulta de Jurisprudência de Segundo Grau
from .cjsg_download import cjsg_download as cjsg_download_mod
from .cjsg_parse import cjsg_n_pags, cjsg_parse_manager

# CPOPG: Consulta Processual de Primeiro Grau
from .cpopg_download import cpopg_download_api, cpopg_download_html
from .cpopg_parse import cpopg_parse_manager, get_cpopg_download_links

# CPOSG: Consulta Processual de Segundo Grau
from .cposg_download import cposg_download_api, cposg_download_html
from .cposg_parse import cposg_parse_manager

# Módulos de download e parsing para cada sistema do TJSP
# A arquitetura modular separa claramente as responsabilidades:
# - *_download: responsáveis por acessar os sistemas e baixar dados brutos
# - *_parse: responsáveis por processar arquivos baixados em estruturas de dados

# Configuração de logging específica do TJSP
logger = logging.getLogger('juscraper.tjsp')

# Suprime avisos de certificados SSL para simplificar logs em desenvolvimento
# Em produção, considere remover esta linha e configurar certificados adequadamente
warnings.filterwarnings('ignore', category=urllib3.exceptions.InsecureRequestWarning)


class TJSPScraper(BaseScraper):
    """
    Scraper principal para o Tribunal de Justiça de São Paulo.

    Esta classe centraliza todas as operações de extração de dados do TJSP,
    oferecendo uma interface unificada para diferentes tipos de consulta.
    Segue o padrão de separação entre download e parsing para maior flexibilidade.

    Attributes:
        session (requests.Session): Sessão HTTP reutilizável para otimizar conexões
        u_base (str): URL base do sistema ESAJ
        api_base (str): URL base da API do TJSP
        download_path (str): Diretório para armazenamento temporário de arquivos
        sleep_time (float): Intervalo entre requisições para evitar bloqueios
        method (str): Método de acesso atual ('html' ou 'api')
    """

    def __init__(
        self,
        verbose: int = 0,
        download_path: str | None = None,
        sleep_time: float = 0.5,
        **kwargs
    ):
        """
        Inicializa o scraper para o TJSP.

        Configura a sessão HTTP, URLs base e diretório de trabalho. O scraper
        utiliza um diretório temporário por padrão para evitar conflitos entre
        execuções simultâneas.

        Args:
            verbose (int, optional): Nível de verbosidade do log.
                0 = sem logs, 1 = informações básicas, 2+ = debug detalhado.
                Default: 0.
            download_path (str, optional): Caminho para salvar arquivos baixados.
                Se None, usa diretório temporário. Default: None.
            sleep_time (float, optional): Tempo de espera entre requisições em segundos.
                Valores muito baixos podem causar bloqueio pelo servidor. Default: 0.5.
            **kwargs: Argumentos adicionais passados para a classe base.

        Note:
            O sleep_time é crucial para evitar rate limiting. Valores recomendados:
            - Produção: 0.5-1.0 segundos
            - Desenvolvimento/testes: 0.1-0.3 segundos
        """
        super().__init__("TJSP")

        # Configuração da sessão HTTP com headers padrão para evitar bloqueios
        # IMPORTANTE: O User-Agent é crucial para evitar detecção como bot
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; JuScraper/1.0)',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.8,en;q=0.6',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive'
        })

        # URLs base dos sistemas do TJSP
        self.u_base = 'https://esaj.tjsp.jus.br/'  # Sistema ESAJ (interface web)
        self.api_base = 'https://api.tjsp.jus.br/'  # API REST oficial

        # Configurações de operação
        self.set_verbose(verbose)
        self.set_download_path(download_path)
        self.sleep_time = sleep_time
        self.args = kwargs
        self.method = None  # Será definido pelos métodos de consulta

    def set_download_path(self, path: str | None = None):
        """
        Define o diretório base para salvamento de arquivos baixados.

        Cria um diretório temporário se nenhum caminho for especificado.
        O diretório temporário é automaticamente limpo ao final da execução.

        Args:
            path (str, optional): Caminho para salvar arquivos baixados.
                Se None, cria um diretório temporário único. Default: None.

        Note:
            Diretórios temporários são criados em /tmp (Linux/Mac) ou %TEMP% (Windows)
            e são automaticamente removidos pelo sistema operacional.
        """
        if path is None:
            path = tempfile.mkdtemp()
        self.download_path = path

    def set_method(self, method: Literal['html', 'api']):
        """
        Define o método de acesso aos dados do TJSP.

        Cada método tem vantagens e desvantagens:
        - 'html': Mais estável, menos propenso a mudanças, mas mais lento
        - 'api': Mais rápido e eficiente, mas pode ser instável ou indisponível

        Args:
            method (Literal['html', 'api']): Método de acesso aos dados.
                'html' = scraping das páginas web
                'api' = acesso via API REST oficial

        Raises:
            ValueError: Se o método não for 'html' ou 'api'.

        Example:
            >>> scraper = TJSPScraper()
            >>> scraper.set_method('api')  # Usar API para maior velocidade
            >>> scraper.set_method('html') # Usar HTML para maior estabilidade
        """
        if method not in ['html', 'api']:
            raise ValueError(
                f"Método {method} nao suportado."
                "Os métodos suportados são 'html' e 'api'."
            )
        self.method = method

    # MÉTODOS CPOPG - CONSULTA PROCESSUAL DE PRIMEIRO GRAU ----------------------
    def cpopg(self, id_cnj: Union[str, List[str]], method: Literal['html', 'api'] = 'html'):
        """
        Extrai dados completos de processo(s) de Primeiro Grau (CPOPG).

        Método principal que orquestra o download e parsing de processos.
        Automaticamente limpa arquivos temporários após o processamento.

        Args:
            id_cnj (Union[str, List[str]]): Número CNJ do processo ou lista de números.
                Formato: NNNNNNN-DD.AAAA.J.TR.OOOO (ex: '1234567-12.2023.8.26.0001')
            method (Literal['html', 'api']): Método de acesso. Default: 'html'.

        Returns:
            dict | List[dict]: Dados estruturados do(s) processo(s) incluindo:
                - Informações básicas (partes, classe, assunto)
                - Movimentações processuais
                - Links para documentos
                - Dados de distribuição e localização

        Example:
            >>> scraper = TJSPScraper()
            >>> dados = scraper.cpopg('1234567-12.2023.8.26.0001')
            >>> print(dados['classe'])  # Classe processual
            >>> print(len(dados['movimentacoes']))  # Número de movimentações
        """
        # FLUXO TÍPICO DE PROCESSAMENTO:
        # 1. Define método de acesso (HTML ou API)
        self.set_method(method)

        # 2. Baixa dados brutos para diretório temporário
        self.cpopg_download(id_cnj, method)

        # 3. Processa arquivos baixados em estruturas Python
        result = self.cpopg_parse(self.download_path)

        # 4. Limpa arquivos temporários (ESSENCIAL para evitar acúmulo)
        shutil.rmtree(self.download_path)

        return result

    def cpopg_download(
        self,
        id_cnj: Union[str, List[str]],
        method: Literal['html', 'api'] = 'html'
    ):
        """
        Baixa arquivos HTML/JSON de processo(s) de Primeiro Grau.

        Realiza o download dos dados brutos do sistema CPOPG, salvando-os
        no diretório de trabalho para posterior processamento. Suporta
        processamento em lote para múltiplos processos.

        Args:
            id_cnj (Union[str, List[str]]): Número CNJ ou lista de números.
                Cada número deve seguir o padrão CNJ completo.
            method (Literal['html', 'api']): Método de download.
                'html': Extrai dados das páginas web (mais lento, mais estável)
                'api': Usa endpoints REST (mais rápido, pode ser instável)

        Raises:
            ValueError: Se o método não for 'html' ou 'api'.
            requests.RequestException: Em caso de falha na comunicação.

        Note:
            - Método HTML: baixa página principal + documentos anexos
            - Método API: baixa apenas dados JSON estruturados
            - Arquivos são salvos com nomenclatura padronizada por CNJ
        """
        self.set_method(method)
        path = self.download_path

        # Normaliza entrada: sempre trabalha com lista internamente
        # Isso simplifica a lógica dos módulos de download
        if isinstance(id_cnj, str):
            id_cnj = [id_cnj]

        # ESTRATÉGIA DE DOWNLOAD POR MÉTODO:
        if self.method == 'html':
            # Método HTML: acessa páginas web do ESAJ
            # + Mais estável e confiável
            # + Extrai links para documentos anexos
            # - Mais lento devido ao parsing de HTML
            def get_links_callback(response):
                return get_cpopg_download_links(response)
            cpopg_download_html(
                id_cnj_list=id_cnj,
                session=self.session,
                u_base=self.u_base,
                download_path=path,
                sleep_time=self.sleep_time,
                get_links_callback=get_links_callback
            )
        elif self.method == 'api':
            # Método API: acessa endpoints REST oficiais
            # + Mais rápido e eficiente (JSON estruturado)
            # + Menor overhead de rede
            # - Pode ser instável ou ter mudanças sem aviso
            cpopg_download_api(
                id_cnj_list=id_cnj,
                session=self.session,
                api_base=self.api_base,
                download_path=path
            )
        else:
            raise ValueError(f"Método '{method}' não é suportado.")

    def cpopg_parse(self, path: str):
        """
        Processa arquivos baixados do CPOPG em dados estruturados.

        Converte os arquivos HTML/JSON baixados em estruturas de dados
        Python padronizadas, extraindo todas as informações relevantes
        do processo.

        Args:
            path (str): Caminho do diretório contendo os arquivos baixados.

        Returns:
            dict | List[dict]: Dados estruturados incluindo:
                - 'numero_cnj': Número CNJ do processo
                - 'classe': Classe processual
                - 'assunto': Assunto principal
                - 'partes': Lista de partes (autor, réu, etc.)
                - 'movimentacoes': Lista cronológica de movimentações
                - 'documentos': Links para peças processuais
                - 'dados_basicos': Informações de distribuição

        Note:
            Este método é automaticamente chamado por cpopg() e geralmente
            não precisa ser usado diretamente.
        """
        return cpopg_parse_manager(path)

    # MÉTODOS CPOSG - CONSULTA PROCESSUAL DE SEGUNDO GRAU ---------------------
    #
    # O sistema CPOSG gerencia processos em segunda instância (recursos, apelações).
    # Possui estrutura de dados diferente do CPOPG, com foco em decisões colegiadas
    # e movimentações de instâncias superiores.

    def cposg(self, id_cnj: str, method: Literal['html', 'api'] = 'html'):
        """
        Extrai dados completos de processo de Segundo Grau (CPOSG).

        Processa recursos e apelações em segunda instância, incluindo
        decisões colegiadas, relatores e informações recurssais.

        Args:
            id_cnj (str): Número CNJ do processo de segundo grau.
                Formato: NNNNNNN-DD.AAAA.J.TR.OOOO
            method (Literal['html', 'api']): Método de acesso. Default: 'html'.

        Returns:
            dict: Dados estruturados do processo incluindo:
                - Informações recurssais (origem, relator)
                - Decisões e acórdãos
                - Movimentações de segunda instância
                - Ligação com processo original (se aplicável)

        Example:
            >>> scraper = TJSPScraper()
            >>> recurso = scraper.cposg('7654321-98.2023.8.26.0000')
            >>> print(recurso['relator'])  # Desembargador relator
            >>> print(recurso['origem'])   # Vara de origem do recurso
        """
        self.set_method(method)
        path = self.download_path
        self.cposg_download(id_cnj, method)
        result = self.cposg_parse(path)
        if os.path.exists(path):
            shutil.rmtree(path)
        else:
            logger.warning("[TJSP] Aviso: diretório %s não existe e não pôde ser removido.", path)
        return result

    def cposg_download(self, id_cnj: Union[str, list], method: Literal['html', 'api'] = 'html'):
        """
        Baixa arquivos de processo(s) de Segundo Grau via HTML ou API.

        Utiliza funções modularizadas para acessar dados de recursos e
        apelações, adaptando-se às particularidades da segunda instância.

        Args:
            id_cnj (Union[str, list]): Número CNJ ou lista de números.
            method (Literal['html', 'api']): Método de download. Default: 'html'.

        Raises:
            ValueError: Se o método não for suportado.

        Note:
            - Processos de segundo grau têm estrutura diferente do primeiro grau
            - Inclui informações específicas de recursos (relator, câmara, etc.)
        """
        self.set_method(method)
        if isinstance(id_cnj, str):
            id_cnj = [id_cnj]
        if self.method == 'html':
            cposg_download_html(
                id_cnj_list=id_cnj,
                session=self.session,
                u_base=self.u_base,
                download_path=self.download_path,
                sleep_time=self.sleep_time
            )
        elif self.method == 'api':
            cposg_download_api(
                id_cnj_list=id_cnj,
                session=self.session,
                api_base=self.api_base,
                download_path=self.download_path,
                sleep_time=self.sleep_time
            )
        else:
            raise ValueError(f"Método '{method}' não é suportado.")

    def cposg_parse(self, path: str):
        """
        Processa arquivos baixados do CPOSG em dados estruturados.

        Converte dados brutos de segunda instância em estruturas padronizadas,
        extraindo informações específicas de recursos e apelações.

        Args:
            path (str): Caminho do diretório com arquivos baixados.

        Returns:
            dict: Dados estruturados incluindo:
                - 'relator': Desembargador relator
                - 'camara': Câmara ou turma julgadora
                - 'acordaos': Textos de acórdãos
                - 'origem': Dados da vara de origem
                - 'recurso_tipo': Tipo de recurso interposto

        Note:
            Automaticamente chamado por cposg(), geralmente não usado diretamente.
        """
        return cposg_parse_manager(path)

    # MÉTODOS CJSG - CONSULTA DE JURISPRUDÊNCIA DE SEGUNDO GRAU -----------------
    #
    # O sistema CJSG permite busca na jurisprudência de segunda instância do TJSP.
    # Ideal para pesquisa de precedentes, acórdãos e decisões colegiadas.
    # Suporta diversos filtros e download automático de páginas de resultados.

    def cjsg(
        self,
        pesquisa: str,
        ementa: str | None = None,
        classe: str | None = None,
        assunto: str | None = None,
        comarca: str | None = None,
        orgao_julgador: str | None = None,
        data_inicio: str | None = None,
        data_fim: str | None = None,
        baixar_sg: bool = True,
        tipo_decisao: str | Literal['acordao', 'monocratica'] = 'acordao',
        paginas: range | None = None,
    ):
        """
        Realiza consulta na jurisprudência de Segundo Grau do TJSP.

        Busca acórdãos e decisões monocráticas com múltiplos filtros,
        ideal para pesquisa de precedentes e análise jurisprudencial.

        Args:
            pesquisa (str): Termo de busca principal (obrigatório).
            ementa (str, optional): Filtro por texto da ementa.
            classe (str, optional): Classe processual (ex: 'Apelação').
            assunto (str, optional): Assunto jurídico específico.
            comarca (str, optional): Comarca de origem do processo.
            orgao_julgador (str, optional): Câmara/turma julgadora.
            data_inicio (str, optional): Data inicial (formato: dd/mm/aaaa).
            data_fim (str, optional): Data final (formato: dd/mm/aaaa).
            baixar_sg (bool): Se True, inclui dados de segundo grau. Default: True.
            tipo_decisao (str): Tipo de decisão ('acordao' ou 'monocratica'). Default: 'acordao'.
            paginas (range, optional): Intervalo de páginas (ex: range(1,5)).

        Returns:
            List[dict]: Lista de resultados da jurisprudência incluindo:
                - 'ementa': Texto da ementa
                - 'acordao': Link ou texto do acórdão
                - 'relator': Desembargador relator
                - 'data_julgamento': Data do julgamento
                - 'numero_processo': Número CNJ do processo

        Example:
            >>> scraper = TJSPScraper()
            >>> resultados = scraper.cjsg(
            ...     pesquisa='dano moral',
            ...     classe='Apelação',
            ...     data_inicio='01/01/2023',
            ...     data_fim='31/12/2023',
            ...     paginas=range(1, 3)  # Páginas 1 e 2
            ... )
            >>> print(f"Encontrados {len(resultados)} acórdãos")
        """
        path_result = self.cjsg_download(
            pesquisa=pesquisa,
            ementa=ementa,
            classe=classe,
            assunto=assunto,
            comarca=comarca,
            orgao_julgador=orgao_julgador,
            data_inicio=data_inicio,
            data_fim=data_fim,
            baixar_sg=baixar_sg,
            tipo_decisao=tipo_decisao,
            paginas=paginas
        )
        data_parsed = self.cjsg_parse(path_result)
        # delete folder
        shutil.rmtree(path_result)
        return data_parsed

    def cjsg_download(
        self,
        pesquisa: str,
        ementa: str | None = None,
        classe: str | None = None,
        assunto: str | None = None,
        comarca: str | None = None,
        orgao_julgador: str | None = None,
        data_inicio: str | None = None,
        data_fim: str | None = None,
        baixar_sg: bool = True,
        tipo_decisao: str | Literal['acordao', 'monocratica'] = 'acordao',
        paginas: range | None = None,
    ):
        """
        Baixa páginas HTML dos resultados da Consulta de Jurisprudência de Segundo Grau.

        Executa a busca no sistema CJSG e baixa todas as páginas de resultados
        especificadas, aplicando os filtros fornecidos.

        Args:
            pesquisa (str): Termo de busca principal.
            ementa (str, optional): Filtro adicional no texto da ementa.
            classe (str, optional): Classe processual (ex: 'Apelação', 'Agravo').
            assunto (str, optional): Assunto jurídico do processo.
            comarca (str, optional): Comarca de origem.
            orgao_julgador (str, optional): Câmara ou turma julgadora.
            data_inicio (str, optional): Data inicial no formato dd/mm/aaaa.
            data_fim (str, optional): Data final no formato dd/mm/aaaa.
            baixar_sg (bool): Se True, inclui dados de segundo grau. Default: True.
            tipo_decisao (str): Tipo ('acordao' ou 'monocratica'). Default: 'acordao'.
            paginas (range, optional): Páginas para baixar. Se None, baixa todas.

        Returns:
            str: Caminho do diretório com arquivos HTML baixados.

        Note:
            - range(0, n) baixa páginas 1 a n (inclusive), seguindo expectativa do usuário
            - Exemplo: range(0,3) baixa páginas 1, 2 e 3
            - Se paginas=None, detecta automaticamente o número total de páginas
        """
        return cjsg_download_mod(
            pesquisa=pesquisa,
            download_path=self.download_path,
            u_base=self.u_base,
            sleep_time=self.sleep_time,
            verbose=self.verbose,
            ementa=ementa,
            classe=classe,
            assunto=assunto,
            comarca=comarca,
            orgao_julgador=orgao_julgador,
            data_inicio=data_inicio,
            data_fim=data_fim,
            baixar_sg=baixar_sg,
            tipo_decisao=tipo_decisao,
            paginas=paginas,
            get_n_pags_callback=cjsg_n_pags
        )

    # MÉTODOS CJPG - CONSULTA DE JURISPRUDÊNCIA DE PRIMEIRO GRAU ----------------
    #
    # O sistema CJPG permite busca na jurisprudência de primeira instância do TJSP.
    # Ideal para pesquisar decisões de varas, sentenças e despachos.
    # Suporta filtros específicos de primeiro grau (varas, classes, etc.).

    def cjpg(
        self,
        pesquisa: str = '',
        classes: list[str] | None = None,
        assuntos: list[str] | None = None,
        varas: list[str] | None = None,
        id_processo: str | None = None,
        data_inicio: str | None = None,
        data_fim: str | None = None,
        paginas: range | None = None,
    ):
        """
        Realiza consulta na jurisprudência de Primeiro Grau do TJSP.

        Busca sentenças, decisões interlocutórias e despachos de primeira instância,
        com filtros específicos para varas e competências.

        Args:
            pesquisa (str): Termo de busca. Default: "" (busca geral).
            classes (list[str], optional): Lista de classes processuais.
                Exemplo: ['Procedimento Comum', 'Execução']
            assuntos (list[str], optional): Lista de assuntos jurídicos.
            varas (list[str], optional): Lista de varas específicas.
                Exemplo: ['1ª Vara Cível', '2ª Vara Criminal']
            id_processo (str, optional): Número do processo específico.
            data_inicio (str, optional): Data inicial (dd/mm/aaaa).
            data_fim (str, optional): Data final (dd/mm/aaaa).
            paginas (range, optional): Intervalo de páginas a baixar.

        Returns:
            List[dict]: Lista de decisões incluindo:
                - 'decisao': Texto da decisão/sentença
                - 'vara': Vara que proferiu a decisão
                - 'juiz': Nome do magistrado
                - 'data_decisao': Data da decisão
                - 'numero_processo': Número CNJ do processo

        Example:
            >>> scraper = TJSPScraper()
            >>> decisoes = scraper.cjpg(
            ...     pesquisa='responsabilidade civil',
            ...     classes=['Procedimento Comum'],
            ...     varas=['1ª Vara Cível de São Paulo'],
            ...     data_inicio='01/01/2023',
            ...     paginas=range(1, 3)
            ... )
            >>> print(f"Encontradas {len(decisoes)} decisões")
        """
        path_result = self.cjpg_download(
            pesquisa=pesquisa,
            classes=classes,
            assuntos=assuntos,
            varas=varas,
            id_processo=id_processo,
            data_inicio=data_inicio,
            data_fim=data_fim,
            paginas=paginas
        )
        data_parsed = self.cjpg_parse(path_result)
        # delete folder
        shutil.rmtree(path_result)
        return data_parsed

    def cjpg_download(
        self,
        pesquisa: str,
        classes: list[str] | None = None,
        assuntos: list[str] | None = None,
        varas: list[str] | None = None,
        id_processo: str | None = None,
        data_inicio: str | None = None,
        data_fim: str | None = None,
        paginas: range | None = None,
    ):
        """
        Baixa páginas HTML dos resultados da Consulta de Jurisprudência de Primeiro Grau.

        Executa a busca no sistema CJPG e baixa todas as páginas de resultados
        especificadas, aplicando os filtros fornecidos.

        Args:
            pesquisa (str): Termo de busca principal.
            classes (list[str], optional): Lista de classes processuais.
            assuntos (list[str], optional): Lista de assuntos jurídicos.
            varas (list[str], optional): Lista de varas específicas.
            id_processo (str, optional): Número do processo específico.
            data_inicio (str, optional): Data inicial no formato dd/mm/aaaa.
            data_fim (str, optional): Data final no formato dd/mm/aaaa.
            paginas (range, optional): Páginas para baixar. Se None, baixa todas.

        Returns:
            str: Caminho do diretório com arquivos HTML baixados.

        Note:
            - Se paginas=None, detecta automaticamente o número total de páginas
            - Arquivos são organizados por data e termo de busca
        """
        def get_n_pags_callback(response):
            # Callback para detectar número de páginas automaticamente
            # Pode receber requests.Response ou string HTML diretamente
            html = response.content if hasattr(response, 'content') else response
            return cjpg_n_pags(html)
        return cjpg_download_mod(
            pesquisa=pesquisa,
            session=self.session,
            u_base=self.u_base,
            download_path=self.download_path,
            sleep_time=self.sleep_time,
            classes=classes,
            assuntos=assuntos,
            varas=varas,
            id_processo=id_processo,
            data_inicio=data_inicio,
            data_fim=data_fim,
            paginas=paginas,
            get_n_pags_callback=get_n_pags_callback
        )

    def cjpg_parse(self, path: str):
        """
        Processa arquivos baixados do CJPG em dados estruturados.

        Converte páginas HTML da jurisprudência de primeiro grau em dados
        estruturados, extraindo informações de decisões e sentenças.

        Args:
            path (str): Caminho do diretório com arquivos HTML baixados.

        Returns:
            List[dict]: Lista de decisões estruturadas com metadados.

        Note:
            Automaticamente chamado por cjpg(), geralmente não usado diretamente.
        """
        return cjpg_parse_manager(path)

    def cjsg_parse(self, path: str):
        """
        Processa arquivos baixados do CJSG em dados estruturados.

        Converte páginas HTML da jurisprudência de segundo grau em dados
        estruturados, extraindo informações de acórdãos e decisões.

        Args:
            path (str): Caminho do diretório com arquivos HTML baixados.

        Returns:
            List[dict]: Lista de acórdãos estruturados com metadados.

        Note:
            Automaticamente chamado por cjsg(), geralmente não usado diretamente.
        """
        return cjsg_parse_manager(path)

# =============================================================================
# FLUXO DE DADOS E ARQUITETURA
# =============================================================================
#
# Este módulo implementa o padrão "Download-Parse-Clean" para cada sistema:
#
# 1. DOWNLOAD: Acesso aos sistemas via HTTP/API
#    - Implementa controle de rate limiting (sleep_time)
#    - Gerencia sessões HTTP reutilizáveis
#    - Suporta download em lote para múltiplos processos
#    - Salva arquivos brutos em diretórios temporários
#
# 2. PARSE: Processamento de dados brutos
#    - Extrai informações estruturadas de HTML/JSON
#    - Padroniza formatos de dados entre diferentes sistemas
#    - Gerencia encoding e caracteres especiais
#    - Valida completude dos dados extraídos
#
# 3. CLEAN: Limpeza automática de recursos
#    - Remove diretórios temporários após processamento
#    - Gerencia lifecycle de arquivos baixados
#    - Previne acúmulo de dados temporários
#
# OBSERVAÇÕES PARA DESENVOLVEDORES:
# - Sempre use sleep_time adequado para evitar bloqueios
# - Métodos HTML são mais estáveis que API
# - Diretórios temporários são criados automaticamente
# - Logs são controlados pelo parâmetro verbose
# - Todos os métodos públicos limpam recursos automaticamente
