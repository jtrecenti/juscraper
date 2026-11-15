"""Scraper for the Tribunal Regional Federal da 5ª Região (TRF5).

Wraps the PJe public-consultation system at
``pje1g.trf5.jus.br/pjeconsulta/``. The TRF5 form ships with reCAPTCHA
markup, but the ``executarReCaptcha()`` JS function short-circuits with
``if (false)`` — the captcha is never enforced, so direct ``requests`` work.
Desde novembro de 2026 o formulário usa o autocomplete ``classeJudicial`` e o
bloco ``dataAutuacaoDecoration``, o padrão da família; o popup
``classeProcessualProcessoHidden`` saiu. Só :data:`BASE_URL` diverge.
"""
from __future__ import annotations

from .._trf.base import TRFConsultaScraper


class TRF5Scraper(TRFConsultaScraper):
    """TRF5 PJe consulta pública (1º grau)."""

    BASE_URL = "https://pje1g.trf5.jus.br/pjeconsulta/"
    TRIBUNAL_NAME = "TRF5"
