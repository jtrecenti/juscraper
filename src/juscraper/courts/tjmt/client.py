"""
Scraper for the Tribunal de Justica do Estado de Mato Grosso (TJMT).
"""

import pandas as pd
import requests

from juscraper.core.base import BaseScraper
from juscraper.utils.params import apply_input_pipeline_search

from .download import cjsg_download
from .parse import cjsg_parse
from .schemas import InputCJSGTJMT


class TJMTScraper(BaseScraper):
    """Scraper for the Tribunal de Justica do Estado de Mato Grosso (TJMT)."""

    BASE_URL = "https://hellsgate-preview.tjmt.jus.br/jurisprudencia"

    def __init__(self):
        super().__init__("TJMT")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
        })

    def cpopg(self, id_cnj: str | list[str]):
        """Stub: first instance case consultation not implemented for TJMT."""
        raise NotImplementedError("Consulta de processos de 1 grau nao implementada para TJMT.")

    def cposg(self, id_cnj: str | list[str]):
        """Stub: second instance case consultation not implemented for TJMT."""
        raise NotImplementedError("Consulta de processos de 2 grau nao implementada para TJMT.")

    def cjsg_download(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        tipo_consulta: str = "Acordao",
        relator: str | None = None,
        orgao_julgador: str | None = None,
        classe: str | None = None,
        tipo_processo: str | None = None,
        thesaurus: bool = False,
        quantidade_por_pagina: int = 10,
        data_julgamento_inicio: str | None = None,
        data_julgamento_fim: str | None = None,
        **kwargs,
    ) -> list:
        """Download raw JSON results from the TJMT jurisprudence API.

        Args:
            pesquisa: Search term. ``query`` and ``termo`` are accepted as deprecated aliases.
            paginas: Pages to download (1-based).
                int: paginas=3 downloads pages 1-3.
                range: range(1, 4) downloads pages 1-3.
                None: downloads all available pages.
            tipo_consulta: ``"Acordao"`` or ``"DecisaoMonocratica"``.
            relator: Filter by judge name.
            orgao_julgador: Filter by court chamber.
            classe: Filter by case class.
            tipo_processo: ``"Civel"`` or ``"Criminal"``.
            thesaurus: Whether to use synonym search.
            quantidade_por_pagina: Items per page (default 10).
            data_julgamento_inicio: Start date for filtering (``yyyy-mm-dd``).
            data_julgamento_fim: End date for filtering (``yyyy-mm-dd``).

        The backend exposes only a single date range (``filtro.periodoDataDe``
        / ``filtro.periodoDataAte``) applied to the judgment date; passing
        ``data_publicacao_*`` raises ``TypeError``.
        """
        inp = apply_input_pipeline_search(
            InputCJSGTJMT,
            "TJMTScraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            tipo_consulta=tipo_consulta,
            relator=relator,
            orgao_julgador=orgao_julgador,
            classe=classe,
            tipo_processo=tipo_processo,
            thesaurus=thesaurus,
            quantidade_por_pagina=quantidade_por_pagina,
        )
        return cjsg_download(
            pesquisa=inp.pesquisa,
            paginas=inp.paginas,
            tipo_consulta=inp.tipo_consulta,
            data_julgamento_inicio=inp.data_julgamento_inicio,
            data_julgamento_fim=inp.data_julgamento_fim,
            relator=inp.relator,
            orgao_julgador=inp.orgao_julgador,
            classe=inp.classe,
            tipo_processo=inp.tipo_processo,
            thesaurus=inp.thesaurus,
            quantidade_por_pagina=inp.quantidade_por_pagina,
            session=self.session,
        )

    def cjsg_parse(self, resultados_brutos: list, tipo_consulta: str = "Acordao") -> list[dict]:
        """Parse raw JSON results into structured records.

        Args:
            resultados_brutos: List of raw JSON dicts (one per page).
            tipo_consulta: ``"Acordao"`` or ``"DecisaoMonocratica"``.

        Returns:
            List of flat dicts.
        """
        return cjsg_parse(resultados_brutos, tipo_consulta=tipo_consulta)

    def cjsg(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        tipo_consulta: str = "Acordao",
        relator: str | None = None,
        orgao_julgador: str | None = None,
        classe: str | None = None,
        tipo_processo: str | None = None,
        thesaurus: bool = False,
        quantidade_por_pagina: int = 10,
        data_julgamento_inicio: str | None = None,
        data_julgamento_fim: str | None = None,
        **kwargs,
    ) -> pd.DataFrame:
        """Search TJMT jurisprudence (download + parse).

        Returns a ready-to-analyze DataFrame.
        """
        brutos = self.cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            tipo_consulta=tipo_consulta,
            relator=relator,
            orgao_julgador=orgao_julgador,
            classe=classe,
            tipo_processo=tipo_processo,
            thesaurus=thesaurus,
            quantidade_por_pagina=quantidade_por_pagina,
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            **kwargs,
        )
        dados = self.cjsg_parse(brutos, tipo_consulta=tipo_consulta)
        df = pd.DataFrame(dados)
        for col in ["data_julgamento", "data_publicacao"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
        return df
