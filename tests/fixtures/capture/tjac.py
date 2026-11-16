"""Capture cjsg and acórdão samples for TJAC.

Run from repo root::

    python -m tests.fixtures.capture.tjac
"""
import juscraper as jus

from ._util import capture_acordao_samples, capture_cjsg_samples, dump, samples_dir_for

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
        monocratica_query="usucapiao rural familia",
    )
    capture_acordao_samples("tjac", ACORDAO_CASOS)
    capture_getarquivo_recaptcha()


def capture_getarquivo_recaptcha() -> None:
    """Capture the reCAPTCHA page ``cjsg/getArquivo.do`` serves in TJAC.

    TJMS and TJCE serve the PDF on this route (``EsajAcordaoCjsgScraper``); the
    TJMS contract uses this page as an answer that is not a PDF.
    """
    scraper = jus.scraper("tjac")
    resposta = scraper.session.get(
        f"{scraper.BASE_URL}cjsg/getArquivo.do", params={"cdAcordao": "1978313", "cdForo": "0"}, timeout=60
    )
    dump(samples_dir_for("tjac", "acordao") / "getarquivo_recaptcha.html", resposta.content)


if __name__ == "__main__":
    main()
