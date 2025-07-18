"""
Functions for parsing specific to TJPR
"""
import pandas as pd
from bs4 import BeautifulSoup
import requests

def cjsg_parse(
    htmls,
    criterio=None,
    session=None,
    jsessionid=None,
    user_agent=None,
):
    """
    Extracts relevant data from the HTMLs returned by TJPR.
    Returns a DataFrame with the decisions.
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
                if not relator:
                    next_sib = relator_label.parent.find_next_sibling(text=True)
                    if next_sib:
                        relator = next_sib.strip()
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
                if not data_julgamento:
                    next_sib = data_label.parent.find_next_sibling(text=True)
                    if next_sib:
                        data_julgamento = next_sib.strip()
            # Ementa
            ementa = ementa_td.get_text("\n", strip=True)
            # Detecta "Leia mais..." e busca a ementa completa
            if 'leia mais' in ementa.lower():
                input_id = dados_td.find('input', {'name': 'idsSelecionados'})
                if input_id and 'value' in input_id.attrs:
                    id_processo = input_id['value']
                else:
                    id_processo = ''
                if id_processo and criterio and session and jsessionid and user_agent:
                    try:
                        ementa = get_ementa_completa(
                            session, jsessionid, user_agent, id_processo, criterio
                        )
                    except (requests.RequestException, AttributeError) as e:
                        ementa += (f"\n[Erro ao buscar ementa completa: {e}]")
            resultados.append({
                'processo': processo,
                'orgao_julgador': orgao_julgador,
                'relator': relator,
                'data_julgamento': data_julgamento,
                'ementa': ementa,
            })
    df = pd.DataFrame(resultados)
    if not df.empty and 'data_julgamento' in df.columns:
        df['data_julgamento'] = pd.to_datetime(
            df['data_julgamento'], errors='coerce', dayfirst=True
        ).dt.date
    return df

def get_ementa_completa(
    session,
    jsessionid,
    user_agent,
    id_processo,
    criterio,
):
    """
    Fetches the complete minute of a process from TJPR.
    """
    url = (
        "https://portal.tjpr.jus.br/jurisprudencia/publico/pesquisa.do?"
        "actionType=exibirTextoCompleto"
        f"&idProcesso={id_processo}&criterio={criterio}"
    )
    headers = {
        'accept': 'text/javascript, text/html, application/xml, text/xml, */*',
        'accept-language': 'pt-BR,pt;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
        'cache-control': 'no-cache',
        'pragma': 'no-cache',
        'referer': (
            'https://portal.tjpr.jus.br/jurisprudencia/publico/pesquisa.do?actionType=pesquisar'
        ),
        'user-agent': user_agent,
        'x-prototype-version': '1.5.1.1',
        'x-requested-with': 'XMLHttpRequest',
    }
    cookies = {'JSESSIONID': jsessionid}
    resp = session.get(url, headers=headers, cookies=cookies)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, 'html.parser').get_text("\n", strip=True)
