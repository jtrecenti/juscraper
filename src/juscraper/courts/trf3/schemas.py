"""Schemas pydantic do ``cpopg`` e do ``cposg`` do TRF3.

Os dois endpoints usam a mesma API JSON (1º e 2º grau em hosts diferentes) e
entregam as mesmas colunas, então os campos vêm dos mixins de
:mod:`juscraper.courts._pje_api.schemas`, que o TRF1 também usa.
"""
from __future__ import annotations

from pydantic import ConfigDict

from ...schemas import CnjInputBase, OutputCnjConsultaBase
from .._pje_api.schemas import CamposProcessoPJe, DownloadPecasMixin


class InputCpopgTRF3(CnjInputBase, DownloadPecasMixin):
    """Entrada aceita por :meth:`TRF3Scraper.cpopg`.

    Herda ``id_cnj``; ``download_pecas`` + ``diretorio`` pedem o PDF de cada
    documento listado no processo.
    """


class InputCposgTRF3(CnjInputBase, DownloadPecasMixin):
    """Entrada aceita por :meth:`TRF3Scraper.cposg`. Mesmos campos do ``cpopg``."""


class OutputCpopgTRF3(OutputCnjConsultaBase, CamposProcessoPJe):
    """Uma linha do DataFrame de :meth:`TRF3Scraper.cpopg`.

    CNJ não encontrado ou cuja consulta falhou gera linha só com ``id_cnj``
    e ``motivo_falha`` (fora deste contrato).
    """

    model_config = ConfigDict(extra="allow")


class OutputCposgTRF3(OutputCnjConsultaBase, CamposProcessoPJe):
    """Uma linha do DataFrame de :meth:`TRF3Scraper.cposg`.

    No 2º grau, ``orgao_julgador_colegiado`` traz a turma e ``orgao_julgador``
    o gabinete do relator. CNJ não encontrado ou cuja consulta falhou gera
    linha só com ``id_cnj`` e ``motivo_falha`` (fora deste contrato).
    """

    model_config = ConfigDict(extra="allow")
