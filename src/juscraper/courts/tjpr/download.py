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

def _extract_total_pages(html):
    """Extract total number of pages from TJPR pagination HTML."""
    soup = BeautifulSoup(html, "html.parser")
    # Look for the pagination info: "Página X de Y"
    pag_text = soup.find(string=re.compile(r'Página\s+\d+\s+de\s+\d+'))
    if pag_text:
        m = re.search(r'Página\s+\d+\s+de\s+(\d+)', pag_text)
        if m:
            return int(m.group(1))
    # Fallback: look for last page link
    page_links = soup.find_all('a', href=re.compile(r'pageNumber=\d+'))
    if page_links:
        max_page = 1
        for link in page_links:
            m = re.search(r'pageNumber=(\d+)', link['href'])
            if m:
                max_page = max(max_page, int(m.group(1)))
        return max_page
    return 1


def cjsg_download(
    session,
    user_agent,
    home_url,
    termo,
    paginas=None,
    data_julgamento_inicio=None,
    data_julgamento_fim=None,
    data_publicacao_inicio=None,
    data_publicacao_fim=None,
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

    def _fetch_page(pagina_atual):
        data = {
            'usuarioCienteSegredoJustica': 'false',
            'segredoJustica': 'pesquisar com',
            'id': '',
            'chave': '',
            'dataJulgamentoInicio': data_julgamento_inicio or '',
            'dataJulgamentoFim': data_julgamento_fim or '',
            'dataPublicacaoInicio': data_publicacao_inicio or '',
            'dataPublicacaoFim': data_publicacao_fim or '',
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
        return resp.text

    if paginas is None:
        # Download all: fetch first page, extract total, then fetch the rest
        first_html = _fetch_page(1)
        n_pags = _extract_total_pages(first_html)
        resultados = [first_html]
        if n_pags > 1:
            for pagina_atual in tqdm(range(2, n_pags + 1), desc='Baixando páginas TJPR'):
                resultados.append(_fetch_page(pagina_atual))
        return resultados

    paginas_iter = list(paginas)
    resultados = []
    for pagina_atual in tqdm(paginas_iter, desc='Baixando páginas TJPR'):
        resultados.append(_fetch_page(pagina_atual))
    return resultados
