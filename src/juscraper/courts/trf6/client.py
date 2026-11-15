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
import numbers
from typing import Any, NamedTuple

import pandas as pd
import requests
from pydantic import ValidationError
from tqdm import tqdm

from ...core.avisos import avisar
from ...core.base import BaseScraper
from ...core.failures import (
    COLUNA_MOTIVO_FALHA,
    MOTIVO_CAPTCHA_ESGOTADO,
    avisar_falhas_de_processos,
    consultar_em_lote,
    consultar_processo,
    exemplos_do_aviso,
    linhas_de_processos,
)
from ...utils.cnj import clean_cnj, format_cnj
from .download import HEADERS, fetch_detail
from .parse import COLUNAS_DETALHE, parse_detail
from .schemas import InputCpopgTRF6

logger = logging.getLogger("juscraper.trf6")


def _detalhe_em_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """DataFrame das linhas, com as colunas de :data:`COLUNAS_DETALHE` em ``None`` onde faltam.

    A linha não lida traz só ``id_cnj`` (e ``motivo_falha``); sem o preenchimento,
    um lote sem nenhuma linha lida sairia sem as colunas do detalhe.
    """
    return pd.DataFrame([{**dict.fromkeys(COLUNAS_DETALHE), **row} for row in rows])


class _Consulta(NamedTuple):
    """Resultado da consulta de um CNJ."""

    html: str | None
    motivo: str | None


def _exigir_inteiro_positivo(nome: str, valor: object, *, aceita_none: bool = False) -> None:
    """Levanta ``TypeError`` se ``valor`` não é inteiro (``bool`` não conta) e ``ValueError`` se é menor que 1.

    Aceita inteiros do numpy, como ``RequestPolicy.max_retries``.
    """
    if aceita_none and valor is None:
        return
    esperado = f"{nome} deve ser {'None ou ' if aceita_none else ''}um inteiro maior que zero, não {valor!r}."
    if isinstance(valor, bool) or not isinstance(valor, numbers.Integral):
        raise TypeError(esperado)
    if valor < 1:
        raise ValueError(esperado)


class TRF6Scraper(BaseScraper):
    """TRF6 eproc consulta pública (1º grau)."""

    BASE_URL = "https://eproc1g.trf6.jus.br/eproc/"

    def __init__(
        self,
        verbose: int = 0,
        download_path: str | None = None,
        sleep_time: float = 1.0,
        max_captcha_attempts: int = 3,
        max_captcha_esgotado_seguidos: int | None = 3,
        **kwargs: Any,
    ):
        """Configura a sessão da consulta pública.

        Args:
            verbose: Nível de log.
            download_path: Diretório de downloads.
            sleep_time: Pausa entre CNJs, em segundos.
            max_captcha_attempts: Captchas tentados por CNJ antes de ele sair
                com ``captcha_esgotado``.
            max_captcha_esgotado_seguidos: CNJs seguidos com
                ``captcha_esgotado`` que encerram o lote: o resolvedor está
                errando sempre, e os CNJs restantes saem com o mesmo motivo,
                sem nova consulta. ``None`` não encerra.
            **kwargs: Guardados em ``self.args``.

        Raises:
            TypeError: ``max_captcha_attempts`` ou ``max_captcha_esgotado_seguidos``
                não é ``int`` (nem ``None``, no segundo).
            ValueError: Um dos dois é menor que 1.
        """
        _exigir_inteiro_positivo("max_captcha_attempts", max_captcha_attempts)
        _exigir_inteiro_positivo("max_captcha_esgotado_seguidos", max_captcha_esgotado_seguidos, aceita_none=True)
        super().__init__("TRF6")
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.set_verbose(verbose)
        self.set_download_path(download_path)
        self.sleep_time = sleep_time
        self.max_captcha_attempts = max_captcha_attempts
        self.max_captcha_esgotado_seguidos = max_captcha_esgotado_seguidos
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
        return consultar_em_lote(
            tqdm(cnjs, desc="TRF6 cpopg"),
            self._consultar,
            lambda motivo: _Consulta(None, motivo),
            sleep_time=self.sleep_time,
            encerrar=self._captcha_errando_sempre,
        )

    def _captcha_errando_sempre(self, consultas: list[_Consulta]) -> bool:
        """Se as últimas ``max_captcha_esgotado_seguidos`` consultas esgotaram o captcha."""
        limite = self.max_captcha_esgotado_seguidos
        if limite is None or len(consultas) < limite:
            return False
        if any(c.motivo != MOTIVO_CAPTCHA_ESGOTADO for c in consultas[-limite:]):
            return False
        logger.warning(
            "TRF6: captcha recusado em %d CNJs seguidos; os CNJs restantes, se houver, saem captcha_esgotado "
            "sem consulta.",
            limite,
        )
        return True

    def _consultar(self, cnj: str) -> _Consulta:
        """A consulta de um CNJ; a falha vem no motivo, e não como exceção."""
        return _Consulta(*consultar_processo(self._fetch_one, cnj, tribunal="TRF6", logger=logger))

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
        interrompem o lote; um bloqueio anti-bot, ou o captcha esgotado em
        ``max_captcha_esgotado_seguidos`` CNJs seguidos, encerra o lote, e os
        CNJs restantes saem ``None``. As falhas entram num único ``UserWarning``
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
        só com ``id_cnj`` preenchido, com ``UserWarning``, e o lote continua.
        As colunas do detalhe existem mesmo quando nenhum HTML foi lido. Sem a
        coluna ``motivo_falha``: um ``None`` vindo de :meth:`cpopg_download`
        pode ser processo ausente ou consulta que falhou, e só :meth:`cpopg`
        sabe qual.
        """
        if len(htmls) != len(id_cnj_list):
            raise ValueError(
                "htmls and id_cnj_list must have the same length "
                f"({len(htmls)} != {len(id_cnj_list)})"
            )
        rows = linhas_de_processos(id_cnj_list, htmls, [None] * len(htmls), parse=parse_detail, logger=logger)
        self._avisar(id_cnj_list, [r.pop(COLUNA_MOTIVO_FALHA) for r in rows], "cpopg_parse")
        _avisar_sem_polos(rows, "cpopg_parse")
        return _detalhe_em_dataframe(rows)

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
        ``movimentacoes`` and ``motivo_falha``. As colunas do detalhe existem
        mesmo quando nenhum CNJ do lote foi lido, com ``None`` nas linhas não
        lidas.

        ``motivo_falha`` é ``None`` quando a consulta respondeu, inclusive
        para processo ausente ou sob sigilo (linha só com ``id_cnj``
        preenchido). Quando a consulta de um CNJ falha, a linha sai só com
        ``id_cnj`` e o motivo preenchidos, no vocabulário de
        :data:`juscraper.core.failures.MOTIVOS_FALHA` (``http_<status>``,
        ``timeout``, ``conexao``; ``captcha_esgotado`` para captcha recusado
        nas ``max_captcha_attempts`` tentativas; ``resposta_inesperada`` para
        formulário sem captcha, HTML que o parser recusa ou outro erro), e o
        lote segue. Um desafio anti-bot vale para a sessão inteira: o lote
        para no CNJ desafiado, sem novos pedidos, e ele e os seguintes saem
        com ``bloqueio_anti_bot``. Do mesmo modo, depois de
        ``max_captcha_esgotado_seguidos`` CNJs seguidos com
        ``captcha_esgotado`` (default 3), o resolvedor está errando sempre: o
        lote para, e os CNJs seguintes saem com ``captcha_esgotado`` sem nova
        consulta. As falhas entram num único
        ``UserWarning`` ao fim
        (:class:`~juscraper.core.exceptions.BloqueioAntiBotWarning` quando
        há bloqueio anti-bot).
        """
        cnjs = self._coerce_id_cnj(id_cnj, **kwargs)
        consultas = self._baixar(cnjs)
        htmls = [c.html for c in consultas]
        motivos = [c.motivo for c in consultas]
        rows = linhas_de_processos(cnjs, htmls, motivos, parse=parse_detail, logger=logger)
        self._avisar(cnjs, [r[COLUNA_MOTIVO_FALHA] for r in rows], "cpopg")
        _avisar_sem_polos(rows, "cpopg")
        return _detalhe_em_dataframe(rows)


def _avisar_sem_polos(rows: list[dict[str, Any]], metodo: str) -> None:
    """Um ``UserWarning`` com os processos lidos cuja tabela de partes não deu polo ativo nem passivo."""
    processos = [r["id_cnj"] for r in rows if "processo" in r and not (r["polo_ativo"] or r["polo_passivo"])]
    if processos:
        exemplos = ", ".join(exemplos_do_aviso(processos))
        avisar(
            f"TRF6Scraper.{metodo}: {len(processos)} processo(s) sem polo ativo nem passivo ({exemplos}). "
            "A tabela de partes não traz a faixa dos polos nem os rótulos AUTOR/RÉU; polo_ativo e "
            "polo_passivo saem vazios."
        )
