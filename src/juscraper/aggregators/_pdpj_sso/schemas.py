"""Schema pydantic compartilhado pelo ``auth_govbr`` de JusBR e PDPJ."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class InputAuthGovbrBase(BaseModel):
    """Campos do ``auth_govbr`` que :class:`~juscraper.aggregators._pdpj_sso.mixin.PdpjSsoMixin` le.

    Tipo de ``PdpjSsoMixin.INPUT_AUTH_GOVBR``: o schema de cada agregador
    herda daqui. ``timeout`` limita a espera pelo login no gov.br; ``salvar``
    controla a gravacao da credencial no cache local compartilhado por JusBR
    e PDPJ; ``navegador`` aponta o executavel do Chrome, Chromium ou Edge.
    """

    timeout: float = Field(default=300.0, gt=0)
    salvar: bool = True
    navegador: str | None = None

    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True,
    )
