"""Schemas pydantic do ``cpopg`` e do ``cposg`` do TRF3.

Os dois endpoints usam a mesma API JSON (1º e 2º grau em hosts diferentes) e
entregam as mesmas colunas, então os campos ficam em mixins compartilhados e
os modelos de cada endpoint são irmãos.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ...schemas import CnjInputBase, OutputCnjConsultaBase


class _DownloadPecasMixin(BaseModel):
    """Opções de download das peças, aceitas por ``cpopg`` e ``cposg``."""

    download_pecas: bool = False
    diretorio: str | None = None


class InputCpopgTRF3(CnjInputBase, _DownloadPecasMixin):
    """Entrada aceita por :meth:`TRF3Scraper.cpopg`.

    Herda ``id_cnj``; ``download_pecas`` + ``diretorio`` pedem o PDF de cada
    documento listado no processo.
    """


class InputCposgTRF3(CnjInputBase, _DownloadPecasMixin):
    """Entrada aceita por :meth:`TRF3Scraper.cposg`. Mesmos campos do ``cpopg``."""


class _CamposProcessoTRF3(BaseModel):
    """Colunas produzidas por :func:`juscraper.courts.trf3.parse.parse_processo`.

    ``polo_ativo``, ``polo_passivo`` e ``outros_interessados`` são listas de
    ``{participante, nome, tipo, situacao, principal, procuradoria,
    segredo_justica}``; ``movimentacoes``, de ``{data, descricao, documento}``;
    ``documentos``, de ``{id, data, descricao, binario}``. ``pecas`` só existe
    com ``download_pecas=True`` e traz os caminhos dos PDFs gravados. Recurso
    que a API não entregou (erro HTTP depois das tentativas) sai ``None``.
    """

    processo: str
    classe: str | None = None
    assunto: str | None = None
    data_distribuicao: str | None = None
    orgao_julgador: str | None = None
    orgao_julgador_colegiado: str | None = None
    jurisdicao: str | None = None
    endereco_orgao: str | None = None
    polo_ativo: list[dict] | None = None
    polo_passivo: list[dict] | None = None
    outros_interessados: list[dict] | None = None
    movimentacoes: list[dict] | None = None
    documentos: list[dict] | None = None
    pecas: list[str] | None = None


class OutputCpopgTRF3(OutputCnjConsultaBase, _CamposProcessoTRF3):
    """Uma linha do DataFrame de :meth:`TRF3Scraper.cpopg`.

    CNJ não encontrado gera linha só com ``id_cnj`` (fora deste contrato).
    """

    model_config = ConfigDict(extra="allow")


class OutputCposgTRF3(OutputCnjConsultaBase, _CamposProcessoTRF3):
    """Uma linha do DataFrame de :meth:`TRF3Scraper.cposg`.

    No 2º grau, ``orgao_julgador_colegiado`` traz a turma e ``orgao_julgador``
    o gabinete do relator. CNJ não encontrado gera linha só com ``id_cnj``
    (fora deste contrato).
    """

    model_config = ConfigDict(extra="allow")
