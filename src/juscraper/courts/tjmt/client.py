"""
Scraper for the Tribunal de Justica do Estado de Mato Grosso (TJMT).
"""
from typing import List, Optional, Union

import pandas as pd
import requests

from juscraper.core.base import BaseScraper
from juscraper.utils.params import apply_input_pipeline_search, normalize_paginas, normalize_pesquisa

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

    def cpopg(self, id_cnj: Union[str, List[str]]):
        """Stub: first instance case consultation not implemented for TJMT."""
        raise NotImplementedError("Consulta de processos de 1 grau nao implementada para TJMT.")

    def cposg(self, id_cnj: Union[str, List[str]]):
        """Stub: second instance case consultation not implemented for TJMT."""
        raise NotImplementedError("Consulta de processos de 2 grau nao implementada para TJMT.")

    def cjsg_download(
        self,
        pesquisa: Optional[str] = None,
        paginas: Union[int, list, range, None] = None,
        tipo_consulta: str = "Acordao",
        relator: Optional[str] = None,
        orgao_julgador: Optional[str] = None,
        classe: Optional[str] = None,
        tipo_processo: Optional[str] = None,
        thesaurus: bool = False,
        quantidade_por_pagina: int = 10,
        data_julgamento_inicio: Optional[str] = None,
        data_julgamento_fim: Optional[str] = None,
        data_publicacao_inicio: Optional[str] = None,
        data_publicacao_fim: Optional[str] = None,
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
        """
        pesquisa = normalize_pesquisa(pesquisa, **kwargs)
        paginas = normalize_paginas(paginas)
        # Re-inject explicit date args into kwargs so the pipeline can resolve
        # aliases (data_inicio/data_fim) and canonical names in a single pass.
        # Passing them as canonical_filters collides with what normalize_datas
        # extracts from kwargs.
        for _date_key, _date_val in (
            ("data_julgamento_inicio", data_julgamento_inicio),
            ("data_julgamento_fim", data_julgamento_fim),
            ("data_publicacao_inicio", data_publicacao_inicio),
            ("data_publicacao_fim", data_publicacao_fim),
        ):
            if _date_val is not None:
                kwargs[_date_key] = _date_val
        inp = apply_input_pipeline_search(
            InputCJSGTJMT,
            "TJMTScraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
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
        pesquisa: Optional[str] = None,
        paginas: Union[int, list, range, None] = None,
        tipo_consulta: str = "Acordao",
        relator: Optional[str] = None,
        orgao_julgador: Optional[str] = None,
        classe: Optional[str] = None,
        tipo_processo: Optional[str] = None,
        thesaurus: bool = False,
        quantidade_por_pagina: int = 10,
        data_julgamento_inicio: Optional[str] = None,
        data_julgamento_fim: Optional[str] = None,
        data_publicacao_inicio: Optional[str] = None,
        data_publicacao_fim: Optional[str] = None,
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
            data_publicacao_inicio=data_publicacao_inicio,
            data_publicacao_fim=data_publicacao_fim,
            **kwargs,
        )
        dados = self.cjsg_parse(brutos, tipo_consulta=tipo_consulta)
        df = pd.DataFrame(dados)
        for col in ["data_julgamento", "data_publicacao"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
        return df
