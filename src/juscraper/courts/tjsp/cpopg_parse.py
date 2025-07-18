"""
Parses downloaded files from the first-degree procedural query.
"""
import os
import glob
from tqdm import tqdm
from bs4 import BeautifulSoup
import pandas as pd

def cpopg_parse_manager(path: str):
    """
    Parses downloaded files from the first-degree procedural query and returns a dictionary
    with tables containing case elements.

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
    """
    Parses a downloaded file from the TJSP Consulta de Processos Originarios do Primeiro Grau (CPOPG).
    """
    # if file extension is html
    if path.endswith('.html'):
        result = cpopg_parse_single_html(path)
    elif path.endswith('.json'):
        result = cpopg_parse_single_json(path)
    else:
        raise ValueError(f"Unknown file extension for path: {path}")
    return result

def cpopg_parse_single_html(path: str):
    """
    Parses a downloaded HTML file from the TJSP Consulta de Processos Originarios do Primeiro Grau (CPOPG).
    """
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
                descricao_principal = descricao_html.find(text=True, recursive=False) or ""
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
    peticoes_div = soup.find("h2", text="Petições diversas")
    if peticoes_div:
        # Pegar a tabela que vem a seguir
        tabela_peticoes = peticoes_div.find_parent().find_next_sibling("table")
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
    """
    Parseia um arquivo JSON baixado com a função cpopg_download.
    """
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
    """
    Retorna os links para download de processos.
    """
    text = request.text
    bsoup = BeautifulSoup(text, 'html.parser')
    lista = bsoup.find('div', {'id': 'listagemDeProcessos'})
    links = []
    if lista is None:
        id_tag = bsoup.find('form', {'id': 'popupSenha'})
        if id_tag is None:
            return links
        href = id_tag.get('action')
        if 'show.do' in href:
            links.append(href)
    else:
        processos = lista.findAll('a')
        if processos is None:
            return links
    return links
