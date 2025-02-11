from .base_scraper import BaseScraper
from .utils import clean_cnj, split_cnj, format_cnj
import requests
import tempfile
from bs4 import BeautifulSoup
import urllib3
import warnings
import os
import pandas as pd
from urllib.parse import parse_qs, urlparse
import glob
import re
from datetime import datetime
import shutil
from tqdm import tqdm
from typing import Union, List, Literal
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
import unidecode

warnings.filterwarnings('ignore', category=urllib3.exceptions.InsecureRequestWarning)

class TJSP_Scraper(BaseScraper):
    """Raspador para o Tribunal de Justiça de São Paulo."""

    def __init__(self, login = None, password = None, verbose = 1, download_path = None, sleep_time = 0.5, **kwargs):
        super().__init__("TJSP")
        self.session = requests.Session()
        self.u_base = 'https://esaj.tjsp.jus.br/'
        self.api_base = 'https://api.tjsp.jus.br/'
        self.login = login
        self.password = password
        self.set_verbose(verbose)
        self.set_download_path(download_path)
        self.sleep_time = sleep_time
        if (login is not None) and (password is not None):
            self.auth(login, password)
    
    def set_download_path(self, path: str | None = None):
        if path is None:
            path = tempfile.mkdtemp()
        self.download_path = path

    def set_method(self, method: str):
        # raise exception if method is not html nor api
        """Define o método para acesso aos dados do TJSP.

        Args:
            method: string com o nome do método. Os métodos suportados são 'html' e 'api'.

        Raises:
            Exception: Se o método passado como parâmetro não for 'html' nem 'api'.
        """
        if method not in ['html', 'api']:
            raise Exception(f"Método {method} nao suportado. Os métodos suportados são 'html' e 'api'.")
        self.method = method
    
    def cpopg(self, id_cnj: Union[str, List[str]], method = 'html'):
        """Busca um processo na consulta de processos originários do primeiro grau.

        Args:
            id_cnj: string com o CNJ do processo, ou lista de strings com vários CNJs.
            method: string com o nome do método. Os métodos suportados são 'html' e 'api'. O padrão é 'html'.

        Returns:
            Um dicionário com os dados do processo. A chave é o CNJ do processo e o valor é outro dicionário com as informações do processo.

        Raises:
            Exception: Se o método passado como parâmetro não for 'html' nem 'api'.
        """
        self.set_method(method)
        path = f"{self.download_path}/cpopg/"
        self.cpopg_download(id_cnj, method)
        result = self.cpopg_parse(path)
        shutil.rmtree(path)
        return result
    
    def cpopg_download(self, id_cnj: Union[str, List[str]], method = 'html'):
        """Baixa um processo na consulta de processos originários do primeiro grau.

        Args:
            id_cnj: string com o CNJ do processo, ou lista de strings com vários CNJs.
            method: string com o nome do método. Os métodos suportados são 'html' e 'api'. O padrão é 'html'.

        Returns:
            None

        Raises:
            Exception: Se o método passado como parâmetro não for 'html' nem 'api'.
        """
        self.set_method(method)
        if isinstance(id_cnj, str):
            id_cnj = [id_cnj]
        if self.method == 'html':
            return self._cpopg_download_html(id_cnj)
        elif self.method == 'api':
            return self._cpopg_download_api(id_cnj)
    
    def _cpopg_download_api(self, id_cnj: list[str]):
        n_items = len(id_cnj)
        for idp in tqdm(id_cnj, total=n_items, desc="Baixando processos"):
            try:
                self._cpopg_download_api_single(idp)
                time.sleep(self.sleep_time)
            except Exception as e:
                print(f"Erro ao baixar o processo {idp}: {e}")
                continue

    def _cpopg_download_api_single(self, id_cnj: str):
        endpoint = 'processo/cpopg/search/numproc/'
        id_clean = clean_cnj(id_cnj)
        u = f"{self.api_base}{endpoint}{id_clean}"
        path = f"{self.download_path}/cpopg/{id_clean}"
        if not os.path.isdir(path):
            os.makedirs(path)
        # primeira requisicao
        r = self.session.get(u)
        if r.status_code != 200:
            raise Exception(f"A consulta à API falhou. Status code {r.status_code}.")
        else:
            with open(f"{path}/{id_clean}.json", 'w', encoding='utf-8') as f:
                f.write(r.text)

        json_response = r.json()
        if not json_response:
            print(f"Nenhum dado encontrado para o processo {id_clean}.")
            return ''


        for processo in json_response:
            cd_processo = processo['cdProcesso']

            # Endpoint para dados básicos
            endpoint_basicos = 'processo/cpopg/dadosbasicos/'
            u_basicos = f"{self.api_base}{endpoint_basicos}{cd_processo}"
            r0 = self.session.get(u_basicos)
            
            # Requisição para dados básicos
            r_basicos = self.session.post(u_basicos, json={'cdProcesso': cd_processo})
            if r_basicos.status_code != 200:
                raise Exception(f"A consulta à API falhou. Status code {r_basicos.status_code}.")
            else:
                with open(f"{path}/{cd_processo}_basicos.json", 'w', encoding='utf-8') as f:
                    f.write(r_basicos.text)

            # Componentes adicionais para buscar informações detalhadas
            componentes = ['partes', 'movimentacao', 'incidente', 'audiencia']

            for comp in componentes:
                endpoint_comp = f"processo/cpopg/{comp}/{cd_processo}"
                r_comp = self.session.get(f"{self.api_base}{endpoint_comp}")
                if r_comp.status_code == 200:
                    with open(f"{path}/{cd_processo}_{comp}.json", 'w', encoding='utf-8') as f:
                        f.write(r_comp.text)
                else:
                    raise Exception(f"Erro ao buscar {comp} para o processo {cd_processo}. Status: {r_comp.status_code}")
            
        return path

    def _cpopg_download_html(self, id_cnj: list[str]):
        n_items = len(id_cnj)
        for idp in tqdm(id_cnj, total=n_items, desc="Baixando processos"):
            try:
                self._cpopg_download_html_single(idp)
                time.sleep(self.sleep_time)
            except Exception as e:
                print(f"Erro ao baixar o processo {idp}: {e}")
                continue

    def _cpopg_download_html_single(self, id_cnj: str):
        # TODO lidar com segredo de justiça

        auth = self.is_authenticated()
        if not auth:
            if self.verbose:
                print("Esse método precisa de autenticação para funcionar.")
            auth = self.auth(self.login, self.password)
            if not auth:
                raise Exception("Não foi possivel autenticar no TJSP.")

        id_clean = clean_cnj(id_cnj)
        path = f"{self.download_path}/cpopg/{id_clean}"
        if not os.path.isdir(path):
            os.makedirs(path)

        id_format = format_cnj(id_clean)
        p = split_cnj(id_clean)
        u = f"{self.u_base}cpopg/search.do"
        parms = {
            'conversationId': '',
            'cbPesquisa': 'NUMPROC',
            'numeroDigitoAnoUnificado': f"{p['num']}-{p['dv']}.{p['ano']}",
            'foroNumeroUnificado': p['orgao'],
            'dadosConsulta.valorConsultaNuUnificado': id_format,
            'dadosConsulta.valorConsulta': '',
            'dadosConsulta.tipoNuProcesso': 'UNIFICADO',
            'dadosConsulta.localPesquisa.cdLocal': '-1',
            'gateway': 'true',
            'uuidCaptcha': ''
        }
        r = self.session.get(u, params=parms)
        links = self._get_cpopg_download_links(r)
        cd_processo = []
        for link in links:
            query_params = parse_qs(urlparse(link).query)
            codigo = query_params.get('processo.codigo', [None])[0]
            cd_processo.append(codigo)

        if (len(links) == 1):
            file_name = f"{path}/{id_clean}_{cd_processo[0]}.html"
            with open(file_name, 'w', encoding='utf-8') as f:
                f.write(r.text)
        else:
            for index, link in enumerate(links):
                u = f"{self.u_base}{link}"
                r = self.session.get(u)
                if r.status_code != 200:
                    raise Exception(f"A consulta à API falhou. Processo: {id_clean}; Código: {cd_processo[index]}, Status code {r.status_code}.")
                file_name = f"{path}/{id_clean}_{cd_processo[index]}.html"
                with open(file_name, 'w', encoding='utf-8') as f:
                    f.write(r.text)

        return path

    def _get_cpopg_download_links(self, request):
        text = request.text
        bsoup = BeautifulSoup(text, 'html.parser')
        lista = bsoup.find('div', {'id': 'listagemDeProcessos'})
        links = []
        if lista is None:
            id_tag = bsoup.find('form', {'id': 'popupSenha'})
            href = id_tag.get('action')
            if 'show.do' in href:
                links.append(href)
        else:
            processos = lista.findAll('a')
            for link in processos:
                href = link.get('href')
                if 'show.do' in href:
                    links.append(href)
        return links

    def cpopg_parse(self, path: str):
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
        if os.path.isfile(path):
            result = [self._cpopg_parse_single(path)]
        else:
            result = []
            arquivos = glob.glob(f"{path}/**/*.[hj][st]*", recursive=True)
            arquivos = [f for f in arquivos if os.path.isfile(f)]
            # remover arquivos json cujo nome nao acaba com um número
            arquivos = [f for f in arquivos if not f.endswith('.json') or f[-6:-5].isnumeric()]
            for file in tqdm(arquivos, desc="Processando documentos"):
                if os.path.isfile(file):
                    try:
                        single_result = self._cpopg_parse_single(file)
                    except Exception as e:
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
        return lista_empilhada
    
    def _cpopg_parse_single(self, path: str):
        # if file extension is html
        if path.endswith('.html'):
            result = self._cpopg_parse_single_html(path)
        elif path.endswith('.json'):
            result = self._cpopg_parse_single_json(path)
        return result
        
    def _cpopg_parse_single_html(self, path: str):
        from bs4 import BeautifulSoup
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
        # A tabela tem <tbody id="tabelaTodasMovimentacoes"> com várias <tr class="containerMovimentacao">
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
    
    def _cpopg_parse_single_json(self, path: str):
        # primeiro, vamos listar todos os arquivos que estão na mesma pasta que o arquivo que está em path
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

    def cposg(self, id_cnj: str):
        print(f"[TJSP] Consultando processo: {id_cnj}")
        # Implementação real da busca aqui

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
        path_result = self.cjsg_download(
            pesquisa, ementa, classe, assunto, comarca, orgao_julgador, 
            data_inicio, data_fim, baixar_sg, tipo_decisao, paginas
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
        # Configurar o driver do Chrome
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        driver = webdriver.Chrome(options=options)
        wait = WebDriverWait(driver, 10)

        # Acessar o site
        driver.get("https://esaj.tjsp.jus.br/cjsg/consultaCompleta.do")

        # Inserir parâmetros de busca
        driver.find_element(By.NAME, 'dados.buscaInteiroTeor').send_keys(pesquisa)
        time.sleep(0.5)

        if ementa:
            driver.find_element(By.NAME, 'dados.ementa').send_keys(ementa)
            time.sleep(0.5)

        if classe:
            driver.find_element(By.NAME, 'dados.classe').send_keys(classe)
            time.sleep(0.5)

        if assunto:
            driver.find_element(By.NAME, 'dados.assunto').send_keys(assunto)
            time.sleep(0.5)

        if comarca:
            driver.find_element(By.NAME, 'dados.comarca').send_keys(comarca)
            time.sleep(0.5)

        if orgao_julgador:
            driver.find_element(By.NAME, 'dados.orgaoJulgador').send_keys(orgao_julgador)
            time.sleep(0.5)

        if data_inicio:
            driver.find_element(By.NAME, 'dados.dtJulgamentoInicio').send_keys(data_inicio)
            time.sleep(0.5)

        if data_fim:
            driver.find_element(By.NAME, 'dados.dtJulgamentoFim').send_keys(data_fim)
            time.sleep(0.5)
        
        if not baixar_sg:
            driver.find_element(By.ID, 'origem2grau').click()
            time.sleep(0.25)
            driver.find_element(By.ID, 'origemRecursal').click()
            time.sleep(0.25)

        # Submeter o formulário de busca
        driver.find_element(By.ID, 'pbSubmit').click()
        time.sleep(1)
        
        n_pags = self._cjsg_n_pags(driver.page_source)

        # Se paginas for None, definir range para todas as páginas
        if paginas is None:
            paginas = range(1, n_pags + 1)
        if max(paginas) > n_pags:
            pag_min = min(paginas)
            paginas = range(pag_min, n_pags + 1)
        
        if self.verbose > 0:
            print(f"Total de páginas: {n_pags}")
            print(f"Paginas a serem baixadas: {list(paginas)}")

        # pega os cookies para usar requests nas próximas requisições
        cookies = driver.get_cookies()
        session = requests.Session()
        for cookie in cookies:
            session.cookies.set(cookie['name'], cookie['value'])

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        path = f"{self.download_path}/cjsg/{timestamp}"
        if not os.path.isdir(path):
            os.makedirs(path)

        for pag in tqdm(paginas, desc="Baixando documentos"):
            time.sleep(self.sleep_time)
            query = {
                'tipoDeDecisao': 'A' if tipo_decisao == 'acordao' else 'D',
                'pagina': pag,
                'conversationId': ''
            }
            u = f"{self.u_base}cjsg/trocaDePagina.do"
            r = session.get(u, params=query)
            file_name = f"{path}/cjsg_{pag:05d}.html"
            with open(file_name, 'w', encoding='utf-8') as f:
                f.write(r.text)

        # fechar a sessão do Selenium
        driver.quit()

        # Retornar os caminhos dos arquivos salvos
        return path

    def _cjsg_n_pags(self, txt):
        soup = BeautifulSoup(txt, "html.parser")
        td_npags = soup.find("td", bgcolor='#EEEEEE')
        txt_pag = td_npags.text
        rx = re.compile(r'(?<=de )[0-9]+')
        n_results = int(rx.findall(txt_pag)[0])
        n_pags = n_results // 20 + 1
        return n_pags
    
    def cjpg(
        self,
        pesquisa: str,
        classe: str | None = None,
        assunto: str | None = None,
        comarca: str | None = None,
        id_processo: str | None = None,
        data_inicio: str | None = None,
        data_fim: str | None = None,
        paginas: range | None = None,
    ):
        """
        Realiza uma busca por jurisprudencia com base nos parametros fornecidos, baixa os resultados,
        os analisa e retorna os dados analisados.

        Args:
            pesquisa (str): A consulta para a jurisprudencia.
            classe (str, opcional): A classe do processo. Padrao None.
            assunto (str, opcional): O assunto do processo. Padrao None.
            comarca (str, opcional): A comarca do processo. Padrao None.
            id_processo (str, opcional): O ID do processo. Padrao None.
            data_inicio (str, opcional): A data de inicio para a busca. Padrao None.
            data_fim (str, opcional): A data de fim para a busca. Padrao None.
            paginas (range, opcional): A faixa de paginas a serem buscadas. Padrao None.

        Retorna:
            pd.DataFrame: Os dados analisados da jurisprudencia baixada.
        """

        path_result = self.cjpg_download(pesquisa, classe, assunto, comarca, id_processo, data_inicio, data_fim, paginas)
        data_parsed = self.cjpg_parse(path_result)
        # delete folder
        shutil.rmtree(path_result)
        return data_parsed
    
    def cjpg_download(
        self, 
        pesquisa: str,
        classe: str | None = None,
        assunto: str | None = None,
        comarca: str | None = None,
        id_processo: str | None = None,
        data_inicio: str | None = None,
        data_fim: str | None = None,
        paginas: range | None = None,
    ):
        """
        Baixa os processos da jurisprud ncia do TJSP

        Args:
            pesquisa (str): A consulta para a jurisprud ncia.
            classe (str, opcional): A classe do processo. Padr o None.
            assunto (str, opcional): O assunto do processo. Padr o None.
            comarca (str, opcional): A comarca do processo. Padr o None.
            id_processo (str, opcional): O ID do processo. Padr o None.
            data_inicio (str, opcional): A data de in cio para a busca. Padr o None.
            data_fim (str, opcional): A data de fim para a busca. Padr o None.
            paginas (range, opcional): A faixa de p ginas a serem buscadas. Padr o None.

        Retorna:
            str: O caminho da pasta onde os processos foram baixados.
        """
        if assunto is not None:
            assunto = ','.join(assunto)
        if comarca is not None:
            comarca = ','.join(comarca)
        if classe is not None:
            classe = ','.join(classe)
        if id_processo is not None:
            id_processo = clean_cnj(id_processo)
        else:
            id_processo = ''

        # query de busca
        query = {
            'conversationId': '',
            'dadosConsulta.pesquisaLivre': pesquisa,
            'tipoNumero': 'UNIFICADO',
            'numeroDigitoAnoUnificado': id_processo[:15],
            'foroNumeroUnificado': id_processo[-4:],
            'dadosConsulta.nuProcesso': id_processo,
            'classeTreeSelection.values': classe,
            'assuntoTreeSelection.values': assunto,
            'dadosConsulta.dtInicio': data_inicio,
            'dadosConsulta.dtFim': data_fim,
            'varasTreeSelection.values': comarca,
            'dadosConsulta.ordenacao': 'DESC'
        }

        # fazendo a busca
        r0 = self.session.get(
            f"{self.u_base}cjpg/pesquisar.do",
            params=query
        )

        # calcula total de páginas
        n_pags = self._cjpg_n_pags(r0)

        # Se paginas for None, definir range para todas as páginas
        if paginas is None:
            paginas = range(1, n_pags + 1)
        else:
            start, stop, step = paginas.start, min(paginas.stop, n_pags + 1), paginas.step
            paginas = range(start, stop, step)

        if self.verbose:
            print(f"Total de páginas: {n_pags}")
            print(f"Paginas a serem baixadas: {list(paginas)}")

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        path = f"{self.download_path}/cjpg/{timestamp}"
        if not os.path.isdir(path):
            os.makedirs(path)

        for pag in tqdm(paginas, desc="Baixando documentos"):
            time.sleep(self.sleep_time)
            u = f"{self.u_base}cjpg/trocarDePagina.do?pagina={pag}&conversationId="
            r = self.session.get(u)
            file_name = f"{path}/cjpg_{pag:05d}.html"
            with open(file_name, 'w', encoding='utf-8') as f:
                f.write(r.text)
        
        return path
   
    def _cjpg_n_pags(self, r0):
        soup = BeautifulSoup(r0.content, "html.parser")
        page_element = soup.find(attrs={'bgcolor': '#EEEEEE'})
        if page_element:
            match = re.search(r'\d+$', page_element.get_text().strip())
            results = int(match.group()) if match else 0
            pags = results // 10 + 1
            return pags
        return 0
    
    def cjpg_parse(self, path: str):
        """
        Parseia os arquivos baixados com a função cjpg e retorna um DataFrame com
        as informações dos processos.

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
            result = [self._cjpg_parse_single(path)]
        else:
            result = []
            arquivos = glob.glob(f"{path}/**/*.ht*", recursive=True)
            arquivos = [f for f in arquivos if os.path.isfile(f)]
            for file in tqdm(arquivos, desc="Processando documentos"):
                if os.path.isfile(file):
                    try:
                        single_result = self._cjpg_parse_single(file)
                    except Exception as e:
                        print(f"Error processing {file}: {e}")
                        single_result = None
                        continue
                    if single_result is not None:
                        result.append(single_result)
        result = pd.concat(result, ignore_index=True)
        return result
    
    def _cjpg_parse_single(self, path: str):
        with open(path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'html.parser')
        processos = []
        div_dados_resultado = soup.find('div', {'id': 'divDadosResultado'})
        if div_dados_resultado:
            tr_processos = div_dados_resultado.find_all('tr', class_='fundocinza1')
            for tr_processo in tr_processos:
                dados_processo = {}
                tabela_dados = tr_processo.find('table')
                # id_processo
                link_inteiro_teor = tabela_dados.find('a', {'style': 'vertical-align: top'})
                if link_inteiro_teor:
                    dados_processo['cd_processo'] = link_inteiro_teor.get('name').split('-')[0] if link_inteiro_teor.get('name') else None
                    dados_processo['id_processo'] = link_inteiro_teor.find('span', class_='fonteNegrito').text.strip() if link_inteiro_teor.find('span', class_='fonteNegrito') else None

                # Outros campos
                linhas_detalhes = tabela_dados.find_all('tr', class_='fonte')
                for linha in linhas_detalhes:
                    strong = linha.find('strong')
                    if strong:
                        texto = linha.text.strip()
                        chave, valor = texto.split(':', 1)
                        chave = chave.strip().lower().replace(' ', '_').replace('-','')
                        valor = valor.strip()
                        if chave == 'data_de_disponibilização':
                            chave = 'data_disponibilizacao'                        
                        dados_processo[chave] = valor

                # Decisão
                div_decisao = tabela_dados.find('div', {'align': 'justify', 'style': 'display: none;'})
                if div_decisao:
                    spans = div_decisao.find_all('span')
                    if spans:
                        decisao_text = spans[-1].get_text(separator=" ", strip=True)
                    dados_processo['decisao'] = decisao_text
                processos.append(dados_processo)

        return pd.DataFrame(processos)

    def cjsg_parse(self, path: str):
        """
        Parseia os arquivos baixados da segunda instância (cjsg) e retorna um DataFrame com
        as informações dos processos.

        Parameters
        ----------
        path : str
            Caminho do arquivo ou da pasta que contém os arquivos HTML baixados.

        Returns
        -------
        result : pd.DataFrame
            DataFrame com as informações extraídas dos processos.
        """
        if os.path.isfile(path):
            result = [self._cjsg_parse_single(path)]
        else:
            result = []
            arquivos = glob.glob(f"{path}/**/*.ht*", recursive=True)
            arquivos = [f for f in arquivos if os.path.isfile(f)]
            for file in tqdm(arquivos, desc="Processando documentos"):
                try:
                    single_result = self._cjsg_parse_single(file)
                except Exception as e:
                    print(f"Error processing {file}: {e}")
                    continue
                if single_result is not None:
                    result.append(single_result)
        return pd.concat(result, ignore_index=True)


    def _cjsg_parse_single(self, path: str):
        with open(path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'html.parser')

        processos = []
        # Itera sobre cada registro de processo (cada <tr> com classe "fundocinza1")
        for tr in soup.find_all('tr', class_='fundocinza1'):
            tds = tr.find_all('td')
            if len(tds) < 2:
                continue
            # O segundo <td> contém os detalhes do processo
            details_td = tds[1]
            details_table = details_td.find('table')
            if not details_table:
                continue

            dados_processo = {}
            # Extrai o número do processo (texto do <a> com classes "esajLinkLogin downloadEmenta")
            proc_a = details_table.find('a', class_='esajLinkLogin downloadEmenta')
            if proc_a:
                dados_processo['processo'] = proc_a.get_text(strip=True)
                dados_processo['cd_acordao'] = proc_a.get('cdacordao')
                dados_processo['cd_foro'] = proc_a.get('cdforo')

            # Itera pelas linhas de detalhes (tr com classe "ementaClass2")
            for tr_detail in details_table.find_all('tr', class_='ementaClass2'):
                strong = tr_detail.find('strong')
                if not strong:
                    continue
                label = strong.get_text(strip=True)
                # remover acentos
                label = unidecode.unidecode(label)
                # Se for a linha da ementa, trata de forma especial
                if "Ementa:" in label:
                    visible_div = None
                    # Procura pela div invisível (aquela que possui "display: none" no atributo style)
                    for div in tr_detail.find_all('div', align="justify"):
                        style = div.get('style', 'display: none;')
                        if 'display: none' not in style:
                            visible_div = div
                            break
                    if visible_div:
                        ementa_text = visible_div.get_text(" ", strip=True)
                        ementa_text = ementa_text.replace("Ementa:", "").strip()
                        dados_processo['ementa'] = ementa_text
                else:
                    # Para as demais linhas, extrai o rótulo e o valor
                    full_text = tr_detail.get_text(" ", strip=True)
                    value = full_text.replace(label, "", 1).strip().lstrip(':').strip()
                    key = label.replace(":", "").strip().lower()
                    # Normaliza a chave (substitui espaços e caracteres especiais)
                    key = key.replace(" ", "_").replace("(", "").replace(")", "").replace("/", "_")
                    key = key.replace("_de_", "_").replace("_do_", "_")
                    if key != 'outros_numeros':
                        dados_processo[key] = value

            processos.append(dados_processo)

        return pd.DataFrame(processos)

    def is_authenticated(self):
        # Verifica se o usuário está autenticado no site do TJSP.
        #
        # Returns
        # -------
        # bool
        #     True se o usuário estiver autenticado, False caso contrário.
        u = f"{self.u_base}sajcas/verificarLogin.js"
        r = self.session.get(u)
        return 'true' in r.text

    def auth(self, login=None, password=None):
        """
        Realiza autenticação no site do TJSP.

        Parameters
        ----------
        login : str, optional
            Login do usuário no e-SAJ. Se não for informado, o método solicitará
            ao usuário.
        password : str, optional
            Senha do usuário no e-SAJ. Se não for informado, o método solicitará
            ao usuário.

        Returns
        -------
        bool
            True se a autenticação for bem sucedida, False caso contrário.

        Notes
        -----
        O método armazena o login e a senha informados como atributos da classe,
        para que possam ser reutilizados em outras chamadas.
        """
        print('Autenticando...')
        
        if self.is_authenticated():
            return True
        
        if (login is not None) and (password is not None):
            self.login = login
            self.password = password
        elif (self.login is not None) and (self.password is not None):
            pass
        else:
            self.login = input("Login e-SAJ: ")
            self.password = input("senha e-SAJ: ")        

        self.session.get(f"{self.u_base}esaj/portal.do?servico=740000", verify=False)

        # Obter página de login
        u_login = f"{self.u_base}sajcas/login?service={self.u_base}esaj/j_spring_cas_security_check"
        f_login = self.session.get(u_login, verify=False)

        # Obter parâmetros para POST
        soup = BeautifulSoup(f_login.content, "html.parser")
        lt = soup.find("input", {"name": "lt"})["value"]
        e2 = soup.find("input", {"name": "execution"})["value"]

        # Criar query POST
        query_post = {
            "username": self.login,
            "password": self.password,
            "lt": lt,
            "execution": e2,
            "_eventId": "submit",
            "pbEntrar": "Entrar",
            "signature": "",
            "certificadoSelecionado": "",
            "certificado": ""
        }
        self.session.post(u_login, data=query_post, verify=False)
        auth = self.is_authenticated()
        if self.verbose:
            if auth:
                print("Autenticação bem sucedida!")
            else:
                print("Autenticação falhou!")
        return auth



