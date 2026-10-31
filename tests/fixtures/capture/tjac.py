"""Capture cjsg and acórdão samples for TJAC.

Run from repo root::

    python -m tests.fixtures.capture.tjac
"""
from ._util import capture_acordao_samples, capture_cjsg_samples

# Processo com dois acórdãos: apelação (julgada em 13/04/2026) e embargos
# (27/10/2026), este tipado como "Embargos de Declaração" na pasta. Com
# 22/04/2026 a busca passa pelas certidões que pedem senha antes dos embargos.
ACORDAO_CASOS = [
    ("dois_acordaos", "0700021-98.2018.8.01.0001", "13/04/2026"),
    ("dois_acordaos", "0700021-98.2018.8.01.0001", "22/04/2026"),
    ("sem_informacoes", "0700000-00.2026.8.01.0001", "01/01/2026"),
]


def main() -> None:
    """Capture cjsg and acórdão samples for TJAC."""
    capture_cjsg_samples(
        tribunal="tjac",
        base_url="https://esaj.tjac.jus.br/",
    )
    capture_acordao_samples("tjac", ACORDAO_CASOS)


if __name__ == "__main__":
    main()
