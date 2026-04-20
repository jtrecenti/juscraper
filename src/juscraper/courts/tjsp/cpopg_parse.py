"""Parses downloaded files from the first-degree procedural query."""
import glob
import os
import re

import pandas as pd
from bs4 import BeautifulSoup
from tqdm import tqdm

# Mapping from normalized dt/dd labels to canonical dados keys
_CANONICAL_KEYS = {
    'assunto': 'assunto',
    'foro': 'foro',
    'vara': 'vara',
    'juiz': 'juiz',
    'classe': 'classe',
    'valor_da_acao': 'valor_acao',
    'distribuicao': 'data_distribuicao',
    'data_de_distribuicao': 'data_distribuicao',
    'recebido_em': 'data_distribuicao',
}

# Regex for CNJ process number format: NNNNNNN-DD.YYYY.J.TR.OOOO
_CNJ_PATTERN = re.compile(r'\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}')


def _normalize_field_name(label: str) -> str:
    """Convert a Portuguese label like 'Processo principal' to 'processo_principal'."""
    text = label.strip().rstrip(":")
    text = text.lower()
    # remove accents (simple approach for common Portuguese chars)
    replacements = {
        'á': 'a', 'à': 'a', 'ã': 'a', 'â': 'a',
        'é': 'e', 'ê': 'e',
        'í': 'i',
        'ó': 'o', 'ô': 'o', 'õ': 'o',
        'ú': 'u', 'ü': 'u',
        'ç': 'c',
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    text = re.sub(r'[^a-z0-9\s]', '', text)
    text = re.sub(r'\s+', '_', text.strip())
    return text


def cpopg_parse_manager(path: str):
    """Parse downloaded files from the first-degree procedural query and return a dict of DataFrames.

    Parameters
    ----------
    path : str
        The file path or directory containing the downloaded files.

    Returns
    -------
    dict
        A dictionary where the keys are table names and the values are DataFrames
        with the parsed data from the case files.
    """
    lista_empilhada = {}
    if os.path.isfile(path):
        result = [cpopg_parse_single(path)]
    else:
        result = []
        arquivos = glob.glob(f"{path}/**/*.[hj][st]*", recursive=True)
        arquivos = [f for f in arquivos if os.path.isfile(f)]
        # remover arquivos json cujo nome nao acaba com um número
        arquivos = [f for f in arquivos if not f.endswith('.json') or f[-6:-5].isnumeric()]
        for file in tqdm(arquivos, desc="Processando documentos"):
            if os.path.isfile(file):
                try:
                    single_result = cpopg_parse_single(file)
                except (OSError, UnicodeDecodeError, ValueError, AttributeError) as e:
                    print(f"Erro ao processar o arquivo {file}: {e}")
                    single_result = None
                    continue
                if single_result:
                    result.append(single_result)
        keys = result[0].keys()
        lista_empilhada = {
            key: pd.concat([dic[key] for dic in result], ignore_index=True)
            for key in keys
        }
    # Defensive: if result is empty, return an empty dict or suitable structure
    if not result:
        return lista_empilhada
    return lista_empilhada


def cpopg_parse_single(path: str):
    """Parse a downloaded file from the TJSP CPOPG consultation."""
    # if file extension is html
    if path.endswith('.html'):
        result = cpopg_parse_single_html(path)
    elif path.endswith('.json'):
        result = cpopg_parse_single_json(path)
    else:
        raise ValueError(f"Unknown file extension for path: {path}")
    return result


def cpopg_parse_single_html(path: str):
    """Parse a downloaded HTML file from the TJSP CPOPG consultation."""
    with open(path, 'r', encoding='utf-8') as f:
        html = f.read()
        soup = BeautifulSoup(html, 'html.parser')

    # 1) Dicionário-base para os dados coletados
    dados = {
        'file_path': path,
        'id_processo': None,
        'classe': None,
        'assunto': None,
        'foro': None,
        'vara': None,
        'juiz': None,
        'data_distribuicao': None,
        'valor_acao': None
    }

    movimentacoes = []
    partes = []
    peticoes_diversas = []

    # 2) Extrair dados básicos (identificadores no HTML)
    # -------------------------------------------------

    # número do processo
    numero_processo_tag = soup.find("span", id="numeroProcesso")
    if numero_processo_tag:
        dados['id_processo'] = numero_processo_tag.get_text(strip=True)

    # classe
    classe_tag = soup.find("span", id="classeProcesso")
    if classe_tag:
        dados['classe'] = classe_tag.get_text(strip=True)

    # assunto
    assunto_tag = soup.find("span", id="assuntoProcesso")
    if assunto_tag:
        dados['assunto'] = assunto_tag.get_text(strip=True)

    # foro
    foro_tag = soup.find("span", id="foroProcesso")
    if foro_tag:
        dados['foro'] = foro_tag.get_text(strip=True)

    # vara
    vara_tag = soup.find("span", id="varaProcesso")
    if vara_tag:
        dados['vara'] = vara_tag.get_text(strip=True)

    # juiz
    juiz_tag = soup.find("span", id="juizProcesso")
    if juiz_tag:
        dados['juiz'] = juiz_tag.get_text(strip=True)

    # data/hora de distribuição
    # (há um trecho: <div id="dataHoraDistribuicaoProcesso">19/04/2024 às 12:27 - Livre</div>)
    dist_tag = soup.find("div", id="dataHoraDistribuicaoProcesso")
    if dist_tag:
        dados['data_distribuicao'] = dist_tag.get_text(strip=True)

    # valor da ação
    valor_acao_tag = soup.find("div", id="valorAcaoProcesso")
    if valor_acao_tag:
        dados['valor_acao'] = valor_acao_tag.get_text(strip=True)

    # 2b) Fallback: incidente template (span.unj-larger contains class + CNJ)
    # Some processes (e.g. Execução de Sentença / Cumprimento de Sentença) don't have
    # id="numeroProcesso" or id="classeProcesso". Instead, the class is inside
    # <span class="unj-larger"> and the CNJ is in parentheses within that span.
    if dados['id_processo'] is None:
        larger_tag = soup.find("span", class_="unj-larger")
        if larger_tag:
            text = larger_tag.get_text(strip=True)
            match = _CNJ_PATTERN.search(text)
            if match:
                dados['id_processo'] = match.group(0)
            # The class is the text before the parenthesized CNJ
            if dados['classe'] is None:
                classe_text = re.sub(r'\s*\(.*$', '', text).replace('\xa0', ' ').strip()
                if classe_text:
                    dados['classe'] = classe_text

    # 2c) Extract extra fields from unj-label spans (Processo principal, Controle, Área, etc.)
    # Both templates use <span class="unj-label">Label</span> followed by a sibling <div>
    # containing the value. We skip labels that map to already-populated canonical fields.
    container = soup.find("div", id="containerDadosPrincipaisProcesso")
    mais_detalhes = soup.find("div", id="maisDetalhes")
    sections = [s for s in [container, mais_detalhes] if s is not None]
    for section in sections:
        for label_span in section.find_all("span", class_="unj-label"):
            label_text = label_span.get_text(strip=True)
            key = _normalize_field_name(label_text)
            if not key:
                continue
            # Skip pure section labels like "Classe", "Assunto" etc. that are already handled by IDs
            canonical = _CANONICAL_KEYS.get(key, key)
            if canonical in dados and dados[canonical] is not None:
                continue
            # Find the value: next sibling <div> in the same parent col-* div
            parent_col = label_span.find_parent("div", class_=re.compile(r'^col-'))
            if parent_col is None:
                continue
            value_div = parent_col.find("div")
            if value_div is None:
                continue
            # Skip category labels whose value div contains the unj-larger class header
            if value_div.find("span", class_="unj-larger"):
                continue
            value = value_div.get_text(strip=True)
            if not value:
                continue
            if canonical in dados:
                dados[canonical] = value
            else:
                dados[canonical] = value

    # 3) Extrair Partes e Advogados
    # -----------------------------
    # Tabela: <table id="tablePartesPrincipais">
    tabela_partes = soup.find("table", id="tablePartesPrincipais")
    if tabela_partes:
        # Geralmente as linhas têm classe "fundoClaro" ou "fundoEscuro"
        for tr in tabela_partes.find_all("tr"):
            # 1ª <td> = tipo de participação (ex: "Reqte", "Reqdo")
            # 2ª <td> = nome da parte e advogado(s)
            tds = tr.find_all("td")
            if len(tds) >= 2:
                tipo_tag = tds[0].find("span", class_="tipoDeParticipacao")
                tipo_parte = tipo_tag.get_text(strip=True) if tipo_tag else ""

                # Nome da parte + advogados
                parte_adv_html = tds[1]
                # Pode ter um <br>, ou "Advogado:" em <span>
                # Fazemos algo simples: pegue o texto todo e depois
                # tente separar parte e advogado manualmente, ou
                # identifique pelos spans
                nome_parte = ""
                advs = []

                # Pegar o texto *antes* do "Advogado:"
                # Procure <span class="mensagemExibindo">Advogado:</span> e separe
                raw_text = parte_adv_html.get_text("||", strip=True)
                # Exemplo de raw_text (com || como separador de <br>):
                # "Juan Bruno da Conceição Santos||Advogado:||Igor Galvão..."

                # Vamos quebrar por "Advogado:" e ver o que acontece
                if "Advogado:" in raw_text:
                    splitted = raw_text.split("Advogado:")
                    nome_parte = splitted[0].replace("||", " ").strip()
                    # splitted[1] pode conter o(s) advogado(s)
                    # Ex: "||Igor Galvão Venancio Martins||"
                    # ou "Igor Galvão Venancio Martins"
                    parte2 = splitted[1]
                    adv_raw = parte2.replace("||", " ").strip()
                    # Dependendo do caso pode ter mais advs na sequência; aqui vamos
                    # tratar como um só ou separar por vírgula, se for o caso.
                    # Ex.: "Igor Galvão Venancio Martins"
                    advs.append(adv_raw)
                else:
                    # Não tem "Advogado:"? Então é só a parte
                    nome_parte = raw_text.replace("||", " ").strip()

                if nome_parte:
                    partes.append({
                        'file_path': path,
                        "tipo": tipo_parte,
                        "nome": nome_parte,
                        "advogados": advs
                    })

    # 4) Extrair Movimentações
    # ------------------------
    # Podemos optar por pegar TODAS as movimentações (tabelaTodasMovimentacoes).
    # A tabela tem <tbody id="tabelaTodasMovimentacoes">
    # com várias <tr class="containerMovimentacao">
    tabela_todas = soup.find("tbody", id="tabelaTodasMovimentacoes")
    if tabela_todas:
        for tr in tabela_todas.find_all("tr", class_="containerMovimentacao"):
            # 1ª <td> = data
            # 3ª <td> = descrição
            tds = tr.find_all("td")
            if len(tds) >= 3:
                data = tds[0].get_text(strip=True)
                descricao_html = tds[2]
                # A "descrição" pode estar dividida em um texto principal e um <span> em itálico
                # Ex.: <span style="font-style: italic;">Some text</span>
                # Vamos concatenar
                descricao_principal = descricao_html.find(string=True, recursive=False) or ""
                descricao_principal = descricao_principal.strip()

                span_it = descricao_html.find("span", style="font-style: italic;")
                descricao_observacao = span_it.get_text(strip=True) if span_it else ""

                # Montar uma string única ou armazenar separadamente
                movimentacoes.append({
                    'file_path': path,
                    "data": data,
                    "movimento": descricao_principal,
                    "observacao": descricao_observacao
                })

    # 5) Petições diversas
    # --------------------
    # Tabela logo abaixo de "<h2 class="subtitle tituloDoBloco">Petições diversas</h2>"
    # No HTML, as datas ficam na primeira <td>, e o tipo no segundo <td>
    # Normalmente: <table> ... <tr class="fundoClaro"> <td>24/05/2024</td> <td>Contestação</td> ...
    peticoes_div = soup.find(lambda t: t.name == "h2" and t.get_text(strip=True) == "Petições diversas")
    if peticoes_div:
        # Pegar a tabela que vem a seguir
        tabela_peticoes = peticoes_div.find_next("table")
        if tabela_peticoes:
            for tr in tabela_peticoes.find_all("tr"):
                tds = tr.find_all("td")
                if len(tds) == 2:
                    data_peticao = tds[0].get_text(strip=True)
                    tipo_peticao = tds[1].get_text(strip=True)
                    # Às vezes pode vir "Contestação\n\n"
                    # limpamos com strip e etc
                    peticoes_diversas.append({
                        'file_path': path,
                        "data": data_peticao,
                        "tipo": tipo_peticao
                    })
    df_movs = pd.DataFrame(movimentacoes)
    df_partes = pd.DataFrame(partes)
    df_peticoes = pd.DataFrame(peticoes_diversas)
    df_basicos = pd.DataFrame([dados])

    result = {
        "basicos": df_basicos,
        "partes": df_partes,
        "movimentacoes": df_movs,
        "peticoes_diversas": df_peticoes
    }

    return result


def cpopg_parse_single_json(path: str):
    """Parse a JSON file downloaded by cpopg_download."""
    # primeiro, vamos listar todos os arquivos que estão na
    # mesma pasta que o arquivo que está em path
    lista_arquivos = glob.glob(f"{os.path.dirname(path)}/*.json")
    lista_processo = [f for f in lista_arquivos if f[-6:-5].isnumeric()][0]
    lista_arquivos = [f for f in lista_arquivos if f not in lista_processo]

    # agora, fazemos a leitura de cada arquivo e transformamos em um dataframe
    dfs = {}
    for arquivo in lista_arquivos:
        nome = os.path.basename(arquivo)
        # split name in two variables separating by _
        cd_processo, tipo = nome.split("_", 1)
        tipo = tipo.split(".", 1)[0]
        if 'basicos' in arquivo:
            df = pd.read_json(arquivo, orient='index').transpose()
        else:
            df = pd.read_json(arquivo, orient='records')
        df['cdProcesso'] = cd_processo
        if tipo not in dfs:
            dfs[tipo] = df
        else:
            dfs[tipo] = pd.concat([dfs[tipo], df], ignore_index=True)
    df_processo = pd.read_json(lista_processo, orient='records')
    df_processo = df_processo.merge(dfs['basicos'], how='left', on='cdProcesso')
    dfs['basicos'] = df_processo
    return dfs


def get_cpopg_download_links(request):
    """Return the download links for the listed processes."""
    text = request.text
    bsoup = BeautifulSoup(text, 'html.parser')
    lista = bsoup.find('div', {'id': 'listagemDeProcessos'})
    links: list = []
    if lista is None:
        id_tag = bsoup.find('form', {'id': 'popupSenha'})
        if id_tag is None:
            return links
        href = id_tag.get('action')
        if href is not None and 'show.do' in str(href):
            links.append(href)
    else:
        for a in lista.find_all('a', href=True):
            links.append(str(a['href']))
    return links
