from .base_scraper import BaseScraper
import requests
from bs4 import BeautifulSoup
from typing import Optional, List, Dict, Any, Union
from urllib.parse import urlencode
import pandas as pd

class TJRS_Scraper(BaseScraper):
    """Raspador para o Tribunal de Justiça do Rio Grande do Sul."""

    BASE_URL = "https://www.tjrs.jus.br/buscas/jurisprudencia/ajax.php"
    DEFAULT_PARAMS = {
        "tipo-busca": "jurisprudencia-mob",
        "client": "tjrs_index",
        "proxystylesheet": "tjrs_index",
        "lr": "lang_pt",
        "oe": "UTF-8",
        "ie": "UTF-8",
        "getfields": "*",
        "filter": "0",
        "entqr": "3",
        "content": "body",
        "accesskey": "p",
        "ulang": "",
        "entqrm": "0",
        "ud": "1",
        "start": "0",
        "aba": "jurisprudencia",
        "sort": "date:D:L:d1"
    }

    def __init__(self):
        super().__init__("TJRS")
        self.session = requests.Session()

    def cpopg(self, process_number: str):
        print(f"[TJRS] Consultando processo: {process_number}")
        # Implementação real da busca aqui

    def cposg(self, process_number: str):
        print(f"[TJRS] Consultando processo: {process_number}")
        # Implementação real da busca aqui

    def cjsg_download(
        self,
        termo: str,
        paginas: Union[int, list, range] = 1,
        classe: str = None,
        assunto: str = None,
        orgao_julgador: str = None,
        relator: str = None,
        data_julgamento_de: str = None,
        data_julgamento_ate: str = None,
        data_publicacao_de: str = None,
        data_publicacao_ate: str = None,
        tipo_processo: str = None,
        secao: str = None,
        **kwargs
    ) -> list:
        """
        Baixa resultados brutos da pesquisa de jurisprudência do TJRS (várias páginas).
        Retorna lista de resultados brutos (JSON).
        Parâmetro novo: secao ('civel', 'crime', ou None)
        """
        if isinstance(paginas, int):
            paginas_iter = range(0, paginas)
        else:
            # Permitir range(0, N), lista ou qualquer iterável, sempre converter para página correta
            paginas_iter = [p+1 for p in paginas]
        resultados = []
        for pagina_atual in paginas_iter:
            payload = {
                'aba': 'jurisprudencia',
                'realizando_pesquisa': '1',
                'pagina_atual': str(pagina_atual),
                'start': '0',  # sempre zero!
                'q_palavra_chave': termo,
                'conteudo_busca': kwargs.get('conteudo_busca', 'ementa_completa'),
                'filtroComAExpressao': kwargs.get('filtroComAExpressao', ''),
                'filtroComQualquerPalavra': kwargs.get('filtroComQualquerPalavra', ''),
                'filtroSemAsPalavras': kwargs.get('filtroSemAsPalavras', ''),
                'filtroTribunal': kwargs.get('filtroTribunal', '-1'),
                'filtroRelator': relator or '-1',
                'filtroOrgaoJulgador': orgao_julgador or '-1',
                'filtroTipoProcesso': tipo_processo or '-1',
                'filtroClasseCnj': classe or '-1',
                'assuntoCnj': assunto or '-1',
                'data_julgamento_de': data_julgamento_de or '',
                'data_julgamento_ate': data_julgamento_ate or '',
                'filtroNumeroProcesso': kwargs.get('filtroNumeroProcesso', ''),
                'data_publicacao_de': data_publicacao_de or '',
                'data_publicacao_ate': data_publicacao_ate or '',
                'facet': 'on',
                'facet.sort': 'index',
                'facet.limit': 'index',
                'wt': 'json',
                'ordem': kwargs.get('ordem', 'desc'),
                'facet_orgao_julgador': '',
                'facet_origem': '',
                'facet_relator_redator': '',
                'facet_ano_julgamento': '',
                'facet_nome_classe_cnj': '',
                'facet_nome_assunto_cnj': '',
                'facet_nome_tribunal': '',
                'facet_tipo_processo': '',
                'facet_mes_ano_publicacao': ''
            }
            if secao:
                secao_map = {"civel": "C", "crime": "P"}
                valor = secao_map.get(secao.lower())
                if valor:
                    payload["filtroSecao"] = valor
            from urllib.parse import urlencode
            parametros_str = urlencode(payload, doseq=True)
            data = {
                'action': 'consultas_solr_ajax',
                'metodo': 'buscar_resultados',
                'parametros': parametros_str
            }
            resp = self.session.post(self.BASE_URL, data=data)
            resp.raise_for_status()
            resultados.append(resp.json())
        return resultados

    def cjsg_parse(self, resultados_brutos: list) -> 'pd.DataFrame':
        import pandas as pd
        def clean_value(val):
            if isinstance(val, list):
                return val[0] if val else None
            return val
        resultados = []
        for data in resultados_brutos:
            docs = data.get('response', {}).get('docs', [])
            for doc in docs:
                url = (
                    clean_value(doc.get('url_html')) or
                    clean_value(doc.get('url_acordao')) or
                    clean_value(doc.get('url'))
                )
                if not url and doc.get('numero_processo'):
                    url = f"https://www.tjrs.jus.br/buscas/jurisprudencia/?numero_processo={clean_value(doc.get('numero_processo'))}"
                # Coletar todos os campos relevantes
                resultado = {
                    'processo': clean_value(doc.get('numero_processo')),
                    'relator': clean_value(doc.get('relator_redator')),
                    'orgao_julgador': clean_value(doc.get('orgao_julgador')),
                    'data_julgamento': clean_value(doc.get('data_julgamento')),
                    'data_publicacao': clean_value(doc.get('data_publicacao')),
                    'classe_cnj': clean_value(doc.get('nome_classe_cnj')),
                    'assunto_cnj': clean_value(doc.get('nome_assunto_cnj')),
                    'tribunal': clean_value(doc.get('nome_tribunal')),
                    'tipo_processo': clean_value(doc.get('tipo_processo')),
                    'url': url,
                    'ementa': clean_value(doc.get('ementa_completa')),
                    # Novos campos:
                    'documento_text': clean_value(doc.get('documento_text')),
                    'documento_tiff': clean_value(doc.get('documento_tiff')),
                    'ementa_text': clean_value(doc.get('ementa_text')),
                    'mes_ano_publicacao': clean_value(doc.get('mes_ano_publicacao')),
                    'origem': clean_value(doc.get('origem')),
                    'secao': clean_value(doc.get('secao')),
                    'ano_julgamento': clean_value(doc.get('ano_julgamento')),
                    'nome_relator': clean_value(doc.get('nome_relator')),
                    'ind_segredo_justica': clean_value(doc.get('ind_segredo_justica')),
                    'ementa_referencia': clean_value(doc.get('ementa_referencia')),
                    'cod_ementa': clean_value(doc.get('cod_ementa')),
                    'cod_classe_cnj': clean_value(doc.get('cod_classe_cnj')),
                    'cod_org_julg': clean_value(doc.get('cod_org_julg')),
                    'cod_redator': clean_value(doc.get('cod_redator')),
                    'cod_tipo_documento': clean_value(doc.get('cod_tipo_documento')),
                    'cod_tribunal': clean_value(doc.get('cod_tribunal')),
                    'cod_assunto_cnj': clean_value(doc.get('cod_assunto_cnj')),
                    'cod_relator': clean_value(doc.get('cod_relator')),
                    'cod_recurso': clean_value(doc.get('cod_recurso')),
                    'tipo_documento': clean_value(doc.get('tipo_documento')),
                    'dthr_criacao': clean_value(doc.get('dthr_criacao')),
                    '_version_': clean_value(doc.get('_version_')),
                }
                resultados.append(resultado)
        df = pd.DataFrame(resultados)
        for col in ["data_julgamento", "data_publicacao"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce').dt.date
        # Colocar as colunas principais no início
        principais = [
            'processo', 'relator', 'orgao_julgador', 'data_julgamento', 'data_publicacao',
            'classe_cnj', 'assunto_cnj', 'tribunal', 'tipo_processo', 'url', 'ementa',
            'documento_text'
        ]
        cols = [c for c in principais if c in df.columns] + [c for c in df.columns if c not in principais]
        df = df[cols]
        return df

    def cjsg(
        self,
        termo: str,
        paginas: Union[int, list, range] = 1,
        classe: str = None,
        assunto: str = None,
        orgao_julgador: str = None,
        relator: str = None,
        data_julgamento_de: str = None,
        data_julgamento_ate: str = None,
        data_publicacao_de: str = None,
        data_publicacao_ate: str = None,
        tipo_processo: str = None,
        secao: str = None,
        **kwargs
    ) -> 'pd.DataFrame':
        """
        Busca jurisprudência do TJRS de forma simplificada (download + parse).
        Parâmetro novo: secao ('civel', 'crime', ou None)
        Retorna um DataFrame pronto para análise.
        """
        brutos = self.cjsg_download(
            termo=termo,
            paginas=paginas,
            classe=classe,
            assunto=assunto,
            orgao_julgador=orgao_julgador,
            relator=relator,
            data_julgamento_de=data_julgamento_de,
            data_julgamento_ate=data_julgamento_ate,
            data_publicacao_de=data_publicacao_de,
            data_publicacao_ate=data_publicacao_ate,
            tipo_processo=tipo_processo,
            secao=secao,
            **kwargs
        )
        return self.cjsg_parse(brutos)
