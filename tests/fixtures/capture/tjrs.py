"""Capture cjsg samples for TJRS.

Run from repo root::

    python -m tests.fixtures.capture.tjrs
"""
from urllib.parse import urlencode

import requests

from ._util import dump, samples_dir_for

BASE_URL = "https://www.tjrs.jus.br/buscas/jurisprudencia/ajax.php"


def _inner_params(pesquisa: str, pagina: int) -> dict:
    return {
        "aba": "jurisprudencia",
        "realizando_pesquisa": "1",
        "pagina_atual": str(pagina),
        "start": "0",
        "q_palavra_chave": pesquisa,
        "conteudo_busca": "ementa_completa",
        "filtroComAExpressao": "",
        "filtroComQualquerPalavra": "",
        "filtroSemAsPalavras": "",
        "filtroTribunal": "-1",
        "filtroRelator": "-1",
        "filtroOrgaoJulgador": "-1",
        "filtroTipoProcesso": "-1",
        "filtroClasseCnj": "-1",
        "assuntoCnj": "-1",
        "data_julgamento_de": "",
        "data_julgamento_ate": "",
        "filtroNumeroProcesso": "",
        "data_publicacao_de": "",
        "data_publicacao_ate": "",
        "facet": "on",
        "facet.sort": "index",
        "facet.limit": "index",
        "wt": "json",
        "ordem": "desc",
        "facet_orgao_julgador": "",
        "facet_origem": "",
        "facet_relator_redator": "",
        "facet_ano_julgamento": "",
        "facet_nome_classe_cnj": "",
        "facet_nome_assunto_cnj": "",
        "facet_nome_tribunal": "",
        "facet_tipo_processo": "",
        "facet_mes_ano_publicacao": "",
    }


def _capture(session: requests.Session, dest, pesquisa: str, pagina: int, filename: str) -> None:
    data = {
        "action": "consultas_solr_ajax",
        "metodo": "buscar_resultados",
        "parametros": urlencode(_inner_params(pesquisa, pagina), doseq=True),
    }
    response = session.post(BASE_URL, data=data, timeout=30)
    response.raise_for_status()
    dump(dest / filename, response.content)
    print(f"[tjrs] wrote {filename}")


def main() -> None:
    """Capture cjsg JSON samples for TJRS."""
    dest = samples_dir_for("tjrs", "cjsg")
    session = requests.Session()

    _capture(session, dest, "dano moral", 1, "results_normal_page_01.json")
    _capture(session, dest, "dano moral", 2, "results_normal_page_02.json")
    _capture(session, dest, "mandado de seguranca", 1, "single_page.json")
    _capture(session, dest, "juscraper_probe_zero_hits_xyzqwe", 1, "no_results.json")


if __name__ == "__main__":
    main()
