"""Scraper for the Tribunal Regional Federal da 5ª Região (TRF5).

Wraps the PJe public-consultation system at
``pje1g.trf5.jus.br/pjeconsulta/``. The TRF5 form ships with reCAPTCHA
markup, but the ``executarReCaptcha()`` JS function short-circuits with
``if (false)`` — the captcha is never enforced, so direct ``requests`` work.
Unlike TRF1/TRF3, the classe filter is a ``classeProcessualProcessoHidden``
popup picker (a single hidden input, no ``dataAutuacaoDecoration`` block), so
TRF5 overrides ``CLASSE_FIELD_NAME`` and ``_classe_payload_fields``.
"""
from __future__ import annotations

from .._trf.base import TRFConsultaScraper
from .._trf.download import FormFieldIds


class TRF5Scraper(TRFConsultaScraper):
    """TRF5 PJe consulta pública (1º grau)."""

    BASE_URL = "https://pje1g.trf5.jus.br/pjeconsulta/"
    TRIBUNAL_NAME = "TRF5"
    CLASSE_FIELD_NAME = "classeProcessualProcessoHidden"

    def _classe_payload_fields(self, field_ids: FormFieldIds) -> dict[str, str]:
        """TRF5 ships a single popup field; no ``_selection`` pair, no date block."""
        return {f"fPP:{field_ids.classe}:classeProcessualProcessoHidden": ""}
