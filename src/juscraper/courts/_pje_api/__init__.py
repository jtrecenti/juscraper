"""Consulta pública do PJe que consome a API JSON ``/v1`` (TRF1 e TRF3).

Pacote interno: o prefixo ``_`` indica que nada aqui é API pública. O TRF3
trocou o portal JSF por esta aplicação primeiro; o TRF1 trocou em novembro de
2026. As instalações JSF que restam (TRF5 e TJPE) seguem em
:mod:`juscraper.courts._trf`.
"""
from .base import PJeAPIScraper
from .download import AplicacaoPJe

__all__ = ["AplicacaoPJe", "PJeAPIScraper"]
