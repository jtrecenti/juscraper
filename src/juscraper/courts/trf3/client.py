"""Scraper for the Tribunal Regional Federal da 3ª Região (TRF3).

Wraps the PJe public-consultation system at ``pje1g.trf3.jus.br/pje/``. The
TRF3 deployment sits behind an Akamai bot manager (``ak_bmsc`` cookie) which
silently drops connections that don't carry a realistic browser header set;
the headers in :mod:`juscraper.courts.trf3.download` (``BROWSER_HEADERS``)
are tuned to pass that challenge.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import pandas as pd
import requests
from pydantic import ValidationError
from tqdm import tqdm

from ...core.base import BaseScraper
from ...utils.cnj import clean_cnj, format_cnj
from .download import (
    BROWSER_HEADERS,
    build_search_payload,
    extract_ca_token,
    extract_form_field_ids,
    fetch_detail,
    fetch_form,
    submit_search,
)
from .parse import parse_detail
from .schemas import InputCpopgTRF3

logger = logging.getLogger("juscraper.trf3")


class TRF3Scraper(BaseScraper):
    """TRF3 PJe consulta pública (1º grau)."""

    BASE_URL = "https://pje1g.trf3.jus.br/pje/"

    def __init__(
        self,
        verbose: int = 0,
        download_path: str | None = None,
        sleep_time: float = 1.0,
        **kwargs: Any,
    ):
        super().__init__("TRF3")
        self.session = requests.Session()
        self.session.headers.update(BROWSER_HEADERS)
        self.set_verbose(verbose)
        self.set_download_path(download_path)
        self.sleep_time = sleep_time
        self.args = kwargs
        self._field_ids = None  # cached after first form fetch

    # --- internal helpers -----------------------------------------------

    def _ensure_field_ids(self):
        """Fetch the form once per session and memoize the auto-generated IDs."""
        if self._field_ids is None:
            form_html = fetch_form(self.session)
            self._field_ids = extract_form_field_ids(form_html)
            logger.debug("TRF3 field IDs: %s", self._field_ids)
        return self._field_ids

    def _coerce_id_cnj(self, id_cnj: str | list[str], **kwargs: Any) -> list[str]:
        """Validate via pydantic and return a list of cleaned 20-digit CNJs."""
        try:
            inp = InputCpopgTRF3(id_cnj=id_cnj, **kwargs)
        except ValidationError as exc:
            extras = [err for err in exc.errors() if err["type"] == "extra_forbidden"]
            if extras and len(extras) == len(exc.errors()):
                names = ", ".join(repr(err["loc"][-1]) for err in extras)
                raise TypeError(
                    f"TRF3Scraper.cpopg got unexpected keyword argument(s): {names}"
                ) from exc
            raise
        raw = inp.id_cnj if isinstance(inp.id_cnj, list) else [inp.id_cnj]
        return [clean_cnj(c) for c in raw]

    def _fetch_one(self, id_cnj_clean: str) -> str | None:
        """Run the 2-request flow for a single CNJ. Returns detail HTML or ``None``."""
        ids = self._ensure_field_ids()
        payload = build_search_payload(format_cnj(id_cnj_clean), ids)
        search_html = submit_search(self.session, payload)
        ca = extract_ca_token(search_html)
        if not ca:
            return None
        return fetch_detail(self.session, ca)

    # --- public API ------------------------------------------------------

    def cpopg_download(
        self,
        id_cnj: str | list[str],
        **kwargs: Any,
    ) -> list[str | None]:
        """Download the detail HTML for each ``id_cnj``.

        Returns a list aligned with the input order. ``None`` entries indicate
        processes the public consultation could not return — typically sigilo
        or invalid CNJ.
        """
        cnjs = self._coerce_id_cnj(id_cnj, **kwargs)
        results: list[str | None] = []
        for i, cnj in enumerate(tqdm(cnjs, desc="TRF3 cpopg")):
            try:
                results.append(self._fetch_one(cnj))
            except requests.RequestException as exc:
                logger.warning("Erro ao consultar %s: %s", cnj, exc)
                results.append(None)
            if i + 1 < len(cnjs) and self.sleep_time:
                time.sleep(self.sleep_time)
        return results

    def cpopg_parse(
        self,
        htmls: list[str | None],
        id_cnj_list: list[str],
    ) -> pd.DataFrame:
        """Parse a list of detail HTMLs into a one-row-per-process DataFrame.

        Rows for ``None`` entries (process not found) carry ``id_cnj`` plus
        ``None`` in every other column, so callers can still distinguish
        "looked up but missing" from "never tried".
        """
        if len(htmls) != len(id_cnj_list):
            raise ValueError(
                "htmls and id_cnj_list must have the same length "
                f"({len(htmls)} != {len(id_cnj_list)})"
            )
        rows: list[dict[str, Any]] = []
        for cnj, html in zip(id_cnj_list, htmls):
            if html is None:
                rows.append({"id_cnj": cnj})
            else:
                record = parse_detail(html)
                record["id_cnj"] = cnj
                rows.append(record)
        return pd.DataFrame(rows)

    def cpopg(
        self,
        id_cnj: str | list[str],
        **kwargs: Any,
    ) -> pd.DataFrame:
        """High-level ``cpopg`` lookup: download + parse.

        Accepts a single CNJ or a list. Returns a DataFrame with one row per
        process; columns include ``id_cnj``, ``processo``, ``classe``,
        ``assunto``, ``data_distribuicao``, ``orgao_julgador``,
        ``jurisdicao``, ``polo_ativo``, ``polo_passivo``, ``movimentacoes``
        and ``documentos``.
        """
        cnjs = self._coerce_id_cnj(id_cnj, **kwargs)
        htmls = self.cpopg_download(id_cnj, **kwargs)
        return self.cpopg_parse(htmls, cnjs)
