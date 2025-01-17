from .base_scraper import BaseScraper
from .utils import clean_cnj, split_cnj, format_cnj
import requests
import tempfile
from bs4 import BeautifulSoup
import urllib3
import warnings
import os
import pdb
import pandas as pd
from urllib.parse import parse_qs, urlparse
import glob



warnings.filterwarnings('ignore', category=urllib3.exceptions.InsecureRequestWarning)

class TJSP_Scraper(BaseScraper):
    """Raspador para o Tribunal de Justiça de São Paulo."""

    def __init__(self, login = None, password = None, verbose = 1, download_path = None, **kwargs):
        super().__init__("TJSP")
        self.session = requests.Session()
        self.u_base = 'https://esaj.tjsp.jus.br/'
        self.api_base = 'https://api.tjsp.jus.br/'
        self.login = login
        self.password = password
        self.set_verbose(verbose)
        self.set_download_path(download_path)
        if (login is not None) and (password is not None):
            self.auth(login, password)

    def set_verbose(self, verbose: int):
        self.verbose = verbose
    
    def set_method(self, method: str):
        # raise exception if method is not html nor api
        if method not in ['html', 'api']:
            raise Exception(f"Método {method} nao suportado. Os métodos suportados são 'html' e 'api'.")
        self.method = method
    
    def set_download_path(self, path: str):
        # if path is None, define a default path in the temp directory
        if path is None:
            path = tempfile.mkdtemp()
        # check if path is a valid directory. If it is not, create it
        if not os.path.isdir(path):
            if self.verbose:
                print(f"O caminho de download '{path}' nao é um diretório. Criando esse diretório...")
            os.makedirs(path)
        self.download_path = path
        if self.verbose:
            print(f"Caminho de download definido como '{path}'.")
    
    def cpopg(self, id_cnj: str, method = 'html'):
        self.set_method(method)
        if self.verbose:
            print(f"[TJSP] Consultando processo de primeiro grau: {id_cnj}")
        id = clean_cnj(id_cnj)
        print("oioi")
    
    def cpopg_download(self, id_cnj: str, method = 'html'):
        self.set_method(method)
        if self.method == 'html':
            return self._cpopg_download_html(id_cnj)
        elif self.method == 'api':
            return self._cpopg_download_api(id_cnj)
    
    def _cpopg_download_api(self, id_cnj: str):
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

        cd_processo = json_response[0]['cdProcesso']

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

    def _cpopg_download_html(self, id_cnj: str):
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

        if r.status_code == 200 and self.verbose:
            print(f"[TJSP] Processo {id_clean} baixado com sucesso.")
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
        if os.path.isfile(path):
            result = [self._cpopg_parse_single(path)]
        else:
            result = []
            arquivos = glob.glob(f"{path}/**/*.[hj][st]*", recursive=True)
            arquivos = [f for f in arquivos if os.path.isfile(f)]
            for file in arquivos:
                if os.path.isfile(file):
                    single_result = self._cpopg_parse_single(file)
                    if single_result:
                        result.append(single_result)
            keys = result[0].keys()
            lista_empilhada = {
                key: pd.concat([dic[key] for dic in result], ignore_index=True)
                for key in keys
            }
        return result
    
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
        print(f"[TJSP] Consultando processo: {path}")
        # Implementação real da busca aqui

    def cposg(self, id_cnj: str):
        print(f"[TJSP] Consultando processo: {id_cnj}")
        # Implementação real da busca aqui

    def cjsg(self, pesquisa: str):
        print(f"[TJSP] Consultando jurisprudência: {pesquisa}")
        # Implementação real da busca aqui

    def is_authenticated(self):
        u = f"{self.u_base}sajcas/verificarLogin.js"
        r = self.session.get(u)
        return 'true' in r.text

    def auth(self, login=None, password=None):
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
