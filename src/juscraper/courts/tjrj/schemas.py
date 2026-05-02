"""Pydantic schemas for TJRJ scraper endpoints.

Ainda nao wired em :mod:`juscraper.courts.tjrj.client` — este arquivo e
documentacao executavel da API publica ate o TJRJ ser refatorado para o
pipeline canonico da #93. A lista de campos bate byte-a-byte com a
assinatura publica de :meth:`TJRJScraper.cjsg` / :meth:`TJRJScraper.cjsg_download`.
"""
from __future__ import annotations

from ...schemas import OutputCJSGBase, OutputDataPublicacaoMixin, OutputRelatoriaMixin, SearchBase


class InputCJSGTJRJ(SearchBase):
    """Accepted input for TJRJ ``cjsg`` / ``cjsg_download``.

    Endpoint ASPX (ejuris). ``pesquisa`` aceita os aliases deprecados
    ``query`` / ``termo`` via :func:`juscraper.utils.params.normalize_pesquisa`,
    que roda *antes* deste modelo. O TJRJ so expoe filtro por ano
    (``ano_inicio``/``ano_fim``); ``data_julgamento_*`` e
    ``data_publicacao_*`` sao emitidos com ``warn_unsupported`` no client
    atual (excluidos deste schema).
    """

    ano_inicio: str | int | None = None
    ano_fim: str | int | None = None
    # TODO: apertar com Literal[...] após captura do form ASPX/ejuris — refs follow-up de #184.
    competencia: str = "1"
    # TODO: apertar com Literal[...] após captura do form ASPX/ejuris — refs follow-up de #184.
    origem: str = "1"
    tipo_acordao: bool = True
    tipo_monocratica: bool = True
    magistrado_codigo: str | None = None
    orgao_codigo: str | None = None


class OutputCJSGTJRJ(OutputCJSGBase, OutputRelatoriaMixin, OutputDataPublicacaoMixin):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJRJScraper.cjsg`.

    Reflete ``tjrj.parse.cjsg_parse`` — backend ASPX (ejuris) com datas no
    formato ``/Date(millis)/`` ja convertidas.
    """

    cod_documento: str | int | None = None
    numero_antigo: str | None = None
    classe: str | None = None
    tipo_documento: str | None = None
