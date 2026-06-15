"""Pydantic schemas for the JusBR aggregator.

Ainda nao wired em :mod:`juscraper.aggregators.jusbr.client` — este
arquivo e documentacao executavel da API publica ate o agregador ser
refatorado para o pipeline canonico da #93. A lista de campos bate
byte-a-byte com as assinaturas publicas dos metodos de
:class:`JusbrScraper`.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from ...schemas import CnjInputBase


class InputAuthJusBR(BaseModel):
    """Accepted input for :meth:`JusbrScraper.auth`.

    Recebe o JWT ja obtido fora da biblioteca (por exemplo, do devtools
    do navegador logado no PJe). O client decodifica sem verificar
    assinatura so para validar o formato e detectar tokens expirados.
    """

    token: str

    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True,
    )


class InputAuthFirefoxJusBR(BaseModel):
    """Accepted input for :meth:`JusbrScraper.auth_firefox`.

    O metodo ``auth_firefox()`` nao aceita parametros — usa
    ``browser_cookie3`` para extrair os cookies da sessao do Firefox e
    completa o fluxo OAuth sozinho. Este schema existe so para manter a
    simetria com os demais endpoints (documentacao + ``extra='forbid'``).
    """

    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True,
    )


class InputCPOPGJusBR(CnjInputBase):
    """Accepted input for :meth:`JusbrScraper.cpopg`.

    Consulta processual unificada via PDPJ-CNJ. Aceita um CNJ ou uma
    lista (herdado de :class:`CnjInputBase`); os digitos sao normalizados
    por :func:`juscraper.utils.cnj.clean_cnj` antes da chamada a API.
    """


class OutputCPOPGJusBR(BaseModel):
    """Colunas observaveis em uma linha do DataFrame de
    :meth:`JusbrScraper.cpopg`.

    ``processo`` (canonico do projeto — ver CLAUDE.md > "Schemas pydantic")
    e a coluna pivot que aparece em todo row, tanto no happy path quanto
    nos fallbacks de CNJ invalido / nao encontrado / erro de detalhes. O
    JusBR retorna uma estrutura rica do PDPJ-CNJ com dezenas de campos
    por processo; a coluna pivot e suficiente como contrato minimo e o
    restante flui via ``extra='allow'`` (incluindo ``processo_pesquisado``,
    que existe historicamente em rows de fallback como sinonimo de
    ``processo``).
    """

    processo: str

    model_config = ConfigDict(extra="allow")


class InputDownloadDocumentsJusBR(BaseModel):
    """Accepted input for :meth:`JusbrScraper.download_documents`.

    ``base_df`` e tipado como ``Any`` porque pydantic nao tem validador
    nativo para ``pandas.DataFrame``; ``arbitrary_types_allowed`` no
    ``ConfigDict`` deixa passar, mas ``Any`` evita o acoplamento de um
    import de pandas so para tipagem.
    """

    base_df: Any
    max_docs_per_process: int | None = None

    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True,
    )


class OutputDownloadDocumentsJusBR(BaseModel):
    """Colunas observaveis em uma linha do DataFrame de
    :meth:`JusbrScraper.download_documents`.

    Cada linha representa um documento de um processo. ``numero_processo``
    e a coluna pivot que liga de volta ao DataFrame de processos; demais
    metadados do documento (id, tipo, data, URL) fluem via ``extra='allow'``.
    """

    numero_processo: str

    model_config = ConfigDict(extra="allow")
