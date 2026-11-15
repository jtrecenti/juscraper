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
from typing import Any, NamedTuple

import pandas as pd
import requests
from pydantic import ValidationError

from ...core.base import BaseScraper
from ...core.exceptions import BotChallengeBlockedError
from ...core.failures import (
    COLUNA_MOTIVO_FALHA,
    MOTIVO_BLOQUEIO_ANTI_BOT,
    avisar_falhas_de_processos,
    consultar_ate_bloqueio,
    linhas_de_processos,
    motivo_falha_ou_inesperada,
)
from ...utils.cnj import clean_cnj, format_cnj
from .download import HEADERS, fetch_detail
from .parse import parse_detail
from .schemas import InputCpopgTRF6

logger = logging.getLogger("juscraper.trf6")


class _Consulta(NamedTuple):
    """Resultado da consulta de um CNJ."""

    html: str | None
    motivo: str | None


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
        self.session.headers.update(HEADERS)
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

    def _baixar(self, cnjs: list[str]) -> list[_Consulta]:
        """Detalhe HTML e motivo de falha de cada CNJ, na ordem da entrada.

        Regras de falha e de bloqueio anti-bot em :meth:`cpopg`. ``ImportError``
        (``txtcaptcha`` ausente) propaga.
        """
        return consultar_ate_bloqueio(
            cnjs,
            self._consultar,
            lambda: _Consulta(None, MOTIVO_BLOQUEIO_ANTI_BOT),
            sleep_time=self.sleep_time,
            desc="TRF6 cpopg",
        )

    def _consultar(self, cnj: str) -> _Consulta:
        """A consulta de um CNJ; a falha vem no motivo, e não como exceção."""
        try:
            return _Consulta(self._fetch_one(cnj), None)
        except BotChallengeBlockedError as exc:
            logger.warning("TRF6: bloqueio anti-bot em %s; o lote para aqui: %s", cnj, exc)
            return _Consulta(None, MOTIVO_BLOQUEIO_ANTI_BOT)
        except ImportError:
            raise
        except Exception as exc:  # noqa: BLE001 — resiliência por item
            logger.warning("Erro ao consultar %s: %s", cnj, exc)
            return _Consulta(None, motivo_falha_ou_inesperada(exc))

    @staticmethod
    def _avisar(cnjs: list[str], motivos: list[str | None], metodo: str) -> None:
        """Um ``UserWarning`` com os CNJs cuja consulta falhou."""
        avisar_falhas_de_processos(cnjs, motivos, f"TRF6Scraper.{metodo}")

    # --- public API ------------------------------------------------------

    def cpopg_download(
        self,
        id_cnj: str | list[str],
        **kwargs: Any,
    ) -> list[str | None]:
        """Baixa o HTML do detalhe de cada ``id_cnj``.

        Devolve uma lista na ordem da entrada. ``None`` indica processo que a
        consulta pública não devolveu: sigilo, CNJ inexistente ou falha da
        consulta (requisição, captcha esgotado). Falhas individuais não
        interrompem o lote; um bloqueio anti-bot encerra o lote e os CNJs
        restantes saem ``None``. As falhas entram num único ``UserWarning``
        ao fim; :meth:`cpopg` traz o motivo de cada uma em ``motivo_falha``.
        """
        cnjs = self._coerce_id_cnj(id_cnj, **kwargs)
        consultas = self._baixar(cnjs)
        self._avisar(cnjs, [c.motivo for c in consultas], "cpopg_download")
        return [c.html for c in consultas]

    def cpopg_parse(
        self,
        htmls: list[str | None],
        id_cnj_list: list[str],
    ) -> pd.DataFrame:
        """Parse a list of detail HTMLs into a one-row-per-process DataFrame.

        Rows for ``None`` entries carry ``id_cnj`` plus ``None`` in every
        other column, so callers can still distinguish "looked up but
        missing" from "never tried". Um HTML que o parser recusa vira linha
        só com ``id_cnj``, com ``UserWarning``, e o lote continua. Sem a
        coluna ``motivo_falha``: um ``None`` vindo de :meth:`cpopg_download`
        pode ser processo ausente ou consulta que falhou, e só :meth:`cpopg`
        sabe qual.
        """
        if len(htmls) != len(id_cnj_list):
            raise ValueError(
                "htmls and id_cnj_list must have the same length "
                f"({len(htmls)} != {len(id_cnj_list)})"
            )
        rows = linhas_de_processos(id_cnj_list, htmls, [None] * len(htmls), parse_detail, logger)
        self._avisar(id_cnj_list, [r.pop(COLUNA_MOTIVO_FALHA) for r in rows], "cpopg_parse")
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
        Quando a consulta de um CNJ falha, a linha sai só com ``id_cnj`` e
        o motivo, no vocabulário de
        :data:`juscraper.core.failures.MOTIVOS_FALHA` (``http_<status>``,
        ``timeout``, ``conexao``; ``resposta_inesperada`` para captcha
        esgotado, formulário sem captcha, HTML que o parser recusa ou outro
        erro), e o lote segue. Um desafio anti-bot vale para a sessão
        inteira: o lote para no CNJ desafiado, sem novos pedidos, e ele e os
        seguintes saem com ``bloqueio_anti_bot``. As falhas entram num único
        ``UserWarning`` ao fim
        (:class:`~juscraper.core.exceptions.BloqueioAntiBotWarning` quando
        há bloqueio anti-bot).
        """
        cnjs = self._coerce_id_cnj(id_cnj, **kwargs)
        consultas = self._baixar(cnjs)
        htmls = [c.html for c in consultas]
        rows = linhas_de_processos(cnjs, htmls, [c.motivo for c in consultas], parse_detail, logger)
        self._avisar(cnjs, [r[COLUNA_MOTIVO_FALHA] for r in rows], "cpopg")
        return pd.DataFrame(rows)
