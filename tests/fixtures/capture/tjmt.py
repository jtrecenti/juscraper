"""Capture cjsg samples for TJMT.

Run from repo root::

    python -m tests.fixtures.capture.tjmt
"""
from typing import cast

import requests

from juscraper.courts.tjmt.download import (
    _build_params,
    _get_api_config,
    _normalize_text_filter,
    _normalize_tipo_processo,
    _to_exclusive_end_date,
    _to_tjmt_date,
)

from ._util import dump, samples_dir_for


def _capture_config(session: requests.Session) -> dict:
    def request_fn(method: str, url: str, **kwargs):
        kwargs.pop("expect_json", None)
        response = session.request(method, url, **kwargs)
        response.raise_for_status()
        return response

    return cast("dict[str, str]", _get_api_config(request_fn))


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
    data_publicacao_inicio: str | None = None,
    data_publicacao_fim: str | None = None,
    relator: str | None = None,
    orgao_julgador: str | None = None,
    tipo_processo: str | None = None,
    thesaurus: bool = False,
) -> None:
    params = _build_params(
        pesquisa=pesquisa,
        pagina=pagina - 1,
        quantidade=quantidade,
        tipo_consulta=tipo_consulta,
        data_publicacao_inicio=_to_tjmt_date(data_publicacao_inicio),
        data_publicacao_fim=_to_exclusive_end_date(data_publicacao_fim),
        relator=_normalize_text_filter(relator, "relator"),
        orgao_julgador=_normalize_text_filter(orgao_julgador, "orgao_julgador"),
        tipo_processo=_normalize_tipo_processo(tipo_processo),
        thesaurus=thesaurus,
    )
    response = session.get(f"{api_url}/consulta", params=params, timeout=60)
    response.raise_for_status()
    dump(dest / filename, response.content)
    print(f"[tjmt] wrote {filename}")


def main() -> None:
    """Capture cjsg JSON samples for TJMT."""
    dest = samples_dir_for("tjmt", "cjsg")
    session = requests.Session()
    session.headers.update({"User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)"})
    cfg = _capture_config(session)
    session.headers.update({
        "Token": cfg["token"],
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://jurisprudencia.tjmt.jus.br/",
    })

    _capture(
        session,
        dest,
        cfg["api_url"],
        "dano moral",
        1,
        "results_normal_page_01.json",
        tipo_consulta="Acordao",
        quantidade=1,
    )
    _capture(
        session,
        dest,
        cfg["api_url"],
        "dano moral",
        1,
        "single_page.json",
        tipo_consulta="DecisaoMonocratica",
        quantidade=1,
    )
    _capture(
        session,
        dest,
        cfg["api_url"],
        "juscraper_probe_zero_hits_xyzqwe",
        1,
        "no_results.json",
        quantidade=1,
    )


if __name__ == "__main__":
    main()
