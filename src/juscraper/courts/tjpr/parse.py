"""
Functions for parsing specific to TJPR
"""
import pandas as pd
import requests
from bs4 import BeautifulSoup

from juscraper.core.exceptions import RetryExhaustedError
from juscraper.core.http import RequestFn
from juscraper.core.parse_utils import coerce_date_columns

from .download import get_ementa_completa


def cjsg_parse(
    htmls,
    criterio=None,
    *,
    request_fn: RequestFn | None = None,
):
    """
    Extracts relevant data from the HTMLs returned by TJPR.
    Returns a DataFrame with the decisions.

    ``request_fn`` is used to fetch the full minute when a row is truncated
    with "Leia mais...". Without it the ementa stays truncated — useful for
    offline parsing of pre-downloaded pages.
    """
    resultados = []
    for html in htmls:
        soup = BeautifulSoup(html, "html.parser")
        tabela = soup.select_one("table.resultTable.jurisprudencia")
        if not tabela:
            continue
        linhas = tabela.find_all("tr")[1:]  # pula o cabeçalho
        for row in linhas:
            cols = row.find_all("td")
            if len(cols) < 2:
                continue
            dados_td = cols[0]
            ementa_td = cols[1]
            # Processo
            processo = ''
            processo_a = dados_td.find('a', class_='decisao negrito')
            if processo_a:
                processo = processo_a.get_text(strip=True)
            else:
                for div in dados_td.find_all('div'):
                    if 'Processo:' in div.get_text():
                        processo_div = div.find_all('div')
                        if processo_div:
                            processo = processo_div[0].get_text(strip=True)
            # Relator
            relator = ''
            relator_label = dados_td.find(string=lambda t: t and 'Relator:' in t)
            if relator_label:
                relator = relator_label.split('Relator:')[-1].strip()
                if not relator and relator_label.parent is not None:
                    next_sib = relator_label.parent.find_next_sibling(string=True)
                    if next_sib:
                        relator = str(next_sib).strip()
            # Órgão julgador
            orgao_julgador = ''
            orgao_label = dados_td.find(string=lambda t: t and 'Órgão Julgador:' in t)
            if orgao_label:
                orgao_julgador = orgao_label.split('Órgão Julgador:')[-1].strip()
            # Data julgamento
            data_julgamento = ''
            data_label = dados_td.find(string=lambda t: t and 'Data Julgamento:' in t)
            if data_label:
                data_julgamento = data_label.split('Data Julgamento:')[-1].strip()
                if not data_julgamento and data_label.parent is not None:
                    next_sib = data_label.parent.find_next_sibling(string=True)
                    if next_sib:
                        data_julgamento = str(next_sib).strip()
            # Ementa
            ementa = ementa_td.get_text("\n", strip=True)
            # Detecta "Leia mais..." e busca a ementa completa
            if 'leia mais' in ementa.lower():
                input_id = dados_td.find('input', {'name': 'idsSelecionados'})
                if input_id and 'value' in input_id.attrs:
                    id_processo = input_id['value']
                else:
                    id_processo = ''
                if id_processo and criterio and request_fn is not None:
                    try:
                        ementa = get_ementa_completa(request_fn, id_processo, criterio)
                    except (requests.RequestException, RetryExhaustedError, AttributeError) as e:
                        # RetryExhaustedError e RequestException sao engolidos para
                        # preservar a degradacao graciosa por linha — uma ementa
                        # truncada que falha no fetch nao deve derrubar o DataFrame.
                        ementa += (f"\n[Erro ao buscar ementa completa: {e}]")
            resultados.append({
                'processo': processo,
                'orgao_julgador': orgao_julgador,
                'relator': relator,
                'data_julgamento': data_julgamento,
                'ementa': ementa,
            })
    df = pd.DataFrame(resultados)
    coerce_date_columns(df, ["data_julgamento"], date_format="%d/%m/%Y")
    return df
