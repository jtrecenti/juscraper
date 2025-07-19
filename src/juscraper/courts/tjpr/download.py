"""
Functions for downloading specific to TJPR
"""
import re
from bs4 import BeautifulSoup
from tqdm.auto import tqdm

def get_initial_tokens(session, home_url):
    """
    Extracts the JSESSIONID and the token from the TJPR initial page.
    """
    resp = session.get(home_url)
    resp.raise_for_status()
    jsessionid = session.cookies.get('JSESSIONID')
    token = None
    soup = BeautifulSoup(resp.text, "html.parser")
    for a in soup.find_all('a', href=True):
        m = re.search(r'tjpr\.url\.crypto=([a-f0-9]+)', a['href'])
        if m:
            token = m.group(1)
            break
    if not token:
        raise RuntimeError("Não foi possível extrair o token da página inicial.")
    return jsessionid, token

def get_ementa_completa(session, jsessionid, user_agent, id_processo, criterio):
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

def cjsg_download(
    session,
    user_agent,
    home_url,
    termo,
    paginas=1,
    data_julgamento_de=None,
    data_julgamento_ate=None,
    data_publicacao_de=None,
    data_publicacao_ate=None,
):
    """
    Downloads raw results from the TJPR 'jurisprudence search' (multiple pages).
    Returns a list of HTMLs (one per page).
    """
    jsessionid, _ = get_initial_tokens(session, home_url)
    url = "https://portal.tjpr.jus.br/jurisprudencia/publico/pesquisa.do?actionType=pesquisar"
    headers = {
        'accept-language': 'pt-BR,pt;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
        'cache-control': 'no-cache',
        'content-type': 'application/x-www-form-urlencoded',
        'origin': 'https://portal.tjpr.jus.br',
        'pragma': 'no-cache',
        'referer': url,
        'user-agent': user_agent,
    }
    cookies = {'JSESSIONID': jsessionid}
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
            'iniciar': 'Pesquisar',
        }
        resp = session.post(url, data=data, headers=headers, cookies=cookies)
        resp.raise_for_status()
        resultados.append(resp.text)
    return resultados
