"""Capture cjsg samples for TJDFT.

Run from repo root::

    python -m tests.fixtures.capture.tjdft
"""
from pathlib import Path

import requests

from juscraper.courts.tjdft.download import BASE_URL, build_cjsg_payload

from ._util import dump, samples_dir_for

# Em 26/11/2026, "direito penal" publicado neste dia trazia 8 acórdãos e 2
# decisões monocráticas na página 1.
DATA_PUBLICACAO_COM_MONOCRATICAS = {"campo": "dataPublicacao", "valor": "entre 2026-11-20 e 2026-11-20"}


def _capture(
    session: requests.Session,
    destino: Path,
    pesquisa: str,
    pagina: int,
    termos_acessorios: list | None = None,
) -> None:
    # ``pagina`` é 1-based, como em ``cjsg``; a API conta a partir de 0.
    payload = build_cjsg_payload(pesquisa, pagina - 1, termos_acessorios=termos_acessorios)
    response = session.post(BASE_URL, json=payload, timeout=30)
    response.raise_for_status()
    dump(destino, response.content)
    print(f"[tjdft] wrote {destino.name}")


def main() -> None:
    """Capture cjsg JSON samples for TJDFT."""
    dest = samples_dir_for("tjdft", "cjsg")
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})

    _capture(session, dest / "results_normal_page_01.json", "dano moral", 1)
    _capture(session, dest / "results_normal_page_02.json", "dano moral", 2)
    _capture(session, dest / "single_page.json", "mandado de seguranca", 1)
    _capture(session, dest / "no_results.json", "juscraper_probe_zero_hits_xyzqwe", 1)
    # Busca com 13 acórdãos (2 páginas) para o ``paginas=None``.
    _capture(session, dest / "todas_paginas_page_01.json", "enfiteuse", 1)
    _capture(session, dest / "todas_paginas_page_02.json", "enfiteuse", 2)
    # Página com acórdãos e decisões monocráticas: as monocráticas
    # (``base="decisoes"``) não trazem ``dataJulgamento``.
    _capture(
        session,
        dest / "com_decisoes_monocraticas.json",
        "direito penal",
        1,
        termos_acessorios=[DATA_PUBLICACAO_COM_MONOCRATICAS],
    )


if __name__ == "__main__":
    main()
