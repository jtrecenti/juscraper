"""Scraper for the Court of Justice of Rio de Janeiro (TJRJ)."""
from __future__ import annotations

import logging

import pandas as pd
import requests

from juscraper.core.base import BaseScraper
from juscraper.utils.params import apply_input_pipeline_search

from .download import cjsg_download as _cjsg_download
from .parse import cjsg_parse as _cjsg_parse
from .schemas import InputCJSGTJRJ

logger = logging.getLogger("juscraper.tjrj")


class TJRJScraper(BaseScraper):
    """Scraper for the Court of Justice of Rio de Janeiro.

    The TJRJ search form displays a reCAPTCHA widget, but the backend does
    not validate it — the entire flow works without solving anything.
    """

    BASE_URL = "https://www3.tjrj.jus.br/ejuris/ConsultarJurisprudencia.aspx"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
    )

    def __init__(self, sleep_time: float = 1.0):
        super().__init__("TJRJ")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.USER_AGENT})
        self.sleep_time = sleep_time

    def cjsg_download(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        ano_inicio: str | int | None = None,
        ano_fim: str | int | None = None,
        competencia: str | int = "1",
        origem: str | int = "1",
        tipo_acordao: bool = True,
        tipo_monocratica: bool = True,
        magistrado_codigo: str | None = None,
        orgao_codigo: str | None = None,
        **kwargs,
    ) -> list:
        """Baixa as paginas de resultado da busca de jurisprudencia do TJRJ.

        Aceita os mesmos filtros de :meth:`cjsg`; veja la a lista completa.
        Retorna a lista bruta de payloads JSON, sem parser.

        See also:
            :class:`InputCJSGTJRJ` — schema pydantic e a fonte da verdade dos
            filtros aceitos.
            :meth:`cjsg` — versao high-level que ja parseia para DataFrame.
        """
        inp = apply_input_pipeline_search(
            InputCJSGTJRJ,
            "TJRJScraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            ano_inicio=ano_inicio,
            ano_fim=ano_fim,
            competencia=competencia,
            origem=origem,
            tipo_acordao=tipo_acordao,
            tipo_monocratica=tipo_monocratica,
            magistrado_codigo=magistrado_codigo,
            orgao_codigo=orgao_codigo,
        )

        ano_inicio_s = str(inp.ano_inicio) if inp.ano_inicio is not None else None
        ano_fim_s = str(inp.ano_fim) if inp.ano_fim is not None else None
        return _cjsg_download(
            session=self.session,
            pesquisa=inp.pesquisa,
            paginas=inp.paginas,
            ano_inicio=ano_inicio_s,
            ano_fim=ano_fim_s,
            competencia=inp.competencia,
            origem=inp.origem,
            tipo_acordao=inp.tipo_acordao,
            tipo_monocratica=inp.tipo_monocratica,
            magistrado_codigo=inp.magistrado_codigo,
            orgao_codigo=inp.orgao_codigo,
            sleep_time=self.sleep_time,
        )

    def cjsg_parse(self, raw_pages: list) -> pd.DataFrame:
        """Transform raw TJRJ payloads into a DataFrame."""
        return _cjsg_parse(raw_pages)

    def cjsg(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        **kwargs,
    ) -> pd.DataFrame:
        """Busca jurisprudencia (acordaos + monocraticas) no TJRJ.

        Submete o form ASPX em ``ConsultarJurisprudencia.aspx`` e segue a
        chamada XHR para ``ProcessarConsJurisES.aspx`` que entrega os
        documentos em JSON.

        Args:
            pesquisa (str): Termo de busca livre.
            paginas (int | list | range | None): Paginas 1-based; ``None``
                baixa todas. Default ``None``.
            **kwargs: Filtros aceitos pelo schema :class:`InputCJSGTJRJ`
                (todos opcionais; ``None`` = sem filtro):

                * ``ano_inicio`` / ``ano_fim`` (str | int): Ano de
                  julgamento. **Granularidade anual e o unico filtro de
                  data exposto pelo backend ASPX** — use estes em vez de
                  ``data_julgamento_*``. Backend:
                  ``cmbAnoInicio`` / ``cmbAnoFim``.
                * ``competencia`` (str | int): ``"1"`` civel / ``"2"``
                  criminal / ``"3"`` ambos. Default ``"1"``. Backend:
                  ``cmbCompetencia``.
                * ``origem`` (str | int): ``"1"`` 2o grau (default).
                  Backend: ``cmbOrigem``.
                * ``tipo_acordao`` (bool): Inclui acordaos. Default
                  ``True``. Backend: ``chkAcordao``.
                * ``tipo_monocratica`` (bool): Inclui decisoes
                  monocraticas. Default ``True``. Backend: ``chkDecMon``.
                * ``magistrado_codigo`` (str): IDs internos do
                  magistrado, separados por virgula. Backend:
                  ``hfCodMags``.
                * ``orgao_codigo`` (str): IDs internos do orgao
                  julgador, separados por virgula. Backend:
                  ``hfCodOrgs``.

        Aliases deprecados (popados com ``DeprecationWarning`` antes do pydantic):
            * ``query`` / ``termo`` -> ``pesquisa``

        Raises:
            TypeError: Quando um kwarg desconhecido e passado, **incluindo**
                ``data_julgamento_inicio`` / ``data_julgamento_fim`` /
                ``data_publicacao_inicio`` / ``data_publicacao_fim`` — o
                backend ASPX do TJRJ nao expoe esses filtros; use
                ``ano_inicio`` / ``ano_fim`` (granularidade anual apenas).
            ValidationError: Quando um filtro tem formato invalido.

        Returns:
            pd.DataFrame: DataFrame com colunas ``processo``, ``classe``,
            ``orgao_julgador``, ``relator``, ``data_julgamento``,
            ``data_publicacao``, ``ementa``, alem de ``cod_documento``,
            ``numero_antigo`` e ``tipo_documento``.

        Exemplo:
            >>> import juscraper as jus
            >>> tjrj = jus.scraper("tjrj")
            >>> df = tjrj.cjsg("dano moral", ano_inicio=2024, ano_fim=2024,
            ...                paginas=range(1, 3))

        See also:
            :class:`InputCJSGTJRJ` — schema pydantic e a fonte da verdade dos
            filtros aceitos.
        """
        raw = self.cjsg_download(pesquisa=pesquisa, paginas=paginas, **kwargs)
        return self.cjsg_parse(raw)

    def cpopg(self, id_cnj: str | list[str]):
        """Stub: first degree case search not implemented for TJRJ."""
        raise NotImplementedError("TJRJ does not implement cpopg.")

    def cposg(self, id_cnj: str | list[str]):
        """Stub: second degree case search not implemented for TJRJ."""
        raise NotImplementedError("TJRJ does not implement cposg.")
