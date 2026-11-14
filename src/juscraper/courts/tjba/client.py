"""
Scraper for the Tribunal de Justica do Estado da Bahia (TJBA).
"""

import pandas as pd

from juscraper.core.http import HTTPScraper
from juscraper.utils.params import apply_input_pipeline_search, pop_deprecated_alias, resolve_deprecated_alias

from .download import cjsg_download
from .parse import cjsg_parse
from .schemas import InputCJSGTJBA


class TJBAScraper(HTTPScraper):
    """Scraper for the Tribunal de Justica do Estado da Bahia."""

    BASE_URL = "https://jurisprudenciaws.tjba.jus.br/graphql"

    def __init__(self):
        super().__init__("TJBA")

    def cpopg(self, id_cnj: str | list[str]):
        """Stub: first-instance case consultation not implemented for TJBA."""
        raise NotImplementedError("Consulta de processos de 1 grau nao implementada para TJBA.")

    def cposg(self, id_cnj: str | list[str]):
        """Stub: second-instance case consultation not implemented for TJBA."""
        raise NotImplementedError("Consulta de processos de 2 grau nao implementada para TJBA.")

    def cjsg_download(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        numero_recurso: str | None = None,
        orgaos: list | None = None,
        relatores: list | None = None,
        classe: list | None = None,
        data_publicacao_inicio: str | None = None,
        data_publicacao_fim: str | None = None,
        segundo_grau: bool = True,
        turmas_recursais: bool = True,
        tipo_acordaos: bool = True,
        tipo_decisoes_monocraticas: bool = True,
        ordenado_por: str = "dataPublicacao",
        tamanho_pagina: int = 10,
        **kwargs,
    ) -> list:
        """
        Download raw results from the TJBA jurisprudence search.

        Parameters
        ----------
        pesquisa : str
            Search term. ``query`` and ``termo`` are accepted as deprecated aliases.
        paginas : int, list, range, or None
            Pages to download (1-based). int: paginas=3 downloads pages 1-3.
            range: range(1, 4) downloads pages 1-3. None: downloads all.
        numero_recurso : str, optional
            Case/appeal number filter.
        orgaos : list, optional
            List of orgao julgador IDs to filter.
        relatores : list, optional
            List of relator IDs to filter.
        classe : list, optional
            List of class IDs to filter. ``classes`` (plural) e aceito como
            alias deprecado (emite :class:`DeprecationWarning`). Refs #232.
        data_publicacao_inicio : str, optional
            Start date for publication filter (YYYY-MM-DD).
        data_publicacao_fim : str, optional
            End date for publication filter (YYYY-MM-DD).
        segundo_grau : bool
            Include second-instance results (default True).
        turmas_recursais : bool
            Include turmas recursais results (default True).
        tipo_acordaos : bool
            Include acordaos (default True).
        tipo_decisoes_monocraticas : bool
            Include monocratic decisions (default True).
        tamanho_pagina : int
            Results per page (default 10). Aceita ``items_per_page`` como
            alias deprecado (emite ``DeprecationWarning``).

        Returns
        -------
        list
            List of raw GraphQL response dicts (one per page).
        """
        tamanho_pagina = resolve_deprecated_alias(
            kwargs, "items_per_page", "tamanho_pagina", tamanho_pagina, sentinel=10
        )
        # Popa alias plural antes do pydantic — sem isso o schema canonico
        # (que so declara o singular ``classe``) trataria ``classes`` como
        # ``extra_forbidden``. Usa ``classe is not None`` (nao ``in kwargs``)
        # para nao tratar ``classe=None`` explicito como conflito. Refs #232.
        if "classes" in kwargs:
            if classe is not None:
                kwargs.pop("classes")
                raise ValueError(
                    "Nao e possivel passar 'classe' e 'classes' simultaneamente."
                )
            classe = pop_deprecated_alias(kwargs, "classes", "classe")
        inp = apply_input_pipeline_search(
            InputCJSGTJBA,
            "TJBAScraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            data_publicacao_inicio=data_publicacao_inicio,
            data_publicacao_fim=data_publicacao_fim,
            numero_recurso=numero_recurso,
            orgaos=orgaos,
            relatores=relatores,
            classe=classe,
            segundo_grau=segundo_grau,
            turmas_recursais=turmas_recursais,
            tipo_acordaos=tipo_acordaos,
            tipo_decisoes_monocraticas=tipo_decisoes_monocraticas,
            ordenado_por=ordenado_por,
            tamanho_pagina=tamanho_pagina,
        )
        return cjsg_download(
            pesquisa=inp.pesquisa,
            paginas=inp.paginas,
            numero_recurso=inp.numero_recurso,
            orgaos=inp.orgaos,
            relatores=inp.relatores,
            classes=inp.classe,
            data_publicacao_inicio=inp.data_publicacao_inicio,
            data_publicacao_fim=inp.data_publicacao_fim,
            segundo_grau=inp.segundo_grau,
            turmas_recursais=inp.turmas_recursais,
            tipo_acordaos=inp.tipo_acordaos,
            tipo_decisoes_monocraticas=inp.tipo_decisoes_monocraticas,
            ordenado_por=inp.ordenado_por,
            items_per_page=inp.tamanho_pagina,
            request_fn=self._request_with_retry,
        )

    def cjsg_parse(self, resultados_brutos: list) -> pd.DataFrame:
        """
        Parse raw results from TJBA into a DataFrame.

        Parameters
        ----------
        resultados_brutos : list
            Raw response dicts as returned by ``cjsg_download``.

        Returns
        -------
        pd.DataFrame
            DataFrame with one row per decision.
        """
        return cjsg_parse(resultados_brutos)

    def cjsg(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        numero_recurso: str | None = None,
        orgaos: list | None = None,
        relatores: list | None = None,
        classe: list | None = None,
        data_publicacao_inicio: str | None = None,
        data_publicacao_fim: str | None = None,
        segundo_grau: bool = True,
        turmas_recursais: bool = True,
        tipo_acordaos: bool = True,
        tipo_decisoes_monocraticas: bool = True,
        ordenado_por: str = "dataPublicacao",
        tamanho_pagina: int = 10,
        **kwargs,
    ) -> pd.DataFrame:
        """
        Search TJBA jurisprudence (download + parse).

        Returns a ready-to-analyze DataFrame.

        Parameters
        ----------
        pesquisa : str
            Search term. ``query`` and ``termo`` are accepted as deprecated aliases.
        paginas : int, list, range, or None
            Pages to download (1-based). None = all pages.
        data_publicacao_inicio : str, optional
            Start date (YYYY-MM-DD).
        data_publicacao_fim : str, optional
            End date (YYYY-MM-DD).
        tamanho_pagina : int
            Results per page (default 10).

        Aliases deprecados
        ------------------
        * ``items_per_page`` -> ``tamanho_pagina``
        * ``classes`` -> ``classe`` (refs #232)

        Returns
        -------
        pd.DataFrame
            Jurisprudence results.
        """
        brutos = self.cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            numero_recurso=numero_recurso,
            orgaos=orgaos,
            relatores=relatores,
            classe=classe,
            data_publicacao_inicio=data_publicacao_inicio,
            data_publicacao_fim=data_publicacao_fim,
            segundo_grau=segundo_grau,
            turmas_recursais=turmas_recursais,
            tipo_acordaos=tipo_acordaos,
            tipo_decisoes_monocraticas=tipo_decisoes_monocraticas,
            ordenado_por=ordenado_por,
            tamanho_pagina=tamanho_pagina,
            **kwargs,
        )
        return self.cjsg_parse(brutos)
