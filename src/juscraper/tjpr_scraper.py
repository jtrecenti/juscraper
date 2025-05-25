"""
Raspador para o Tribunal de Justiça do Paraná (TJPR).
"""
import re
from typing import Optional, Union, List
import requests
from bs4 import BeautifulSoup
import pandas as pd
from tqdm import tqdm
from .base_scraper import BaseScraper

class TJPRScraper(BaseScraper):
    """Raspador para o Tribunal de Justiça do Paraná."""

    BASE_URL = "https://portal.tjpr.jus.br/jurisprudencia/publico/pesquisa.do?actionType=pesquisar"
    HOME_URL = "https://portal.tjpr.jus.br/jurisprudencia/"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0"
    )

    def __init__(self):
        super().__init__("TJPR")
        self.session = requests.Session()
        self.token: Optional[str] = None
        self.jsessionid: Optional[str] = None

    def _get_initial_tokens(self):
        resp = self.session.get(self.HOME_URL)
        resp.raise_for_status()
        self.jsessionid = self.session.cookies.get('JSESSIONID')
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all('a', href=True):
            m = re.search(r'tjpr\.url\.crypto=([a-f0-9]+)', a['href'])
            if m:
                self.token = m.group(1)
                break
        if not self.token:
            raise RuntimeError("Não foi possível extrair o token da página inicial.")

    def _get_ementa_completa(self, id_processo: str, criterio: str) -> str:
        """
        Busca a ementa completa via GET se houver "Leia mais...".
        """
        url = (
            (
                "https://portal.tjpr.jus.br/jurisprudencia/publico/pesquisa.do?"
                "actionType=exibirTextoCompleto"
                f"&idProcesso={id_processo}&criterio={criterio}"
            )
        )
        headers = {
            'accept': 'text/javascript, text/html, application/xml, text/xml, */*',
            'accept-language': 'pt-BR,pt;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
            'cache-control': 'no-cache',
            'pragma': 'no-cache',
            'referer': (
                'https://portal.tjpr.jus.br/jurisprudencia/publico/pesquisa.do?actionType=pesquisar'
            ),
            'user-agent': self.USER_AGENT,
            'x-prototype-version': '1.5.1.1',
            'x-requested-with': 'XMLHttpRequest',
        }
        cookies = {'JSESSIONID': self.jsessionid}
        resp = self.session.get(url, headers=headers, cookies=cookies)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, 'html.parser').get_text("\n", strip=True)

    def cjsg_download(
        self,
        termo: str,
        paginas: Union[int, list, range] = 1,
        data_julgamento_de: str = None,
        data_julgamento_ate: str = None,
        data_publicacao_de: str = None,
        data_publicacao_ate: str = None
    ) -> list:
        """
        Baixa resultados brutos da pesquisa de jurisprudência do TJPR (várias páginas).
        Retorna lista de HTMLs (um por página).
        """
        self._get_initial_tokens()
        url = "https://portal.tjpr.jus.br/jurisprudencia/publico/pesquisa.do?actionType=pesquisar"
        headers = {
            'accept-language': 'pt-BR,pt;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
            'cache-control': 'no-cache',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://portal.tjpr.jus.br',
            'pragma': 'no-cache',
            'referer': url,
            'user-agent': self.USER_AGENT,
        }
        cookies = {'JSESSIONID': self.jsessionid}
        # Determina o iterador de páginas
        if isinstance(paginas, int):
            paginas_iter = range(1, paginas+1)
        else:
            paginas_iter = list(paginas)
        resultados = []
        for pagina_atual in tqdm(paginas_iter, desc='Baixando páginas TJPR'):
            data = {
                'usuarioCienteSegredoJustica': 'false',
                'segredoJustica': 'pesquisar com',
                'id': '',
                'chave': '',
                'dataJulgamentoInicio': data_julgamento_de or '',
                'dataJulgamentoFim': data_julgamento_ate or '',
                'dataPublicacaoInicio': data_publicacao_de or '',
                'dataPublicacaoFim': data_publicacao_ate or '',
                'processo': '',
                'acordao': '',
                'idComarca': '',
                'idRelator': '',
                'idOrgaoJulgador': '',
                'idClasseProcessual': '',
                'idAssunto': '',
                'pageVoltar': pagina_atual - 1,
                'idLocalPesquisa': '1',
                'ambito': '-1',
                'descricaoAssunto': '',
                'descricaoClasseProcessual': '',
                'nomeComarca': '',
                'nomeOrgaoJulgador': '',
                'nomeRelator': '',
                'idTipoDecisaoAcordao': '',
                'idTipoDecisaoMonocratica': '',
                'idTipoDecisaoDuvidaCompetencia': '',
                'criterioPesquisa': termo,
                'pesquisaLivre': '',
                'pageSize': 10,
                'pageNumber': pagina_atual,
                'sortColumn': 'processo_sDataJulgamento',
                'sortOrder': 'DESC',
                'page': pagina_atual - 1,
                # 'pagina': str(pagina_atual),  # Não é enviado no curl
                'iniciar': 'Pesquisar',
            }
            resp = self.session.post(url, data=data, headers=headers, cookies=cookies)
            resp.raise_for_status()
            resultados.append(resp.text)
        return resultados

    def cjsg_parse(self, resultados_brutos: list, criterio: str = None) -> pd.DataFrame:
        """
        Extrai os dados relevantes dos HTMLs retornados pelo TJPR.
        Retorna um DataFrame com as decisões.
        """
        resultados = []
        for html in resultados_brutos:
            soup = BeautifulSoup(html, "html.parser")
            tabela = soup.select_one("table.resultTable.jurisprudencia")
            if not tabela:
                continue
            linhas = tabela.find_all("tr")[1:]  # pula o cabeçalho
            for row in linhas:
                cols = row.find_all("td")
                if len(cols) < 2:
                    continue
                # Primeira coluna: dados do processo
                dados_td = cols[0]
                ementa_td = cols[1]
                # Processo
                processo = ''
                processo_a = dados_td.find('a', class_='decisao negrito')
                if processo_a:
                    processo = processo_a.get_text(strip=True)
                else:
                    # fallback: procura por div após label Processo:
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
                    # Pode vir com o nome junto após o label
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
                    # pode ter o valor logo após o label
                    data_julgamento = data_label.split('Data Julgamento:')[-1].strip()
                    # ou pode estar em outro nó
                    if not data_julgamento:
                        next_sib = data_label.parent.find_next_sibling(text=True)
                        if next_sib:
                            data_julgamento = next_sib.strip()
                # Ementa
                ementa = ementa_td.get_text("\n", strip=True)
                # Detecta "Leia mais..." e busca a ementa completa
                if 'leia mais' in ementa.lower():
                    # idProcesso pode estar no input[name=idsSelecionados] na primeira coluna
                    input_id = dados_td.find('input', {'name': 'idsSelecionados'})
                    if input_id and 'value' in input_id.attrs:
                        id_processo = input_id['value']
                    else:
                        id_processo = ''
                    if id_processo and criterio:
                        try:
                            ementa = self._get_ementa_completa(id_processo, criterio)
                        except (requests.RequestException, AttributeError) as e:
                            ementa += (
                                f"\n[Erro ao buscar ementa completa: {e}]"
                            )
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

    def cjsg(
        self,
        query: str,
        paginas: Union[int, list, range] = 1,
        data_julgamento_de: str = None,
        data_julgamento_ate: str = None,
        data_publicacao_de: str = None,
        data_publicacao_ate: str = None,
        **kwargs
    ) -> pd.DataFrame:
        """
        Busca jurisprudência do TJPR de forma simplificada (download + parse).
        Retorna um DataFrame pronto para análise.
        """
        brutos = self.cjsg_download(
            termo=query,
            paginas=paginas,
            data_julgamento_de=data_julgamento_de,
            data_julgamento_ate=data_julgamento_ate,
            data_publicacao_de=data_publicacao_de,
            data_publicacao_ate=data_publicacao_ate,
            **kwargs
        )
        return self.cjsg_parse(brutos, query)


    def cpopg(self, id_cnj: Union[str, List[str]]):
        """Stub: Consulta de processos de 1º grau não implementada para TJPR."""
        raise NotImplementedError("Consulta de processos de 1º grau não implementada para TJPR.")

    def cposg(self, id_cnj: Union[str, List[str]]):
        """Stub: Consulta de processos de 2º grau não implementada para TJPR."""
        raise NotImplementedError("Consulta de processos de 2º grau não implementada para TJPR.")
