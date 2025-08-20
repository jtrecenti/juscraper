"""
Módulo para download de processos da consulta de jurisprudência do TJSP (CJPG).

Este módulo implementa a funcionalidade de download de decisões judiciais
do Primeiro Grau do Tribunal de Justiça de São Paulo através da interface
de Consulta de Jurisprudência de Primeiro Grau (CJPG).

Funcionalidades principais:
- Download paginado de resultados de busca de jurisprudência
- Suporte a filtros por classe, assunto, vara, período e número de processo
- Sistema de debug automático em caso de falhas na extração
- Controle de tempo entre requisições para evitar sobrecarga do servidor

Nota importante sobre contagem de documentos:
Este módulo baixa PÁGINAS de resultados, não documentos individuais.
Cada página pode conter múltiplos documentos (tipicamente 10 por página).
O número total de documentos processados será maior que o número de páginas baixadas.
"""
import logging
import os
import time
from datetime import datetime

import requests
from tqdm import tqdm

from ...utils.cnj import clean_cnj


def cjpg_download(
    pesquisa: str,
    session: requests.Session,
    u_base: str,
    download_path: str,
    sleep_time: float = 0.5,
    classes: list[str] | None = None,
    assuntos: list[str] | None = None,
    varas: list[str] | None = None,
    id_processo: str | None = None,
    data_inicio: str | None = None,
    data_fim: str | None = None,
    paginas: range | None = None,
    get_n_pags_callback=None
):
    """
    Baixa páginas de resultados da consulta de jurisprudência do TJSP (CJPG).

    Esta função realiza o download das páginas HTML contendo os resultados da busca
    de jurisprudência de primeiro grau do TJSP. Cada página contém tipicamente 10
    documentos/decisões judiciais.

    IMPORTANTE: Esta função baixa PÁGINAS de resultados, não documentos individuais.
    O número real de documentos será maior que o número de páginas baixadas.

    Fluxo de execução:
    1. Monta os parâmetros de consulta com base nos filtros fornecidos
    2. Faz a primeira requisição para obter informações sobre paginação
    3. Usa o callback para extrair o número total de páginas disponíveis
    4. Baixa sequencialmente todas as páginas do intervalo especificado
    5. Salva cada página como arquivo HTML separado com timestamp

    Sistema de debug:
    Em caso de erro na extração do número de páginas, o HTML da primeira página
    é automaticamente salvo em uma pasta 'cjpg_debug' para análise posterior.

    Args:
        pesquisa (str): Termo de busca livre para a jurisprudência.
        session (requests.Session): Sessão HTTP autenticada para as requisições.
        u_base (str): URL base do sistema ESAJ (ex: 'https://esaj.tjsp.jus.br/').
        download_path (str): Diretório base onde os arquivos serão salvos.
        sleep_time (float, optional): Tempo de espera entre requisições em segundos.
            Padrão: 0.5 segundos. Recomenda-se não usar valores muito baixos para
            evitar sobrecarga no servidor.
        classes (list[str], optional): Lista de códigos de classes processuais para filtro.
            Exemplo: ["11"] para Procedimento Comum, ["436"] para Execução de Título.
        assuntos (list[str], optional): Lista de códigos de assuntos para filtro.
            Exemplo: ["1058"] para Indenização, ["7325"] para Cobrança.
        varas (list[str], optional): Lista de códigos de varas para filtro.
            Exemplo: ["1001", "1002"] para varas específicas do foro.
        id_processo (str, optional): Número CNJ do processo para busca específica.
            Será automaticamente limpo usando a função clean_cnj().
        data_inicio (str, optional): Data de início do período de busca no formato
            'dd/mm/aaaa'. Exemplo: '01/01/2023'.
        data_fim (str, optional): Data de fim do período de busca no formato
            'dd/mm/aaaa'. Exemplo: '31/12/2023'.
        paginas (range, optional): Intervalo específico de páginas para download.
            Se None, baixa todas as páginas disponíveis. Exemplo: range(1, 6)
            baixa páginas 1 a 5.
        get_n_pags_callback (callable): Função callback que recebe a resposta HTTP
            da primeira página e retorna o número total de páginas disponíveis.
            OBRIGATÓRIO - a função falhará se não fornecido.

    Returns:
        str: Caminho do diretório onde os arquivos foram salvos.

    Raises:
        ValueError: Se get_n_pags_callback não for fornecido ou se houver erro
            na extração do número de páginas. Em caso de erro, o HTML de debug
            é salvo automaticamente.

    Exemplo de uso típico (através da classe TJSPScraper):
        >>> from juscraper.courts.tjsp import TJSPScraper
        >>> scraper = TJSPScraper(download_path="/tmp/downloads")
        >>> resultado = scraper.cjpg(
        ...     pesquisa="responsabilidade civil",
        ...     classes=["11"],  # Procedimento Comum
        ...     data_inicio="01/01/2023",
        ...     data_fim="31/12/2023",
        ...     paginas=range(0, 5)  # Baixa primeiras 5 páginas
        ... )
        >>> print(f"Documentos encontrados: {len(resultado)}")

    Nota: Esta função é normalmente chamada internamente pela classe TJSPScraper.
    O callback get_n_pags_callback é fornecido automaticamente pela biblioteca.

    Estrutura de arquivos criada:
        download_path/
        └── cjpg/
            └── YYYYMMDD_HHMMSS/  # timestamp da execução
                ├── cjpg_00001.html
                ├── cjpg_00002.html
                └── ...
    """
    # Preparação dos parâmetros de filtro: converte listas em strings separadas por vírgula
    # conforme esperado pela API do ESAJ
    assuntos_str = ','.join(assuntos) if assuntos is not None else None
    varas_str = ','.join(varas) if varas is not None else None
    classes_str = ','.join(classes) if classes is not None else None

    # Tratamento do número CNJ: remove formatação e garante que esteja limpo
    if id_processo is not None:
        id_processo = clean_cnj(id_processo)
    else:
        id_processo = ''

    # Montagem dos parâmetros de consulta conforme especificação da API do ESAJ
    # Estes parâmetros correspondem aos campos do formulário de busca na interface web
    query = {
        'conversationId': '',  # ID da sessão, vazio para nova consulta (ESAJ gerencia internamente)
        'dadosConsulta.pesquisaLivre': pesquisa,  # Termo de busca livre
        'tipoNumero': 'UNIFICADO',  # Tipo de numeração CNJ
        'numeroDigitoAnoUnificado': id_processo[:15],  # Primeiros 15 dígitos do CNJ (sequencial + dígito + ano)
        'foroNumeroUnificado': id_processo[-4:],  # Últimos 4 dígitos (código do foro/tribunal)
        'dadosConsulta.nuProcesso': id_processo,  # Número completo do processo
        'classeTreeSelection.values': classes_str,  # Filtros de classe processual
        'assuntoTreeSelection.values': assuntos_str,  # Filtros de assunto
        'dadosConsulta.dtInicio': data_inicio,  # Data de início da busca
        'dadosConsulta.dtFim': data_fim,  # Data de fim da busca
        'varasTreeSelection.values': varas_str,  # Filtros de vara
        'dadosConsulta.ordenacao': 'DESC'  # Ordenação decrescente (mais recentes primeiro)
    }

    # Executa a primeira requisição para obter a página inicial dos resultados
    # Esta requisição é necessária para determinar quantas páginas existem no total
    r0 = session.get(f"{u_base}cjpg/pesquisar.do", params=query)

    # Extrai o número total de páginas usando o callback fornecido
    try:
        if get_n_pags_callback is None:
            raise ValueError(
                "É necessário fornecer get_n_pags_callback para extrair o número de páginas."
            )
        n_pags = get_n_pags_callback(r0)
    except Exception as e:
        # Sistema de debug automático: salva o HTML da primeira página para análise
        # Isso permite investigar problemas na extração do número de páginas
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        debug_dir = os.path.join(download_path, "cjpg_debug")
        if not os.path.isdir(debug_dir):
            os.makedirs(debug_dir)
        debug_file = os.path.join(debug_dir, f"cjpg_primeira_pagina_{timestamp}.html")
        with open(debug_file, 'w', encoding='utf-8') as f:
            f.write(r0.text)

        # Log do erro com localização do arquivo de debug
        logger = logging.getLogger("juscraper.cjpg_download")
        logger.error(
            "Erro ao extrair número de páginas: %s. HTML salvo em: %s",
            str(e),
            debug_file
        )
        raise ValueError(
            f"Erro ao extrair número de páginas: {e}. HTML salvo em: {debug_file}"
        ) from e

    # Determinação do range de páginas a serem baixadas
    # Se não especificado, baixa todas as páginas disponíveis
    if paginas is None:
        paginas = range(1, n_pags + 1)
    else:
        # Ajusta o range para não exceder o número total de páginas
        start, stop, step = paginas.start, min(paginas.stop, n_pags + 1), paginas.step
        paginas = range(start, stop, step)

    # Criação do diretório de destino com timestamp para evitar conflitos
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"{download_path}/cjpg/{timestamp}"
    if not os.path.isdir(path):
        os.makedirs(path)

    # Loop principal de download das páginas
    # Cada iteração baixa uma página e salva como arquivo HTML
    for pag in tqdm(paginas, desc="Baixando páginas"):
        # Pausa entre requisições para evitar sobrecarga do servidor
        time.sleep(sleep_time)

        # Monta URL para navegação entre páginas
        # IMPORTANTE: O ESAJ usa indexação baseada em 1, mas nosso range usa base 0
        # Por isso o +1 é necessário para alinhamento correto
        u = f"{u_base}cjpg/trocarDePagina.do?pagina={pag + 1}&conversationId="
        r = session.get(u)

        # Salva o HTML da página com numeração formatada (5 dígitos)
        # O nome do arquivo mantém o +1 para consistência com a numeração do ESAJ
        file_name = f"{path}/cjpg_{pag + 1: 05d}.html"
        with open(file_name, 'w', encoding='utf-8') as f:
            f.write(r.text)

    # Retorna o caminho do diretório criado para uso posterior (parsing, etc.)
    return path
