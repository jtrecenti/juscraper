"""Shared pydantic schemas for juscraper public APIs (refs #93)."""
from .cjsg import OutputCJSGBase, SearchBase
from .consulta import CnjInputBase, OutputCnjConsultaBase
from .mixins import (
    AutoChunkMixin,
    CountOnlyMixin,
    DataJulgamentoMixin,
    DataPublicacaoMixin,
    OutputDataPublicacaoMixin,
    OutputRelatoriaMixin,
    PaginasMixin,
)
from .types import IdFiltro, IdFiltroUnico

__all__ = [
    "SearchBase",
    "OutputCJSGBase",
    "AutoChunkMixin",
    "CountOnlyMixin",
    "PaginasMixin",
    "DataJulgamentoMixin",
    "DataPublicacaoMixin",
    "OutputRelatoriaMixin",
    "OutputDataPublicacaoMixin",
    "CnjInputBase",
    "OutputCnjConsultaBase",
    "IdFiltro",
    "IdFiltroUnico",
]
