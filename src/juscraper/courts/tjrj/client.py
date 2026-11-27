"""Scraper for the Court of Justice of Rio de Janeiro (TJRJ)."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, ClassVar, Literal

import pandas as pd
import requests

from juscraper.core.http import HTTPScraper, RequestPolicy
from juscraper.utils.params import apply_input_pipeline_search

from .download import cjsg_download as _cjsg_download
from .parse import cjsg_parse as _cjsg_parse
from .schemas import Competencia, InputCJSGTJRJ, Origem

# Mais os mesmos codigos em ``int``, que o schema converte para ``str``.
CompetenciaAceita = Competencia | Literal[1, 2, 3]
OrigemAceita = Origem | Literal[1, 2, 3, 4, 5]

logger = logging.getLogger("juscraper.tjrj")


class TJRJScraper(HTTPScraper):
    """Scraper for the Court of Justice of Rio de Janeiro.

    The TJRJ search form displays a reCAPTCHA widget, but the backend does
    not validate it — the entire flow works without solving anything.
    """

    BASE_URL = "https://www3.tjrj.jus.br/ejuris/ConsultarJurisprudencia.aspx"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
    )

    perfis_http: ClassVar[Mapping[str, RequestPolicy]] = {
        "formulario": RequestPolicy(timeout=30),
        "cjsg": RequestPolicy(timeout=60),
    }

    def __init__(self, sleep_time: float = 1.0, *, politica: Mapping[str, Mapping[str, Any]] | None = None):
        super().__init__("TJRJ", sleep_time=sleep_time, politica=politica)

    def _configure_session(self, session: requests.Session) -> None:
        session.headers["User-Agent"] = self.USER_AGENT

    def cjsg_download(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        ano_inicio: str | int | None = None,
        ano_fim: str | int | None = None,
        competencia: CompetenciaAceita | None = None,
        origem: OrigemAceita = "1",
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
            request_fn=self._request_with_retry,
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
            pesquisa: Termo de busca livre.
            paginas: Paginas 1-based; ``None``
                baixa todas. Default ``None``.
            **kwargs: Filtros aceitos pelo schema :class:`InputCJSGTJRJ`
                (todos opcionais; ``None`` = sem filtro):

                * ``ano_inicio`` / ``ano_fim`` (str | int | None): Ano de
                  julgamento. **Granularidade anual e o unico filtro de
                  data exposto pelo backend ASPX** — use estes em vez de
                  ``data_julgamento_*``. ``None`` usa o ano mais recente
                  que o form da origem oferece: o corrente, ou 1998 nos
                  Tribunais de Alcada, que vao de 1975 a 1998. So
                  ``ano_fim`` informado: ``ano_inicio`` vira o ano mais
                  antigo da origem (1975). ``ano_inicio`` posterior a
                  ``ano_fim`` levanta ``ValidationError``. Backend:
                  ``cmbAnoInicio`` / ``cmbAnoFim``.
                * ``competencia`` (CompetenciaAceita | None): ``"1"`` civel / ``"2"``
                  criminal / ``"3"`` fazendaria (so na Turma Recursal).
                  ``None`` (default) usa a primeira competencia do form da
                  origem: ``"1"`` na 2a instancia, no Alcada Civel e na
                  Turma Recursal, ``"2"`` no Alcada Criminal. O Conselho da
                  Magistratura nao tem competencia: deixe ``None``.
                  Backend: ``cmbCompetencia``.
                * ``origem`` (OrigemAceita): ``"1"`` 2a instancia (default) /
                  ``"2"`` Tribunal de Alcada Civel / ``"3"`` Tribunal de
                  Alcada Criminal / ``"4"`` Turma Recursal / ``"5"``
                  Conselho da Magistratura. Backend: ``cmbOrigem``.
                * ``tipo_acordao`` (bool): Inclui acordaos. Default
                  ``True``. Backend: ``chkAcordao``.
                * ``tipo_monocratica`` (bool): Inclui decisoes
                  monocraticas. Default ``True``. Backend: ``chkDecMon``.
                * ``magistrado_codigo`` (str | None): IDs internos do
                  magistrado, separados por virgula. Backend:
                  ``hfCodMags``.
                * ``orgao_codigo`` (str | None): IDs internos do orgao
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
            ValidationError: Quando um filtro tem formato invalido ou
                ``ano_inicio`` e posterior a ``ano_fim``, que o portal
                responderia sem resultados.
            ValueError: Quando ``ano_inicio``, ``ano_fim`` ou ``competencia``
                nao e opcao do form da ``origem`` pedida (ex.: ``ano_inicio=2020``
                com ``origem="2"``, ou ``competencia="1"`` com ``origem="5"``),
                que o portal responderia com HTTP 500.

        Returns:
            DataFrame com colunas ``processo``, ``classe``,
                ``orgao_julgador``, ``relator``, ``data_julgamento``,
                ``data_publicacao``, ``ementa``, alem de ``cod_documento``,
                ``numero_antigo`` e ``tipo_documento``.

        Examples: Exemplo
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
