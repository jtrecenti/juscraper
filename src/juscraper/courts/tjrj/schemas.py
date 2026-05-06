"""Pydantic schemas for TJRJ scraper endpoints."""
from __future__ import annotations

from pydantic import field_validator

from ...schemas import OutputCJSGBase, OutputDataPublicacaoMixin, OutputRelatoriaMixin, SearchBase


class InputCJSGTJRJ(SearchBase):
    """Accepted input for TJRJ ``cjsg`` / ``cjsg_download``.

    Endpoint ASPX (ejuris). ``pesquisa`` aceita os aliases deprecados
    ``query`` / ``termo`` via :func:`juscraper.utils.params.normalize_pesquisa`,
    que roda *antes* deste modelo. O TJRJ so expoe filtro por ano
    (``ano_inicio``/``ano_fim``); ``data_julgamento_*`` e
    ``data_publicacao_*`` nao sao aceitos — o backend ASPX nao expoe esses
    filtros, e este schema rejeita via ``extra="forbid"``.
    """

    ano_inicio: str | int | None = None
    ano_fim: str | int | None = None
    # TODO (#212): apertar com Literal[...] após captura do form ASPX/ejuris — vale para `competencia` e `origem`.
    competencia: str = "1"
    origem: str = "1"
    tipo_acordao: bool = True
    tipo_monocratica: bool = True
    magistrado_codigo: str | None = None
    orgao_codigo: str | None = None

    @field_validator("competencia", "origem", mode="before")
    @classmethod
    def _coerce_int(cls, value):
        # O backend ASPX espera string no body, mas o usuario tipicamente
        # pensa em valores discretos pequenos (1/2/3) — aceitar ``int`` evita
        # surpresa do tipo `competencia=2 -> ValidationError`. Coerce so para
        # int "puro"; bool nao entra (Python trata bool como subtipo de int).
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return str(value)
        return value


class OutputCJSGTJRJ(OutputCJSGBase, OutputRelatoriaMixin, OutputDataPublicacaoMixin):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJRJScraper.cjsg`.

    Reflete ``tjrj.parse.cjsg_parse`` — backend ASPX (ejuris) com datas no
    formato ``/Date(millis)/`` ja convertidas.
    """

    cod_documento: str | int | None = None
    numero_antigo: str | None = None
    classe: str | None = None
    tipo_documento: str | None = None
