"""Main scraper for Tribunal de Justiça de São Paulo (TJSP)."""
from __future__ import annotations

import logging
import os
import shutil
import tempfile
from typing import Any, List, Literal, Optional, Union

from pydantic import BaseModel

from ...utils.params import SEARCH_ALIASES, apply_input_pipeline_cjsg, normalize_pesquisa
from .._esaj.base import EsajSearchScraper
from .cjpg_download import cjpg_download as cjpg_download_mod
from .cjpg_parse import cjpg_n_pags, cjpg_parse_manager
from .cpopg_download import cpopg_download_api, cpopg_download_html
from .cpopg_parse import cpopg_parse_manager, get_cpopg_download_links
from .cposg_download import cposg_download_api, cposg_download_html
from .cposg_parse import cposg_parse_manager
from .exceptions import QueryTooLongError, validate_pesquisa_length
from .forms import build_tjsp_cjsg_body
from .schemas import InputCJPGTJSP, InputCJSGTJSP

logger = logging.getLogger("juscraper.tjsp")


class TJSPScraper(EsajSearchScraper):
    """Main scraper for TJSP — eSAJ web + api.tjsp.jus.br."""

    BASE_URL = "https://esaj.tjsp.jus.br/"
    TRIBUNAL_NAME = "TJSP"
    INPUT_CJSG = InputCJSGTJSP
    CJSG_CHROME_UA = True
    CJSG_EXTRACT_CONVERSATION_ID = True

    def __init__(
        self,
        verbose: int = 0,
        download_path: str | None = None,
        sleep_time: float = 0.5,
        **kwargs: Any,
    ):
        super().__init__(
            verbose=verbose,
            download_path=download_path,
            sleep_time=sleep_time,
            **kwargs,
        )
        self.u_base = self.BASE_URL
        self.api_base = "https://api.tjsp.jus.br/"
        self.method: Optional[Literal["html", "api"]] = None

    def set_download_path(self, path: str | None = None):
        """Set download base dir; creates a tempdir when ``path`` is ``None``."""
        if path is None:
            path = tempfile.mkdtemp()
        self.download_path = path

    def set_method(self, method: Literal["html", "api"]):
        """Validate and store the access method (``'html'`` or ``'api'``) for cpopg/cposg."""
        if method not in ("html", "api"):
            raise ValueError(
                f"Método {method} nao suportado. Os métodos suportados são 'html' e 'api'."
            )
        self.method = method

    # --- cjsg -----------------------------------------------------------

    def cjsg_download(
        self,
        pesquisa: str,
        paginas: int | list | range | None = None,
        diretorio: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Download TJSP cjsg pages. Length check happens before pydantic
        so ``QueryTooLongError`` propagates cleanly.
        """
        pesquisa = normalize_pesquisa(pesquisa, **kwargs)
        # Only the search aliases get popped here; the base class will run
        # normalize_datas on the date aliases before popping them, preserving
        # the DeprecationWarning they emit.
        for alias in SEARCH_ALIASES:
            kwargs.pop(alias, None)
        validate_pesquisa_length(pesquisa, endpoint="CJSG")
        return super().cjsg_download(
            pesquisa=pesquisa, paginas=paginas, diretorio=diretorio, **kwargs,
        )

    def _build_cjsg_body(self, inp: BaseModel) -> dict:
        data = inp.model_dump()
        body: dict = build_tjsp_cjsg_body(
            pesquisa=data["pesquisa"],
            ementa=data.get("ementa"),
            classe=data.get("classe"),
            assunto=data.get("assunto"),
            comarca=data.get("comarca"),
            orgao_julgador=data.get("orgao_julgador"),
            data_julgamento_inicio=data.get("data_julgamento_inicio"),
            data_julgamento_fim=data.get("data_julgamento_fim"),
            baixar_sg=data.get("baixar_sg", True),
            tipo_decisao=data.get("tipo_decisao", "acordao"),
        )
        return body

    # --- cjpg -----------------------------------------------------------
    # Internals (``cjpg_download.py`` + ``cjpg_parse.py``) are unique to
    # TJSP, so they're kept as-is. The public entry point still routes
    # through pydantic (``InputCJPGTJSP``) for documentation + rejection
    # of unknown kwargs.

    def cjpg(
        self,
        pesquisa: str = "",
        paginas: int | list | range | None = None,
        **kwargs: Any,
    ):
        """Search TJSP first-degree jurisprudence (CJPG) and return a DataFrame."""
        path = self.cjpg_download(pesquisa=pesquisa, paginas=paginas, **kwargs)
        try:
            return self.cjpg_parse(path)
        finally:
            shutil.rmtree(path, ignore_errors=True)

    def cjpg_download(
        self,
        pesquisa: str = "",
        paginas: int | list | range | None = None,
        **kwargs: Any,
    ) -> str:
        """Download raw CJPG HTML result pages. Returns the output directory path."""
        # CJPG allows pesquisa="" (default) — only call normalize_pesquisa
        # when pesquisa was explicitly passed OR a deprecated alias is in
        # kwargs. normalize_pesquisa refuses to reconcile pesquisa="" with
        # an alias, so we pass None when pesquisa is empty to let the alias
        # take precedence.
        has_alias = "query" in kwargs or "termo" in kwargs
        if pesquisa or has_alias:
            pesquisa = normalize_pesquisa(pesquisa or None, **kwargs)
        validate_pesquisa_length(pesquisa, endpoint="CJPG")

        inp = apply_input_pipeline_cjsg(
            InputCJPGTJSP,
            f"{type(self).__name__}.cjpg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
        )

        def _get_n_pags(r0):
            html = r0.content if hasattr(r0, "content") else r0
            return cjpg_n_pags(html)

        path: str = cjpg_download_mod(
            pesquisa=inp.pesquisa,
            session=self.session,
            u_base=self.u_base,
            download_path=self.download_path,
            sleep_time=self.sleep_time,
            classes=inp.classes,
            assuntos=inp.assuntos,
            varas=inp.varas,
            id_processo=inp.id_processo,
            data_inicio=inp.data_julgamento_inicio,
            data_fim=inp.data_julgamento_fim,
            paginas=inp.paginas,
            get_n_pags_callback=_get_n_pags,
        )
        return path

    def cjpg_parse(self, path: str):
        """Parse downloaded CJPG HTML files into a DataFrame."""
        return cjpg_parse_manager(path)

    # --- cpopg ----------------------------------------------------------
    # Kept as-is — unique to TJSP, not eSAJ-search-shaped.

    def cpopg(self, id_cnj: Union[str, List[str]], method: Literal["html", "api"] = "html"):
        """Fetch a first-degree process by CNJ and return a DataFrame."""
        self.set_method(method)
        self.cpopg_download(id_cnj, method)
        result = self.cpopg_parse(self.download_path)
        shutil.rmtree(self.download_path)
        return result

    def cpopg_download(
        self,
        id_cnj: Union[str, List[str]],
        method: Literal["html", "api"] = "html",
    ):
        """Download raw CPOPG files for one or many CNJs via ``'html'`` or ``'api'``."""
        self.set_method(method)
        if isinstance(id_cnj, str):
            id_cnj = [id_cnj]
        if self.method == "html":
            def get_links_callback(response):
                return get_cpopg_download_links(response)
            cpopg_download_html(
                id_cnj_list=id_cnj,
                session=self.session,
                u_base=self.u_base,
                download_path=self.download_path,
                sleep_time=self.sleep_time,
                get_links_callback=get_links_callback,
            )
        elif self.method == "api":
            cpopg_download_api(
                id_cnj_list=id_cnj,
                session=self.session,
                api_base=self.api_base,
                download_path=self.download_path,
            )
        else:
            raise ValueError(f"Método '{method}' não é suportado.")

    def cpopg_parse(self, path: str):
        """Parse downloaded CPOPG files into a DataFrame."""
        return cpopg_parse_manager(path)

    # --- cposg ----------------------------------------------------------

    def cposg(self, id_cnj: str, method: Literal["html", "api"] = "html"):
        """Fetch a second-degree process by CNJ and return a DataFrame."""
        self.set_method(method)
        path = self.download_path
        self.cposg_download(id_cnj, method)
        result = self.cposg_parse(path)
        if os.path.exists(path):
            shutil.rmtree(path)
        else:
            logger.warning("[TJSP] Aviso: diretório %s não existe e não pôde ser removido.", path)
        return result

    def cposg_download(self, id_cnj: Union[str, list], method: Literal["html", "api"] = "html"):
        """Download raw CPOSG files for one or many CNJs via ``'html'`` or ``'api'``."""
        self.set_method(method)
        if isinstance(id_cnj, str):
            id_cnj = [id_cnj]
        if self.method == "html":
            cposg_download_html(
                id_cnj_list=id_cnj,
                session=self.session,
                u_base=self.u_base,
                download_path=self.download_path,
                sleep_time=self.sleep_time,
            )
        elif self.method == "api":
            cposg_download_api(
                id_cnj_list=id_cnj,
                session=self.session,
                api_base=self.api_base,
                download_path=self.download_path,
                sleep_time=self.sleep_time,
            )
        else:
            raise ValueError(f"Método '{method}' não é suportado.")

    def cposg_parse(self, path: str):
        """Parse downloaded CPOSG files into a DataFrame."""
        return cposg_parse_manager(path)


__all__ = ["TJSPScraper", "QueryTooLongError"]
