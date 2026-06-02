"""Scraper for the Tribunal Regional Federal da 6ª Região (TRF6).

Wraps the eproc public-consultation system at
``eproc1g.trf6.jus.br/eproc/`` (Seção Judiciária de Minas Gerais). The
form gates the search behind a text-based image captcha that the backend
*does* validate; we solve it via :mod:`txtcaptcha` (HuggingFace pretrained
CRNN). Each retry fetches a fresh captcha because the image is bound to
the session's ``PHPSESSID``.
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
from .download import BROWSER_HEADERS, fetch_detail
from .parse import parse_detail
from .schemas import InputCpopgTRF6

logger = logging.getLogger("juscraper.trf6")


class TRF6Scraper(BaseScraper):
    """TRF6 eproc consulta pública (1º grau)."""

    BASE_URL = "https://eproc1g.trf6.jus.br/eproc/"

    def __init__(
        self,
        verbose: int = 0,
        download_path: str | None = None,
        sleep_time: float = 1.0,
        max_captcha_attempts: int = 3,
        **kwargs: Any,
    ):
        super().__init__("TRF6")
        self.session = requests.Session()
        self.session.headers.update(BROWSER_HEADERS)
        self.set_verbose(verbose)
        self.set_download_path(download_path)
        self.sleep_time = sleep_time
        self.max_captcha_attempts = max_captcha_attempts
        self.args = kwargs

    # --- internal helpers -----------------------------------------------

    def _coerce_id_cnj(self, id_cnj: str | list[str], **kwargs: Any) -> list[str]:
        """Validate via pydantic and return a list of cleaned 20-digit CNJs."""
        try:
            inp = InputCpopgTRF6(id_cnj=id_cnj, **kwargs)
        except ValidationError as exc:
            extras = [err for err in exc.errors() if err["type"] == "extra_forbidden"]
            if extras and len(extras) == len(exc.errors()):
                names = ", ".join(repr(err["loc"][-1]) for err in extras)
                raise TypeError(
                    f"TRF6Scraper.cpopg got unexpected keyword argument(s): {names}"
                ) from exc
            raise
        raw = inp.id_cnj if isinstance(inp.id_cnj, list) else [inp.id_cnj]
        return [clean_cnj(c) for c in raw]

    def _fetch_one(self, id_cnj_clean: str) -> str | None:
        """Fetch the detail HTML for a single CNJ. ``None`` when not found."""
        formatted = format_cnj(id_cnj_clean)
        return fetch_detail(
            self.session,
            formatted,
            max_captcha_attempts=self.max_captcha_attempts,
        )

    # --- public API ------------------------------------------------------

    def cpopg_download(
        self,
        id_cnj: str | list[str],
        **kwargs: Any,
    ) -> list[str | None]:
        """Download the detail HTML for each ``id_cnj``.

        Returns a list aligned with the input order. ``None`` entries indicate
        processes the public consultation could not return — typically sigilo
        or invalid CNJ. Captcha-solver failures (``RuntimeError``) propagate.
        """
        cnjs = self._coerce_id_cnj(id_cnj, **kwargs)
        results: list[str | None] = []
        for i, cnj in enumerate(tqdm(cnjs, desc="TRF6 cpopg")):
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
        ``data_autuacao``, ``situacao``, ``magistrado``, ``orgao_julgador``,
        ``assuntos``, ``polo_ativo``, ``polo_passivo``, ``mpf``, ``perito``
        and ``movimentacoes``.
        """
        cnjs = self._coerce_id_cnj(id_cnj, **kwargs)
        htmls = self.cpopg_download(id_cnj, **kwargs)
        return self.cpopg_parse(htmls, cnjs)
