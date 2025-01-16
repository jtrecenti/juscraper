from .base_scraper import BaseScraper
from .utils import clean_cnj, split_cnj, format_cnj
import requests
import tempfile
from bs4 import BeautifulSoup
import urllib3
import warnings
import os
import pdb
from urllib.parse import parse_qs, urlparse



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
                print(u)
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
        print(f"[TJSP] Consultando processo: {path}")
        if os.isfile(path):
            with open(path, 'r', encoding='utf-8') as f:
                html = f.read()
                soup = BeautifulSoup(html, 'html.parser')
        else:
            soup = None
        return soup

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
