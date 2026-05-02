"""Scraper for the Tribunal de Justica da Paraiba (TJPB)."""
from datetime import date, datetime
from typing import List, Optional, Union

import pandas as pd
import requests

from juscraper.core.base import BaseScraper
from juscraper.utils.params import (
    apply_input_pipeline_search,
    coerce_brazilian_date,
    pop_deprecated_alias,
    resolve_deprecated_alias,
)

from .download import cjsg_download_manager
from .parse import cjsg_parse_manager
from .schemas import InputCJSGTJPB


def _parse_backend_date(d: Optional[str]) -> Optional[date]:
    """Parse a date string already coerced to ``InputCJSGTJPB.BACKEND_DATE_FORMAT``.

    ``apply_input_pipeline_search`` runs ``coerce_brazilian_date`` against the
    schema's ``BACKEND_DATE_FORMAT`` before instantiating the model, so values
    on ``inp.data_julgamento_*`` are guaranteed to be either ``""``/``None`` or
    a string in that format. Returns ``None`` for empty/malformed input so the
    post-filter caller can short-circuit.
    """
    if not d:
        return None
    try:
        return datetime.strptime(d, InputCJSGTJPB.BACKEND_DATE_FORMAT).date()
    except (ValueError, TypeError):
        return None


class TJPBScraper(BaseScraper):
    """Scraper for the Tribunal de Justica da Paraiba (TJPB).

    Uses the PJe jurisprudence search at pje-jurisprudencia.tjpb.jus.br.
    Built on the same platform developed by TJRN (Laravel + Elasticsearch).
    """

    BASE_URL = "https://pje-jurisprudencia.tjpb.jus.br"

    def __init__(self):
        super().__init__("TJPB")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
        })

    def cpopg(self, id_cnj: Union[str, List[str]]):
        """Stub: first instance case consultation not implemented for TJPB."""
        raise NotImplementedError("Consulta de processos de 1o grau nao implementada para TJPB.")

    def cposg(self, id_cnj: Union[str, List[str]]):
        """Stub: second instance case consultation not implemented for TJPB."""
        raise NotImplementedError("Consulta de processos de 2o grau nao implementada para TJPB.")

    def cjsg(
        self,
        pesquisa: Optional[str] = None,
        paginas: Union[int, list, range, None] = None,
        numero_processo: str = "",
        id_classe_judicial: str = "",
        id_orgao_julgador: str = "",
        id_relator: str = "",
        id_origem: str = "8,2",
        decisoes: bool = False,
        data_julgamento_inicio: Optional[str] = None,
        data_julgamento_fim: Optional[str] = None,
        **kwargs,
    ) -> pd.DataFrame:
        """Search TJPB jurisprudence.

        Parameters
        ----------
        pesquisa : str
            Free-text search term (searched in ementa).
        paginas : int, list, range, or None
            Pages to download (1-based). None downloads all.
        numero_processo : str, optional
            Process number filter. Accepts the deprecated alias ``nr_processo``.
        id_classe_judicial : str, optional
            Judicial class ID.
        id_orgao_julgador : str, optional
            Judging body ID.
        id_relator : str, optional
            Reporter judge ID.
        id_origem : str, optional
            Origin filter. ``"8,2"`` for all (default), ``"8"`` for Turmas Recursais,
            ``"2"`` for Tribunal Pleno/Camaras.
        decisoes : bool
            If True, include monocratic decisions.
        data_julgamento_inicio, data_julgamento_fim : str, optional
            Julgamento date range. Backend filtra dt_disponibilizacao, mas o
            DataFrame expoe dt_ementa como ``data_julgamento`` — pos-filtro
            aplicado para alinhar com a intencao do usuario.

        Returns
        -------
        pd.DataFrame
        """
        # Resolve datas aliases here so the post-filter has access to the
        # canonical values; cjsg_download will handle pesquisa/numero_processo
        # aliases via the pipeline.
        for old, new, current in (
            ("data_inicio", "data_julgamento_inicio", data_julgamento_inicio),
            ("data_fim", "data_julgamento_fim", data_julgamento_fim),
            ("data_julgamento_de", "data_julgamento_inicio", data_julgamento_inicio),
            ("data_julgamento_ate", "data_julgamento_fim", data_julgamento_fim),
        ):
            if old in kwargs:
                if current is not None and current != "":
                    raise ValueError(
                        f"Não é possível passar '{new}' e '{old}' ao mesmo tempo. "
                        f"Use apenas '{new}'."
                    )
                value = pop_deprecated_alias(kwargs, old, new)
                if new == "data_julgamento_inicio":
                    data_julgamento_inicio = value
                else:
                    data_julgamento_fim = value

        df = self.cjsg_parse(self.cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            numero_processo=numero_processo,
            id_classe_judicial=id_classe_judicial,
            id_orgao_julgador=id_orgao_julgador,
            id_relator=id_relator,
            id_origem=id_origem,
            decisoes=decisoes,
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            **kwargs,
        ))

        # The TJPB backend filter on dt_inicio/dt_fim acts on an internal
        # disponibilização date, not on dt_ementa. Rows returned can have
        # dt_ementa far outside the requested window. Post-filter so the
        # returned data_julgamento (= dt_ementa) matches user intent.
        if not df.empty and "data_julgamento" in df.columns:
            backend_format = InputCJSGTJPB.BACKEND_DATE_FORMAT
            start = _parse_backend_date(coerce_brazilian_date(data_julgamento_inicio, backend_format))
            end = _parse_backend_date(coerce_brazilian_date(data_julgamento_fim, backend_format))
            if start is not None and end is not None:
                mask = df["data_julgamento"].between(start, end)
                df = df[mask].reset_index(drop=True)
        return df

    def cjsg_download(
        self,
        pesquisa: Optional[str] = None,
        paginas: Union[int, list, range, None] = None,
        numero_processo: str = "",
        id_classe_judicial: str = "",
        id_orgao_julgador: str = "",
        id_relator: str = "",
        id_origem: str = "8,2",
        decisoes: bool = False,
        **kwargs,
    ) -> list:
        """Download raw CJSG JSON responses from TJPB.

        Aceita os mesmos filtros de :meth:`cjsg`; veja la a lista completa.

        Returns
        -------
        list
            List of raw JSON responses (one per page).
        """
        numero_processo = resolve_deprecated_alias(
            kwargs, "nr_processo", "numero_processo", numero_processo, sentinel=""
        )
        inp = apply_input_pipeline_search(
            InputCJSGTJPB,
            "TJPBScraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            numero_processo=numero_processo,
            id_classe_judicial=id_classe_judicial,
            id_orgao_julgador=id_orgao_julgador,
            id_relator=id_relator,
            id_origem=id_origem,
            decisoes=decisoes,
        )
        return cjsg_download_manager(
            pesquisa=inp.pesquisa,
            paginas=inp.paginas,
            session=self.session,
            nr_processo=inp.numero_processo,
            id_classe_judicial=inp.id_classe_judicial,
            id_orgao_julgador=inp.id_orgao_julgador,
            id_relator=inp.id_relator,
            dt_inicio=inp.data_julgamento_inicio or "",
            dt_fim=inp.data_julgamento_fim or "",
            id_origem=inp.id_origem,
            decisoes=inp.decisoes,
        )

    def cjsg_parse(self, resultados_brutos: list) -> pd.DataFrame:
        """Parse downloaded CJSG JSON responses.

        Returns
        -------
        pd.DataFrame
        """
        return cjsg_parse_manager(resultados_brutos)
