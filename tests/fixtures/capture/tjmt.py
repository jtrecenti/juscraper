"""Capture cjsg samples for TJMT.

Run from repo root::

    python -m tests.fixtures.capture.tjmt
"""
import requests

from juscraper.courts.tjmt.download import CONFIG_URL, _build_params

from ._util import dump, samples_dir_for


def _capture_config(session: requests.Session, dest) -> dict:
    response = session.get(CONFIG_URL, timeout=30)
    response.raise_for_status()
    dump(dest / "config.json", response.content)
    print("[tjmt] wrote config.json")
    cfg = response.json()
    return {
        "api_url": cfg["api_url"],
        "token": cfg["api_hellsgate_token"],
    }


def _capture(
    session: requests.Session,
    dest,
    api_url: str,
    pesquisa: str,
    pagina: int,
    filename: str,
    *,
    tipo_consulta: str = "Acordao",
    quantidade: int = 10,
    data_julgamento_inicio: str | None = None,
    data_julgamento_fim: str | None = None,
    relator: str | None = None,
    orgao_julgador: str | None = None,
    tipo_processo: str | None = None,
    thesaurus: bool = False,
) -> None:
    params = _build_params(
        pesquisa=pesquisa,
        pagina=pagina,
        quantidade=quantidade,
        tipo_consulta=tipo_consulta,
        data_julgamento_inicio=data_julgamento_inicio,
        data_julgamento_fim=data_julgamento_fim,
        relator=relator,
        orgao_julgador=orgao_julgador,
        classe=None,
        tipo_processo=tipo_processo,
        thesaurus=thesaurus,
    )
    response = session.get(f"{api_url}/api/Consulta", params=params, timeout=60)
    response.raise_for_status()
    dump(dest / filename, response.content)
    print(f"[tjmt] wrote {filename}")


def main() -> None:
    """Capture cjsg JSON samples for TJMT."""
    dest = samples_dir_for("tjmt", "cjsg")
    session = requests.Session()
    session.headers.update({"User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)"})
    cfg = _capture_config(session, dest)
    session.headers.update({
        "Token": cfg["token"],
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://jurisprudencia.tjmt.jus.br/",
    })

    _capture(session, dest, cfg["api_url"], "dano moral", 1, "results_normal_page_01.json")
    _capture(session, dest, cfg["api_url"], "dano moral", 2, "results_normal_page_02.json")
    _capture(session, dest, cfg["api_url"], "mandado de seguranca", 1, "single_page.json")
    _capture(session, dest, cfg["api_url"], "juscraper_probe_zero_hits_xyzqwe", 1, "no_results.json")
    _capture(
        session,
        dest,
        cfg["api_url"],
        "dano moral",
        1,
        "filters_all.json",
        tipo_consulta="Acordao",
        quantidade=5,
        data_julgamento_inicio="01/01/2024",
        data_julgamento_fim="31/03/2024",
        relator="306",
        orgao_julgador="30",
        tipo_processo="942",
        thesaurus=True,
    )


if __name__ == "__main__":
    main()
