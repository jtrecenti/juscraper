"""Shared pydantic schemas for juscraper public APIs (refs #93)."""
from .cjsg import OutputCJSGBase, SearchBase
from .consulta import CnjInputBase, OutputCnjConsultaBase
from .mixins import (
    AutoChunkMixin,
    DataJulgamentoMixin,
    DataPublicacaoMixin,
    OutputDataPublicacaoMixin,
    OutputRelatoriaMixin,
    PaginasMixin,
)

__all__ = [
    "SearchBase",
    "OutputCJSGBase",
    "AutoChunkMixin",
    "PaginasMixin",
    "DataJulgamentoMixin",
    "DataPublicacaoMixin",
    "OutputRelatoriaMixin",
    "OutputDataPublicacaoMixin",
    "CnjInputBase",
    "OutputCnjConsultaBase",
]
