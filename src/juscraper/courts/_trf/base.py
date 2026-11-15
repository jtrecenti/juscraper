"""Shared scraper base for the TRF PJe ConsultaPública family (TRF1/TRF3/TRF5).

Absorbs the near-identical ``client.py`` modules of the three PJe
ConsultaPública deployments (refs #84, #294). A concrete tribunal is a thin
subclass that sets ``BASE_URL`` + ``TRIBUNAL_NAME`` (and, when a deployment
diverges, the classe form-field shape). Mirrors ``courts/_esaj/base.py``:

* inherits :class:`HTTPScraper` (session + centralized retry/backoff, refs #281);
* the only per-tribunal divergences are class attributes / one hook, never
  ``if tribunal == ...`` in shared code.
"""
# pylint: disable=protected-access
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel, ValidationError
from tqdm import tqdm

from ...core.exceptions import BotChallengeBlockedError
from ...core.failures import (
    COLUNA_MOTIVO_FALHA,
    EXCECOES_DE_FALHA_POR_LINHA,
    MOTIVO_BLOQUEIO_ANTI_BOT,
    MOTIVO_RESPOSTA_INESPERADA,
    avisar_falhas,
    motivo_falha,
)
from ...core.http import HTTPScraper
from ...utils.cnj import clean_cnj, format_cnj
from .download import (
    BROWSER_HEADERS,
    FormFieldIds,
    build_search_payload,
    extract_ca_token,
    extract_docs_pagination,
    extract_documento_urls,
    extract_form_field_ids,
    extract_movs_pagination,
    fetch_detail,
    fetch_documento,
    fetch_form,
    fetch_movs_page,
    merge_docs_pages,
    merge_movs_pages,
    submit_search,
)
from .parse import parse_detail
from .schemas import InputCpopgTRF

logger = logging.getLogger("juscraper._trf")


class TRFConsultaScraper(HTTPScraper):
    """Base scraper for a TRF PJe ConsultaPública (1º grau) deployment.

    Subclasses define the class attributes below; everything else is shared.
    """

    #: Deployment root, ``https://.../consultapublica/`` (trailing slash).
    BASE_URL: str = ""
    #: Short name (``"TRF1"``) — drives logging, tqdm, error messages, bot check.
    TRIBUNAL_NAME: str = ""
    #: Pydantic schema validating ``cpopg`` kwargs (``extra="forbid"``).
    INPUT_CPOPG: type[BaseModel] = InputCpopgTRF
    #: PJe classe form field. Every current deployment uses the ``classeJudicial``
    #: autocomplete; a deployment with another component overrides it.
    CLASSE_FIELD_NAME: str = "classeJudicial"

    def __init__(
        self,
        verbose: int = 0,
        download_path: str | None = None,
        sleep_time: float = 1.0,
        **kwargs: Any,
    ):
        super().__init__(
            self.TRIBUNAL_NAME,
            verbose=verbose,
            download_path=download_path,
            sleep_time=sleep_time,
            **kwargs,
        )
        self._field_ids: FormFieldIds | None = None  # cached after first form fetch

    def _configure_session(self, session) -> None:
        """Send a browser-realistic header set (overrides the juscraper UA).

        TRF3 sits behind an Akamai bot manager that stalls on stripped
        requests; the Chrome-flavoured headers prime the session predictably.
        Mirrors how TJCE customizes its session in the eSAJ family.
        """
        session.headers.update(BROWSER_HEADERS)

    # --- per-tribunal hook ----------------------------------------------

    def _classe_payload_fields(self, field_ids: FormFieldIds) -> dict[str, str]:
        """Build the classe (+ date) slice of the search payload.

        Default = TRF1/TRF3 shape: the ``classeJudicial`` autocomplete (with its
        paired ``sgbClasseJudicial_selection``) plus the ``dataAutuacaoDecoration``
        date block. A deployment with another classe component overrides this.
        """
        return {
            f"fPP:{field_ids.classe}:classeJudicial": "",
            f"fPP:{field_ids.classe}:sgbClasseJudicial_selection": "",
            "fPP:dataAutuacaoDecoration:dataAutuacaoInicioInputDate": "",
            "fPP:dataAutuacaoDecoration:dataAutuacaoFimInputDate": "",
        }

    # --- internal helpers -----------------------------------------------

    def _ensure_field_ids(self) -> FormFieldIds:
        """Fetch the form once per session and memoize the auto-generated IDs."""
        if self._field_ids is None:
            form_html = fetch_form(self, self.BASE_URL)
            self._field_ids = extract_form_field_ids(form_html, self.CLASSE_FIELD_NAME, self.TRIBUNAL_NAME)
            logger.debug("%s field IDs: %s", self.TRIBUNAL_NAME, self._field_ids)
        return self._field_ids

    def _coerce_id_cnj(self, id_cnj: str | list[str], **kwargs: Any) -> list[str]:
        """Validate via pydantic and return a list of cleaned 20-digit CNJs."""
        try:
            inp = self.INPUT_CPOPG(id_cnj=id_cnj, **kwargs)
        except ValidationError as exc:
            extras = [err for err in exc.errors() if err["type"] == "extra_forbidden"]
            if extras and len(extras) == len(exc.errors()):
                names = ", ".join(repr(err["loc"][-1]) for err in extras)
                raise TypeError(
                    f"{type(self).__name__}.cpopg got unexpected keyword argument(s): {names}"
                ) from exc
            raise
        raw = inp.id_cnj if isinstance(inp.id_cnj, list) else [inp.id_cnj]
        return [clean_cnj(c) for c in raw]

    def _fetch_one(self, id_cnj_clean: str) -> str | None:
        """Run the search/detail flow for a single CNJ.

        Returns the detail HTML with all movimentação pages spliced in, or
        ``None`` when the public consultation has nothing for the CNJ. PJe
        renders the movs table 15 rows at a time behind a Richfaces slider,
        so processes with > 15 movs need additional POSTs to surface the
        remaining pages.
        """
        ids = self._ensure_field_ids()
        classe_fields = self._classe_payload_fields(ids)
        payload = build_search_payload(format_cnj(id_cnj_clean), ids, classe_fields)
        search_html = submit_search(self, self.BASE_URL, payload)
        ca = extract_ca_token(search_html)
        if not ca:
            return None
        detail = fetch_detail(self, self.BASE_URL, ca)
        movs_info = extract_movs_pagination(detail)
        if movs_info is not None and movs_info.max_pages > 1:
            extras: list[str] = []
            for page in range(2, movs_info.max_pages + 1):
                extras.append(fetch_movs_page(self, self.BASE_URL, movs_info, page, ca))
                if self.sleep_time:
                    time.sleep(self.sleep_time)
            detail = merge_movs_pages(detail, extras)
        docs_info = extract_docs_pagination(detail)
        if docs_info is not None and docs_info.max_pages > 1:
            extras_docs: list[str] = []
            for page in range(2, docs_info.max_pages + 1):
                # Re-use fetch_movs_page — POST shape is identical, only the
                # IDs (container/source/slider) come from docs_info.
                extras_docs.append(
                    fetch_movs_page(self, self.BASE_URL, docs_info, page, ca)
                )
                if self.sleep_time:
                    time.sleep(self.sleep_time)
            detail = merge_docs_pages(detail, extras_docs)
        return detail

    def _baixar(self, cnjs: list[str]) -> tuple[list[str | None], list[str | None]]:
        """Detalhe HTML e motivo de falha de cada CNJ, na ordem da entrada.

        Um CNJ que falha vira ``None`` com o motivo, e o lote segue. O
        bloqueio anti-bot vale para a sessão inteira: ele encerra o lote, e o
        CNJ bloqueado e os seguintes saem com ``bloqueio_anti_bot`` sem novos
        pedidos. Processo ausente da consulta pública sai ``None`` sem motivo.
        ``ImportError`` (extra ``juscraper[waf]`` ausente) propaga.
        """
        htmls: list[str | None] = []
        motivos: list[str | None] = []
        for i, cnj in enumerate(tqdm(cnjs, desc=f"{self.TRIBUNAL_NAME} cpopg")):
            html: str | None = None
            motivo: str | None = None
            try:
                html = self._fetch_one(cnj)
            except BotChallengeBlockedError as exc:
                logger.warning("%s: bloqueio anti-bot em %s; o lote para aqui: %s", self.TRIBUNAL_NAME, cnj, exc)
                restantes = len(cnjs) - i
                htmls.extend([None] * restantes)
                motivos.extend([MOTIVO_BLOQUEIO_ANTI_BOT] * restantes)
                break
            except ImportError:
                raise
            except Exception as exc:  # noqa: BLE001 — resiliência por item
                logger.warning("Erro ao consultar %s: %s", cnj, exc)
                no_vocabulario = isinstance(exc, EXCECOES_DE_FALHA_POR_LINHA)
                motivo = motivo_falha(exc) if no_vocabulario else MOTIVO_RESPOSTA_INESPERADA
            htmls.append(html)
            motivos.append(motivo)
            if i + 1 < len(cnjs) and self.sleep_time:
                time.sleep(self.sleep_time)
        return htmls, motivos

    def _linhas(
        self,
        htmls: list[str | None],
        cnjs: list[str],
        motivos: list[str | None],
    ) -> list[dict[str, Any]]:
        """Uma linha por CNJ, com ``motivo_falha``; HTML que o parser recusa sai ``resposta_inesperada``."""
        rows: list[dict[str, Any]] = []
        for cnj, html, motivo_download in zip(cnjs, htmls, motivos, strict=True):
            record: dict[str, Any] = {}
            motivo = motivo_download
            if html is not None:
                try:
                    record = parse_detail(html)
                except Exception as exc:  # noqa: BLE001 — resiliência por item
                    logger.warning("Erro ao parsear detalhe de %s: %s", cnj, exc)
                    motivo = motivo or MOTIVO_RESPOSTA_INESPERADA
            rows.append({**record, "id_cnj": cnj, COLUNA_MOTIVO_FALHA: motivo})
        return rows

    def _avisar(self, cnjs: list[str], motivos: list[str | None], metodo: str) -> None:
        """Um ``UserWarning`` com os CNJs que falharam, atribuído ao método público ``metodo``."""
        falhas = [f"processo {c}: {m}" for c, m in zip(cnjs, motivos, strict=True) if m]
        avisar_falhas(falhas, f"{self.TRIBUNAL_NAME}Scraper.{metodo}", "consulta(s) de processo")

    # --- public API ------------------------------------------------------

    def cpopg_download(
        self,
        id_cnj: str | list[str],
        **kwargs: Any,
    ) -> list[str | None]:
        """Download the detail HTML for each ``id_cnj``.

        Returns a list aligned with the input order. ``None`` entries indicate
        processes the public consultation could not return — sigilo, CNJ
        inexistente ou falha da requisição. Falhas individuais não
        interrompem o batch; um bloqueio anti-bot encerra o batch e os CNJs
        restantes saem ``None``. As falhas entram num único ``UserWarning``
        ao fim; :meth:`cpopg` traz o motivo de cada uma em ``motivo_falha``.
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
        missing" from "never tried". Um HTML que sobreviveu ao download mas
        falhou no parse vira linha só com ``id_cnj``, com ``UserWarning``, e o
        batch continua. Sem a coluna ``motivo_falha``: um ``None`` vindo de
        :meth:`cpopg_download` pode ser processo ausente ou requisição que
        falhou, e só :meth:`cpopg` sabe qual.
        """
        if len(htmls) != len(id_cnj_list):
            raise ValueError(
                "htmls and id_cnj_list must have the same length "
                f"({len(htmls)} != {len(id_cnj_list)})"
            )
        rows = self._linhas(htmls, id_cnj_list, [None] * len(htmls))
        self._avisar(id_cnj_list, [r.pop(COLUNA_MOTIVO_FALHA) for r in rows], "cpopg_parse")
        return pd.DataFrame(rows)

    def cpopg(
        self,
        id_cnj: str | list[str],
        download_pecas: bool = False,
        diretorio: str | None = None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """Consulta CPOPG: baixa o detalhe, parseia e (opcional) baixa peças.

        Por default retorna apenas os metadados + movimentações + lista de
        documentos (id/data/descrição). Para também baixar os arquivos das
        peças (HTML viewer do PJe), passe ``download_pecas=True`` + um
        ``diretorio``. As peças vão para ``<diretorio>/<cnj>/<id>.html`` e a
        coluna ``pecas`` no DataFrame ganha a lista de caminhos por processo.

        ``download_pecas`` vive como flag aqui (em vez de um
        ``cpopg_download_pecas`` separado) porque os tokens ``ca`` que
        identificam cada peça estão amarrados à conversa Seam que produziu o
        detalhe — peças precisam ser baixadas na mesma ``requests.Session``.
        Manter as duas etapas numa só chamada evita refazer o GET do detalhe
        para cada peça.

        Args:
            id_cnj: CNJ único ou lista.
            download_pecas: Se ``True``, baixa as peças junto. Default ``False``.
            diretorio: Onde gravar as peças. Sobrescreve ``download_path``
                para esta chamada. Quando omitido, usa ``download_path`` (que
                vira um ``tempfile.mkdtemp()`` se nada for passado ao construtor).

        Returns:
            DataFrame com uma linha por CNJ. Colunas: ``id_cnj``, ``processo``,
            ``classe``, ``assunto``, ``data_distribuicao``, ``orgao_julgador``,
            ``jurisdicao``, ``endereco_orgao``, ``polo_ativo``, ``polo_passivo``,
            ``movimentacoes``, ``documentos`` (metadados) e ``motivo_falha``.
            Quando ``download_pecas=True``, ganha ainda a coluna ``pecas`` com
            a lista de caminhos salvos.

            ``motivo_falha`` é ``None`` quando a consulta respondeu, inclusive
            para processo ausente ou sob sigilo (linha só com ``id_cnj``).
            Quando a requisição de um CNJ falha, a linha sai só com ``id_cnj``
            e o motivo, no vocabulário de
            :data:`juscraper.core.failures.MOTIVOS_FALHA`, e o lote segue; o
            HTML fora do formato conhecido sai ``resposta_inesperada``. As
            falhas entram num único ``UserWarning`` ao fim.

            Um bloqueio anti-bot vale para a sessão inteira: o lote para no
            CNJ bloqueado, sem novos pedidos, e ele e os seguintes saem com
            ``bloqueio_anti_bot``. As linhas anteriores são preservadas. Com
            ``download_pecas=True``, o bloqueio, no detalhe ou nas peças,
            também encerra as peças: os processos cujas peças ficaram por
            baixar saem com ``bloqueio_anti_bot``, com o detalhe e as peças já
            salvas. Aguarde alguns minutos ou troque de IP e peça de novo só as
            linhas com ``motivo_falha``.

        Raises:
            TypeError: Kwarg desconhecido.
        """
        cnjs = self._coerce_id_cnj(
            id_cnj,
            download_pecas=download_pecas,
            diretorio=diretorio,
            **kwargs,
        )
        htmls, motivos = self._baixar(cnjs)
        pecas_paths: list[list[str]] | None = None
        if download_pecas:
            base_dir = diretorio if diretorio is not None else self.download_path
            Path(base_dir).mkdir(parents=True, exist_ok=True)
            pecas_paths, motivos = self._download_pecas(htmls, cnjs, base_dir, motivos)
        rows = self._linhas(htmls, cnjs, motivos)
        self._avisar(cnjs, [r[COLUNA_MOTIVO_FALHA] for r in rows], "cpopg")
        df = pd.DataFrame(rows)
        if pecas_paths is not None:
            df["pecas"] = pecas_paths
        return df

    def _download_pecas(
        self,
        htmls: list[str | None],
        cnjs: list[str],
        base_dir: str,
        motivos: list[str | None],
    ) -> tuple[list[list[str]], list[str | None]]:
        """Baixa as peças de cada detalhe HTML usando a sessão atual.

        Cada peça vira ``<base_dir>/<cnj>/<id_processo_doc>.html``. Erros por
        peça viram warning e seguem. Um :class:`BotChallengeBlockedError` vale
        para a sessão inteira: as peças param ali, e nada é pedido se o
        detalhe já foi bloqueado.

        Returns:
            Os caminhos salvos por processo e ``motivos`` com
            ``bloqueio_anti_bot`` nos processos com detalhe cujas peças o
            bloqueio impediu.
        """
        results: list[list[str]] = []
        novos = list(motivos)
        bloqueado = MOTIVO_BLOQUEIO_ANTI_BOT in motivos
        for i, (cnj, html) in enumerate(zip(cnjs, htmls, strict=True)):
            paths: list[str] = []
            if html is not None and not bloqueado:
                paths, bloqueado = self._pecas_do_processo(cnj, html, base_dir)
                if not bloqueado and i + 1 < len(cnjs) and self.sleep_time:
                    time.sleep(self.sleep_time)
            if html is not None and bloqueado:
                novos[i] = MOTIVO_BLOQUEIO_ANTI_BOT
            results.append(paths)
        return results, novos

    def _pecas_do_processo(self, cnj: str, html: str, base_dir: str) -> tuple[list[str], bool]:
        """Caminhos das peças salvas de um processo e se o download parou num bloqueio anti-bot."""
        proc_dir = Path(base_dir) / cnj
        proc_dir.mkdir(parents=True, exist_ok=True)
        paths: list[str] = []
        for ca, doc_id in extract_documento_urls(html):
            try:
                content = fetch_documento(self, self.BASE_URL, ca, doc_id)
            except BotChallengeBlockedError as exc:
                logger.warning(
                    "%s: bloqueio anti-bot na peça %s do %s; as peças param aqui: %s",
                    self.TRIBUNAL_NAME, doc_id, cnj, exc,
                )
                return paths, True
            except ImportError:
                raise
            except Exception as exc:  # noqa: BLE001 — resiliência por peça
                logger.warning("Erro ao baixar peça %s do %s: %s", doc_id, cnj, exc)
                continue
            path = proc_dir / f"{doc_id}.html"
            path.write_bytes(content)
            paths.append(str(path))
            if self.sleep_time:
                time.sleep(self.sleep_time)
        return paths, False
