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
    "AutoChunkMixin",
    "CnjInputBase",
    "CountOnlyMixin",
    "DataJulgamentoMixin",
    "DataPublicacaoMixin",
    "IdFiltro",
    "IdFiltroUnico",
    "OutputCJSGBase",
    "OutputCnjConsultaBase",
    "OutputDataPublicacaoMixin",
    "OutputRelatoriaMixin",
    "PaginasMixin",
    "SearchBase",
]
