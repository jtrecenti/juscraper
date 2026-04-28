"""Capture cjsg/cjpg samples for TJES.

Run from repo root::

    python -m tests.fixtures.capture.tjes
"""
import requests

from juscraper.courts.tjes.download import BASE_URL, CJPG_CORE, DEFAULT_CORE, _build_params

from ._util import dump, samples_dir_for


def _capture(session: requests.Session, dest, pesquisa: str, pagina: int, filename: str, *, core: str) -> None:
    params = _build_params(
        pesquisa=pesquisa,
        pagina=pagina,
        per_page=20,
        core=core,
        busca_exata=False,
        data_inicio=None,
        data_fim=None,
        magistrado=None,
        orgao_julgador=None,
        classe_judicial=None,
        jurisdicao=None,
        assunto=None,
        ordenacao=None,
    )
    response = session.get(f"{BASE_URL}/search", params=params, timeout=30)
    response.raise_for_status()
    dump(dest / filename, response.content)
    print(f"[tjes] wrote {dest.name}/{filename}")


def main() -> None:
    """Capture cjsg and cjpg JSON samples for TJES."""
    session = requests.Session()
    session.headers.update({"User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)"})

    cjsg_dest = samples_dir_for("tjes", "cjsg")
    _capture(session, cjsg_dest, "dano moral", 1, "results_normal_page_01.json", core=DEFAULT_CORE)
    _capture(session, cjsg_dest, "dano moral", 2, "results_normal_page_02.json", core=DEFAULT_CORE)
    _capture(session, cjsg_dest, "mandado de seguranca", 1, "single_page.json", core=DEFAULT_CORE)
    _capture(session, cjsg_dest, "juscraper_probe_zero_hits_xyzqwe", 1, "no_results.json", core=DEFAULT_CORE)

    cjpg_dest = samples_dir_for("tjes", "cjpg")
    _capture(session, cjpg_dest, "obrigacao de fazer", 1, "results_normal_page_01.json", core=CJPG_CORE)
    _capture(session, cjpg_dest, "juscraper_probe_zero_hits_xyzqwe", 1, "no_results.json", core=CJPG_CORE)


if __name__ == "__main__":
    main()
