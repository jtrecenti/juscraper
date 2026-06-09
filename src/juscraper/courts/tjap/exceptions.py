"""Exceções específicas do raspador TJAP (Tucujuris).

O backend Tucujuris devolve HTTP-200 mesmo quando a consulta falha: o corpo é um
envelope ``{"status": "ERRO", "mensagem": ..., "detalhe": ...}`` sem a chave
``dados``. Para não engolir isso como "0 resultados", o ``download.py`` inspeciona
o envelope e levanta uma destas exceções — subclasses de
``core.exceptions.HTTPSemanticError`` (a base abstrata para "HTTP-200 com página
de erro disfarçada").
"""
from __future__ import annotations

from juscraper.core.exceptions import HTTPSemanticError


class TJAPApiError(HTTPSemanticError):
    """Envelope de erro do Tucujuris (``status == "ERRO"``) numa resposta HTTP-200.

    Carrega a ``mensagem`` e o ``detalhe`` brutos do backend para o usuário
    entender o que aconteceu, em vez de receber um DataFrame vazio silencioso.
    """

    def __init__(self, mensagem: str, detalhe: str | None = None):
        self.mensagem = mensagem
        self.detalhe = detalhe
        msg = f"TJAP (Tucujuris) devolveu erro: {mensagem!r}."
        if detalhe:
            msg += f" Detalhe: {detalhe!r}"
        super().__init__(msg)


class TJAPSecurityCheckError(TJAPApiError):
    """Falha na verificação de segurança do TJAP (Cloudflare Turnstile).

    Desde ~2026 a busca de jurisprudência do TJAP passou a exigir um token de
    Cloudflare Turnstile (CAPTCHA), gerado no front-end e validado server-side.
    O raspador (HTTP puro, sem browser) não tem como produzir esse token, então
    o backend responde ``"A verificação de segurança falhou"``. Não há solução
    pela API HTTP pública. Ver issue #279.
    """

    def __init__(self, mensagem: str, detalhe: str | None = None):
        super().__init__(mensagem, detalhe)
        self.args = (
            f"TJAP (Tucujuris) bloqueou a consulta de jurisprudência: {mensagem!r}. "
            "O tribunal passou a exigir um CAPTCHA Cloudflare Turnstile na busca, "
            "validado server-side. O raspador (HTTP puro, sem browser) não consegue "
            "produzir esse token, então a coleta de cjsg do TJAP não funciona pela "
            "API pública. Ver issue #279.",
        )
