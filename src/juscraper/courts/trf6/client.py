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
from ...core.failures import COLUNA_MOTIVO_FALHA, avisar_falhas, motivo_falha_ou_inesperada
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

    def _baixar(self, cnjs: list[str]) -> tuple[list[str | None], list[str | None]]:
        """Detalhe HTML e motivo de falha de cada CNJ, na ordem da entrada.

        Processo ausente da consulta pública sai ``None`` sem motivo. A
        requisição que falha sai ``None`` com o motivo, e o lote segue.
        """
        htmls: list[str | None] = []
        motivos: list[str | None] = []
        for i, cnj in enumerate(tqdm(cnjs, desc="TRF6 cpopg")):
            html: str | None = None
            motivo: str | None = None
            try:
                html = self._fetch_one(cnj)
            except requests.RequestException as exc:
                logger.warning("Erro ao consultar %s: %s", cnj, exc)
                motivo = motivo_falha_ou_inesperada(exc)
            htmls.append(html)
            motivos.append(motivo)
            if i + 1 < len(cnjs) and self.sleep_time:
                time.sleep(self.sleep_time)
        return htmls, motivos

    @staticmethod
    def _avisar(cnjs: list[str], motivos: list[str | None], metodo: str) -> None:
        """Um ``UserWarning`` com os CNJs cuja requisição falhou."""
        falhas = [f"processo {c}: {m}" for c, m in zip(cnjs, motivos, strict=True) if m]
        avisar_falhas(falhas, f"TRF6Scraper.{metodo}", "consulta(s) de processo")

    # --- public API ------------------------------------------------------

    def cpopg_download(
        self,
        id_cnj: str | list[str],
        **kwargs: Any,
    ) -> list[str | None]:
        """Baixa o HTML do detalhe de cada ``id_cnj``.

        Devolve uma lista na ordem da entrada. ``None`` indica processo que a
        consulta pública não devolveu: sigilo, CNJ inexistente ou falha da
        requisição. Falhas de requisição não interrompem o lote e entram num
        único ``UserWarning`` ao fim; :meth:`cpopg` traz o motivo de cada uma
        em ``motivo_falha``. Falhas do resolvedor de captcha
        (``RuntimeError``) propagam.
        """
        cnjs = self._coerce_id_cnj(id_cnj, **kwargs)
        htmls, motivos = self._baixar(cnjs)
        self._avisar(cnjs, motivos, "cpopg_download")
        return htmls

    def cpopg_parse(
        self,
        htmls: list[str | None],
        id_cnj_list: list[str],
    ) -> pd.DataFrame:
        """Parse a list of detail HTMLs into a one-row-per-process DataFrame.

        Rows for ``None`` entries carry ``id_cnj`` plus ``None`` in every
        other column, so callers can still distinguish "looked up but
        missing" from "never tried". Sem a coluna ``motivo_falha``: um
        ``None`` vindo de :meth:`cpopg_download` pode ser processo ausente
        ou requisição que falhou, e só :meth:`cpopg` sabe qual.
        """
        if len(htmls) != len(id_cnj_list):
            raise ValueError(
                "htmls and id_cnj_list must have the same length "
                f"({len(htmls)} != {len(id_cnj_list)})"
            )
        rows: list[dict[str, Any]] = []
        for cnj, html in zip(id_cnj_list, htmls, strict=False):
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
        ``assuntos``, ``polo_ativo``, ``polo_passivo``, ``mpf``, ``perito``,
        ``movimentacoes`` and ``motivo_falha``.

        ``motivo_falha`` é ``None`` quando a consulta respondeu, inclusive
        para processo ausente ou sob sigilo (linha só com ``id_cnj``).
        Quando a requisição de um CNJ falha, a linha sai só com ``id_cnj`` e
        o motivo, no vocabulário de
        :data:`juscraper.core.failures.MOTIVOS_FALHA` (``http_<status>``,
        ``timeout``, ``conexao``; ``resposta_inesperada`` para outro erro de
        requisição), e o lote segue. As falhas entram num único
        ``UserWarning`` ao fim.
        """
        cnjs = self._coerce_id_cnj(id_cnj, **kwargs)
        htmls, motivos = self._baixar(cnjs)
        df = self.cpopg_parse(htmls, cnjs)
        df[COLUNA_MOTIVO_FALHA] = motivos
        self._avisar(cnjs, motivos, "cpopg")
        return df
