"""Funções de download para o scraper do Conselho Nacional de Justiça (CNJ)."""

import os
import tempfile
import time
from datetime import datetime
from typing import Any, Dict, cast

import requests
from tqdm import tqdm


def cjpg_download(
    api_base: str,
    pesquisa: str,
    data_inicio: str | None = '2021-01-10',
    data_fim: str | None = None,
    paginas: range | None = None,
    sleep_time: int = 2,
    download_path: str | None = None,
):
    """
    Baixa os processos da jurisprud ncia do TJSP.

    Args:
        api_base (str): A URL base da API.
        pesquisa (str): A consulta para a jurisprud ncia.
        data_inicio (str, opcional): A data de in cio para a busca. Padr o None.
        data_fim (str, opcional): A data de fim para a busca. Padr o None.
        paginas (range, opcional): A faixa de p ginas a serem buscadas. Padr o None.
        sleep_time (int, opcional): O tempo de espera entre as requisi es. Padr o 2.
        download_path (str, opcional): O caminho para salvar os arquivos. Padr o None.

    Retorna:
        str: O caminho da pasta onde os processos foram baixados.
    """
    session = requests.Session()

    # query de busca
    query = {
            'itensPorPagina': 5,
            'texto': pesquisa,
            'dataDisponibilizacaoInicio': data_inicio
        }

    # fazendo a busca
    r0 = session.get(
        api_base,
        params=cast(Dict[str, Any], query)
    )

    # calcula total de páginas
    n_pags = _cjpg_n_pags(r0)

    # Se paginas for None, definir range para todas as páginas
    if paginas is None:
        paginas = range(1, n_pags + 1)
    else:
        start, stop, step = paginas.start, min(paginas.stop, n_pags + 1), paginas.step
        paginas = range(start, stop, step)

    print(f"Total de páginas: {n_pags}")
    print(f"Paginas a serem baixadas: {list(paginas)}")

    if download_path is None:
        download_path = tempfile.mkdtemp()

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    path = f"{download_path}/cjpg/{timestamp}"
    if not os.path.isdir(path):
        os.makedirs(path)

    for pag in tqdm(paginas, desc="Baixando documentos"):
        time.sleep(sleep_time)

        query = {
            'pagina': pag,
            'itensPorPagina': 5,
            'texto': pesquisa,
            'dataDisponibilizacaoInicio': data_inicio
        }
        if data_fim:
            query['dataDisponibilizacaoFim'] = data_fim

        r = session.get(api_base, params=cast(Dict[str, Any], query))  # sending the parameters.

        file_name = f"{path}/cjpg_{pag: 05d}.json"
        with open(file_name, 'w', encoding='utf-8') as f:
            f.write(r.text)

    return path


def _cjpg_n_pags(r0):
    contagem = r0.json()['count']
    return contagem // 5 + 1
