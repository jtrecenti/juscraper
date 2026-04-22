"""Shared pydantic schemas for juscraper public APIs (refs #93)."""
from .cjsg import OutputCJSGBase, SearchBase
from .consulta import CnjInputBase, OutputCnjConsultaBase
from .mixins import DataJulgamentoMixin, DataPublicacaoMixin

__all__ = [
    "SearchBase",
    "OutputCJSGBase",
    "DataJulgamentoMixin",
    "DataPublicacaoMixin",
    "CnjInputBase",
    "OutputCnjConsultaBase",
]
