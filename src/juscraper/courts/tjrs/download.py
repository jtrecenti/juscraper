"""
Downloads raw files from the TJRS jurisprudence search.
"""
from urllib.parse import urlencode
import requests
from tqdm import tqdm

def cjsg_download_manager(
    termo: str,
    paginas: 'Union[int, list, range]' = 1,
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
    session: requests.Session = None,
    **kwargs
) -> list:
    """
    Downloads raw files from the TJRS jurisprudence search (multiple pages).
    Returns a list of raw files (JSON).
    New parameter: secao ('civel', 'crime', or None)
    """
    base_url = "https://www.tjrs.jus.br/buscas/jurisprudencia/ajax.php"
    if session is None:
        session = requests.Session()
    if isinstance(paginas, int):
        paginas_iter = range(0, paginas)
    else:
        paginas_iter = [p+1 for p in paginas]
    resultados = []
    for pagina_atual in tqdm(paginas_iter, desc='Baixando páginas TJRS'):
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
        parametros_str = urlencode(payload, doseq=True)
        data = {
            'action': 'consultas_solr_ajax',
            'metodo': 'buscar_resultados',
            'parametros': parametros_str
        }
        resp = session.post(base_url, data=data)
        resp.raise_for_status()
        resultados.append(resp.json())
    return resultados
