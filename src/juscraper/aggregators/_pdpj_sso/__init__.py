"""Autenticacao no SSO do PJe compartilhada por JusBR e PDPJ.

Pacote interno — o prefixo ``_`` indica que nada aqui e API publica. Os dois
agregadores consomem o mesmo JWT (``client_id=portalexterno-frontend``), entao
login pelo gov.br, cache local e renovacao pelo refresh token vivem aqui e
entram nos scrapers por :class:`PdpjSsoMixin`.
"""
from .credencial import CredencialPdpj
from .mixin import PdpjSsoMixin

__all__ = ["CredencialPdpj", "PdpjSsoMixin"]
