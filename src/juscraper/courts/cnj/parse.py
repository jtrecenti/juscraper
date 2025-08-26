"""Funções de parse para o scraper do Conselho Nacional de Justiça (CNJ)."""

import glob
import json
import os

import pandas as pd
from tqdm import tqdm


def cjpg_parse_manager(path: str):
    """
    Parseia os arquivos baixados com a função cjpg.

    Retorna um DataFrame com as informações dos processos.

    Parameters
    ----------
    path : str
        Caminho do arquivo ou da pasta que contém os arquivos baixados.

    Returns
    -------
    result : pd.DataFrame
        Dataframe com as informações dos processos.
    """
    if os.path.isfile(path):
        result = [cjpg_parse_single(path)]
    else:
        result = []
        arquivos = glob.glob(f"{path}/**/*.json", recursive=True)
        arquivos = [f for f in arquivos if os.path.isfile(f)]
        for file in tqdm(arquivos, desc="Processando documentos"):
            try:
                single_result = cjpg_parse_single(file)
            except Exception as e:
                print(f"Error processing {file}: {e}")
                single_result = None
                continue
            if single_result is not None:
                result.append(single_result)
    result = pd.concat(result, ignore_index=True)
    return result


def cjpg_parse_single(path: str):
    """Parseia um único arquivo JSON e retorna um DataFrame."""
    with open(path, 'r', encoding='utf-8') as f:
        dados = json.load(f)

    lista_infos = []

    infos_processos = dados['items']

    for processo in infos_processos:
        lista_infos.append(processo)

    return pd.DataFrame(lista_infos)
