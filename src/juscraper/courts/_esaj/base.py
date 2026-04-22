"""Base class for eSAJ cjsg scrapers.

Absorbs the constructor + ``cjsg``/``cjsg_download``/``cjsg_parse`` template
shared by TJAC/TJAL/TJAM/TJCE/TJMS. Subclasses set ``BASE_URL`` and the
pydantic input schema; TJSP adds a Chrome UA and conversationId
propagation via class attributes.

Hooks a subclass may override:

* ``_configure_session`` — mount custom HTTPAdapter (TJCE TLS).
* ``INPUT_CJSG`` — swap ``InputCJSGEsajPuro`` for a tribunal-specific
  schema (TJSP uses ``InputCJSGTJSP`` which enforces a 120-char limit).
"""
from __future__ import annotations

import logging
import shutil
from typing import Any

import requests
from pydantic import BaseModel, ValidationError

from ...core.base import BaseScraper
from ...utils.params import normalize_datas, normalize_paginas, normalize_pesquisa, validate_intervalo_datas
from .download import download_cjsg_pages
from .forms import build_cjsg_form_body
from .parse import cjsg_n_pags, cjsg_parse_manager
from .schemas import InputCJSGEsajPuro

logger = logging.getLogger("juscraper._esaj.base")


def _raise_on_extra(exc: ValidationError, method: str) -> None:
    """Convert pydantic ``extra_forbidden`` errors into a ``TypeError``.

    Regular users expect ``TypeError: got unexpected keyword argument`` when
    they mistype a param name. Raising pydantic's ``ValidationError`` for
    that case is accurate but unfriendly. Other validation errors (e.g.
    bad date format) surface as-is.
    """
    extras = [err for err in exc.errors() if err["type"] == "extra_forbidden"]
    if extras and len(extras) == len(exc.errors()):
        names = ", ".join(repr(err["loc"][-1]) for err in extras)
        raise TypeError(f"{method} got unexpected keyword argument(s): {names}") from exc


class EsajSearchScraper(BaseScraper):
    """Shared scaffolding for eSAJ cjsg scrapers.

    Class attributes:
        BASE_URL: eSAJ root, e.g. ``https://esaj.tjac.jus.br/`` (must end
            with ``/``).
        TRIBUNAL_NAME: Used in logs and :attr:`BaseScraper.tribunal_name`.
        INPUT_CJSG: Pydantic model validating ``cjsg`` inputs. Defaults to
            :class:`InputCJSGEsajPuro`. TJSP overrides with its own model.
        CJSG_CHROME_UA: TJSP only — sends the Chrome-flavoured UA that the
            eSAJ form expects from browsers.
        CJSG_EXTRACT_CONVERSATION_ID: TJSP only — capture ``conversationId``
            from the first-page HTML and propagate to subsequent GETs.
    """

    BASE_URL: str = ""
    TRIBUNAL_NAME: str = ""
    INPUT_CJSG: type[BaseModel] = InputCJSGEsajPuro
    CJSG_CHROME_UA: bool = False
    CJSG_EXTRACT_CONVERSATION_ID: bool = False

    def __init__(
        self,
        verbose: int = 0,
        download_path: str | None = None,
        sleep_time: float = 1.0,
        **kwargs: Any,
    ):
        if not self.BASE_URL:
            raise NotImplementedError(
                f"{type(self).__name__} must set BASE_URL as a class attribute."
            )
        super().__init__(self.TRIBUNAL_NAME or type(self).__name__)
        self.session = requests.Session()
        self._configure_session(self.session)
        self.set_verbose(verbose)
        self.set_download_path(download_path)
        self.sleep_time = sleep_time
        self.args = kwargs

    # --- hook -----------------------------------------------------------

    def _configure_session(self, session: requests.Session) -> None:
        """Override to mount custom adapters. Default: no-op.

        TJCE attaches a TLS adapter with ``SECLEVEL=1`` to accept the court's
        outdated cipher suite.
        """

    # --- cjsg -----------------------------------------------------------

    def cjsg(
        self,
        pesquisa: str,
        paginas: int | list | range | None = None,
        **kwargs: Any,
    ):
        """Search this tribunal's second-degree jurisprudence (cjsg).

        Delegates to :meth:`cjsg_download` + :meth:`cjsg_parse`. The
        downloaded directory is cleaned up before returning.
        """
        path = self.cjsg_download(pesquisa=pesquisa, paginas=paginas, **kwargs)
        try:
            return self.cjsg_parse(path)
        finally:
            shutil.rmtree(path, ignore_errors=True)

    def cjsg_download(
        self,
        pesquisa: str,
        paginas: int | list | range | None = None,
        diretorio: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Download raw HTML result pages for ``cjsg``.

        ``diretorio`` overrides :attr:`download_path` for this single call.
        Deprecated aliases (``query``/``termo`` for ``pesquisa``,
        ``data_inicio``/``data_fim`` and ``_de``/``_ate`` for date fields)
        are popped from ``kwargs`` with a ``DeprecationWarning`` before
        pydantic validation.
        """
        pesquisa = normalize_pesquisa(pesquisa, **kwargs)
        for alias in ("query", "termo"):
            kwargs.pop(alias, None)
        paginas_norm = normalize_paginas(paginas)
        datas = normalize_datas(**kwargs)
        for alias in (
            "data_julgamento_inicio", "data_julgamento_fim",
            "data_publicacao_inicio", "data_publicacao_fim",
            "data_julgamento_de", "data_julgamento_ate",
            "data_publicacao_de", "data_publicacao_ate",
            "data_inicio", "data_fim",
        ):
            kwargs.pop(alias, None)

        validate_intervalo_datas(
            datas["data_julgamento_inicio"],
            datas["data_julgamento_fim"],
            rotulo="data_julgamento",
        )
        validate_intervalo_datas(
            datas["data_publicacao_inicio"],
            datas["data_publicacao_fim"],
            rotulo="data_publicacao",
        )

        try:
            input_model = self.INPUT_CJSG(
                pesquisa=pesquisa,
                paginas=paginas_norm,
                **{k: v for k, v in datas.items() if v is not None},
                **kwargs,
            )
        except ValidationError as exc:
            _raise_on_extra(exc, f"{type(self).__name__}.cjsg_download()")
            raise

        body = self._build_cjsg_body(input_model)

        return download_cjsg_pages(
            session=self.session,
            base_url=self.BASE_URL,
            download_path=diretorio or self.download_path,
            body=body,
            tipo_decisao=getattr(input_model, "tipo_decisao", "acordao"),
            paginas=input_model.paginas,
            get_n_pags_callback=cjsg_n_pags,
            sleep_time=self.sleep_time,
            chrome_ua=self.CJSG_CHROME_UA,
            extract_conversation_id=self.CJSG_EXTRACT_CONVERSATION_ID,
            progress_desc=f"Baixando CJSG {self.tribunal_name}",
        )

    def cjsg_parse(self, path: str):
        """Parse downloaded ``cjsg`` HTML files into a ``pd.DataFrame``."""
        return cjsg_parse_manager(path)

    def _build_cjsg_body(self, inp: BaseModel) -> dict:
        """Convert the validated pydantic input into the eSAJ form body.

        Default builder assumes :class:`InputCJSGEsajPuro`. TJSP overrides
        because its body drops ``conversationId``/``dtPublicacao*`` and
        swaps ``origem`` for ``baixar_sg``.
        """
        data = inp.model_dump()
        body: dict = build_cjsg_form_body(
            pesquisa=data["pesquisa"],
            ementa=data.get("ementa"),
            numero_recurso=data.get("numero_recurso"),
            classe=data.get("classe"),
            assunto=data.get("assunto"),
            comarca=data.get("comarca"),
            orgao_julgador=data.get("orgao_julgador"),
            data_julgamento_inicio=data.get("data_julgamento_inicio"),
            data_julgamento_fim=data.get("data_julgamento_fim"),
            data_publicacao_inicio=data.get("data_publicacao_inicio"),
            data_publicacao_fim=data.get("data_publicacao_fim"),
            origem=data.get("origem", "T"),
            tipo_decisao=data.get("tipo_decisao", "acordao"),
        )
        return body
