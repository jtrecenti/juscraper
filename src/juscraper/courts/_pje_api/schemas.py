"""Campos compartilhados pelos schemas da consulta pública do PJe (API ``/v1``).

TRF1 e TRF3 montam seus modelos ``Input*``/``Output*`` com estes mixins, porque
recebem as mesmas opções e entregam as mesmas colunas.
"""
from __future__ import annotations

from pydantic import BaseModel


class DownloadPecasMixin(BaseModel):
    """Opções de download das peças, aceitas por ``cpopg`` e ``cposg``."""

    download_pecas: bool = False
    diretorio: str | None = None


class CamposProcessoPJe(BaseModel):
    """Colunas produzidas por :func:`juscraper.courts._pje_api.parse.parse_processo`.

    ``polo_ativo``, ``polo_passivo`` e ``outros_interessados`` são listas de
    ``{participante, nome, tipo, situacao, principal, procuradoria,
    segredo_justica}``; ``movimentacoes``, de ``{data, descricao, documento}``;
    ``documentos``, de ``{id, data, descricao, binario}``. ``pecas`` e
    ``pecas_falhas`` só existem com ``download_pecas=True``: os caminhos dos
    PDFs gravados e ``[{"id", "motivo_falha"}]`` das peças que faltam. Recurso
    que a API não entregou (erro HTTP depois das tentativas) sai ``None``.
    ``motivo_falha`` é ``None`` no processo lido, salvo o bloqueado durante as
    peças (``bloqueio_anti_bot``); a linha de CNJ que falhou ou que a consulta
    não devolveu fica fora deste contrato.
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
    pecas_falhas: list[dict] | None = None
    motivo_falha: str | None = None
