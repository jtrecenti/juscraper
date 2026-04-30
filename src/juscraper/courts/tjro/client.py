"""Scraper for the Tribunal de Justica de Rondonia (TJRO)."""
from typing import List, Optional, Union

import pandas as pd
import requests

from juscraper.core.base import BaseScraper
from juscraper.utils.params import (
    apply_input_pipeline_cjsg,
    normalize_paginas,
    normalize_pesquisa,
    pop_deprecated_alias,
    to_iso_date,
)

from .download import cjsg_download_manager
from .parse import cjsg_parse_manager
from .schemas import InputCJSGTJRO


class TJROScraper(BaseScraper):
    """Scraper for the Tribunal de Justica de Rondonia (TJRO).

    Uses the JURIS Elasticsearch backend at juris-back.tjro.jus.br.
    """

    BASE_URL = "https://juris.tjro.jus.br"

    def __init__(self):
        super().__init__("TJRO")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
        })

    def cpopg(self, id_cnj: Union[str, List[str]]):
        """Stub: first instance case consultation not implemented for TJRO."""
        raise NotImplementedError("Consulta de processos de 1o grau nao implementada para TJRO.")

    def cposg(self, id_cnj: Union[str, List[str]]):
        """Stub: second instance case consultation not implemented for TJRO."""
        raise NotImplementedError("Consulta de processos de 2o grau nao implementada para TJRO.")

    def cjsg(
        self,
        pesquisa: Optional[str] = None,
        paginas: Union[int, list, range, None] = None,
        tipo: list | None = None,
        numero_processo: str = "",
        relator: str = "",
        orgao_julgador: int | str = "",
        orgao_julgador_colegiado: int | str = "",
        classe: str = "",
        instancia: list | None = None,
        termo_exato: bool = False,
        **kwargs,
    ) -> pd.DataFrame:
        """Search TJRO jurisprudence.

        Parameters
        ----------
        pesquisa : str
            Free-text search term.
        paginas : int, list, range, or None
            Pages to download (1-based). None downloads all.
        tipo : list, optional
            Document types. Default ``["EMENTA"]``. Options include
            ``"ACORDAO"``, ``"DECISAO"``, ``"SENTENCA"``, ``"VOTO"``, etc.
        numero_processo : str, optional
            Process number filter. Accepts the deprecated alias ``nr_processo``.
        relator : str, optional
            Reporter judge name. Accepts the deprecated alias ``magistrado``
            (refs #129).
        orgao_julgador : int or str, optional
            Judging body ID.
        orgao_julgador_colegiado : int or str, optional
            Collegiate judging body ID.
        classe : str, optional
            Judicial class name. Accepts the deprecated alias
            ``classe_judicial`` (refs #129).
        instancia : list, optional
            Jurisdiction grades (e.g. ``[1]``, ``[2]``, ``[1, 2]``).
        termo_exato : bool
            If True, search for exact term.

        Returns
        -------
        pd.DataFrame
        """
        if "nr_processo" in kwargs:
            alias_value = pop_deprecated_alias(kwargs, "nr_processo", "numero_processo")
            if numero_processo:
                raise ValueError(
                    "Não é possível passar 'numero_processo' e 'nr_processo' simultaneamente."
                )
            numero_processo = alias_value or ""

        if "magistrado" in kwargs:
            alias_value = pop_deprecated_alias(kwargs, "magistrado", "relator")
            if relator:
                raise ValueError(
                    "Não é possível passar 'relator' e 'magistrado' simultaneamente."
                )
            relator = alias_value or ""

        if "classe_judicial" in kwargs:
            alias_value = pop_deprecated_alias(kwargs, "classe_judicial", "classe")
            if classe:
                raise ValueError(
                    "Não é possível passar 'classe' e 'classe_judicial' simultaneamente."
                )
            classe = alias_value or ""

        pesquisa = normalize_pesquisa(pesquisa, **kwargs)

        inp = apply_input_pipeline_cjsg(
            InputCJSGTJRO,
            "TJROScraper.cjsg()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            date_format="%Y-%m-%d",
            tipo=tipo,
            numero_processo=numero_processo,
            relator=relator,
            orgao_julgador=orgao_julgador,
            orgao_julgador_colegiado=orgao_julgador_colegiado,
            classe=classe,
            instancia=instancia,
            termo_exato=termo_exato,
        )

        brutos = self.cjsg_download(
            pesquisa=inp.pesquisa,
            paginas=inp.paginas,
            tipo=inp.tipo,
            nr_processo=inp.numero_processo,
            relator=inp.relator,
            orgao_julgador=inp.orgao_julgador,
            orgao_julgador_colegiado=inp.orgao_julgador_colegiado,
            classe=inp.classe,
            data_julgamento_inicio=to_iso_date(inp.data_julgamento_inicio) or "",
            data_julgamento_fim=to_iso_date(inp.data_julgamento_fim) or "",
            instancia=inp.instancia,
            termo_exato=inp.termo_exato,
        )
        return self.cjsg_parse(brutos)

    def cjsg_download(
        self,
        pesquisa: Optional[str] = None,
        paginas: Union[int, list, range, None] = None,
        **kwargs,
    ) -> list:
        """Download raw CJSG JSON responses from TJRO.

        Returns
        -------
        list
            List of raw JSON responses (one per page).
        """
        pesquisa = normalize_pesquisa(pesquisa, **kwargs)
        paginas = normalize_paginas(paginas)
        return cjsg_download_manager(
            pesquisa=pesquisa,
            paginas=paginas,
            session=self.session,
            **{k: v for k, v in kwargs.items() if k not in ("query", "termo")},
        )

    def cjsg_parse(self, resultados_brutos: list) -> pd.DataFrame:
        """Parse downloaded CJSG JSON responses.

        Returns
        -------
        pd.DataFrame
        """
        return cjsg_parse_manager(resultados_brutos)
