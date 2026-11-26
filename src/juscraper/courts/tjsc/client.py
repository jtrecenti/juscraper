"""Scraper for the Tribunal de Justica de Santa Catarina (TJSC)."""
from collections.abc import Mapping
from typing import Any, ClassVar

import pandas as pd

from juscraper.core.http import HTTPScraper, RequestPolicy
from juscraper.utils.deprecacao import resolve_buscar_em
from juscraper.utils.params import apply_input_pipeline_search

from .download import PERFIL_CJSG, cjsg_download_manager
from .parse import cjsg_parse_manager
from .schemas import InputCJSGTJSC


class TJSCScraper(HTTPScraper):
    """Scraper for the Tribunal de Justica de Santa Catarina (TJSC).

    Uses the eproc jurisprudence search at eprocwebcon.tjsc.jus.br.
    """

    BASE_URL = "https://eprocwebcon.tjsc.jus.br"

    #: O portal derruba às vezes a conexão keep-alive reaproveitada.
    perfis_http: ClassVar[Mapping[str, RequestPolicy]] = {
        PERFIL_CJSG: RequestPolicy(timeout=60, retry_on_connection_error=True),
    }

    def __init__(
        self,
        verbose: int = 0,
        download_path: str | None = None,
        sleep_time: float = 1.0,
        **kwargs: Any,
    ):
        super().__init__(
            "TJSC",
            verbose=verbose,
            download_path=download_path,
            sleep_time=sleep_time,
            **kwargs,
        )

    def cpopg(self, id_cnj: str | list[str]):
        """Stub: first instance case consultation not implemented for TJSC."""
        raise NotImplementedError("Consulta de processos de 1o grau nao implementada para TJSC.")

    def cposg(self, id_cnj: str | list[str]):
        """Stub: second instance case consultation not implemented for TJSC."""
        raise NotImplementedError("Consulta de processos de 2o grau nao implementada para TJSC.")

    def cjsg(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        buscar_em: str | None = None,
        processo: str | None = None,
        **kwargs,
    ) -> pd.DataFrame:
        """Busca jurisprudencia no TJSC.

        Args:
            pesquisa (str): Termo de busca livre, procurado no campo indicado
                por ``buscar_em``.
            paginas (int | list | range | None): Paginas 1-based; ``None`` baixa
                todas. Default ``None``.
            buscar_em (str | None): Onde procurar ``pesquisa``: ``"ementa"``
                (default; ``None`` tambem) ou ``"inteiro_teor"`` (texto
                integral da decisao, que inclui a ementa). Outro valor levanta
                ``ValidationError``.
            processo (str): Filtro por numero do processo.
            **kwargs: Filtros aceitos pelo schema :class:`InputCJSGTJSC`.
                Listados abaixo (todos opcionais; ``None`` = sem filtro):

                * ``data_julgamento_inicio`` / ``data_julgamento_fim``
                  (str | date | None): ``DD/MM/AAAA``, ``DD-MM-AAAA``,
                  ``AAAA-MM-DD``, ``AAAA/MM/DD``, ``date`` ou ``datetime``.
                  Mapeado para ``dt_decisao_*`` no backend, que recebe
                  ``DD/MM/YYYY``.
                * ``data_publicacao_inicio`` / ``data_publicacao_fim``
                  (str | date | None): nos mesmos formatos.

        Aliases deprecados (popados com ``DeprecationWarning`` antes do pydantic):
            * ``query`` / ``termo`` -> ``pesquisa``
            * ``data_inicio`` / ``data_fim`` -> ``data_julgamento_inicio`` / ``_fim``
            * ``data_julgamento_de`` / ``_ate`` -> ``data_julgamento_inicio`` / ``_fim``
            * ``data_publicacao_de`` / ``_ate`` -> ``data_publicacao_inicio`` / ``_fim``
            * ``campo`` -> ``buscar_em``: ``campo="E"`` vira
              ``buscar_em="ementa"`` e ``campo="I"``, ``buscar_em="inteiro_teor"``

        Raises:
            TypeError: Quando um kwarg desconhecido e passado.
            ValidationError: Quando um filtro tem formato invalido.
            ValueError: Quando ``campo`` e ``buscar_em`` sao passados juntos.
            RuntimeError: Quando o portal redireciona a busca (mudanca de endereco).
            requests.ConnectionError: Quando o portal derruba a conexao em
                todas as tentativas do perfil HTTP ``"cjsg"`` (ajustavel com
                ``politica={"cjsg": {...}}`` no construtor).

        Avisos:
            ``UserWarning``: Quando algum registro sai sem numero de processo
                (nem link nem texto ``<numero>/TJSC``); a coluna ``processo``
                fica vazia nessas linhas.

        Returns:
            DataFrame com as decisoes.

        See also:
            :class:`InputCJSGTJSC` — schema pydantic e a fonte da verdade dos
            filtros aceitos.
        """
        return self.cjsg_parse(self.cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            buscar_em=buscar_em,
            processo=processo,
            **kwargs,
        ))

    def cjsg_download(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        buscar_em: str | None = None,
        processo: str | None = None,
        **kwargs,
    ) -> list:
        """Download raw HTML pages from TJSC.

        Aceita os mesmos filtros de :meth:`cjsg`; veja la a lista completa.

        Returns
        -------
        list
            List of raw HTML strings (one per page).
        """
        resolve_buscar_em(kwargs, "campo", buscar_em, {"E": "ementa", "I": "inteiro_teor"})
        inp = apply_input_pipeline_search(
            InputCJSGTJSC,
            "TJSCScraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            processo=processo,
        )
        return cjsg_download_manager(
            pesquisa=inp.pesquisa,
            paginas=inp.paginas,
            request_fn=self._request_with_retry,
            sleep_time=self.sleep_time,
            buscar_em=inp.buscar_em,
            processo=inp.processo or "",
            dt_decisao_inicio=inp.data_julgamento_inicio or "",
            dt_decisao_fim=inp.data_julgamento_fim or "",
            dt_publicacao_inicio=inp.data_publicacao_inicio or "",
            dt_publicacao_fim=inp.data_publicacao_fim or "",
        )

    def cjsg_parse(self, resultados_brutos: list) -> pd.DataFrame:
        """Parse downloaded HTML pages.

        Returns
        -------
        pd.DataFrame
        """
        return cjsg_parse_manager(resultados_brutos)
