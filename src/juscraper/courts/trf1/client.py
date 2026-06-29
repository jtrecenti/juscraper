"""Scraper for the Tribunal Regional Federal da 1ª Região (TRF1).

Wraps the PJe public-consultation system at
``pje1g-consultapublica.trf1.jus.br/consultapublica/``. The form layout
mirrors TRF3 (autocomplete ``classeJudicial`` + ``dataAutuacaoDecoration``
block), so the search payload shape is shared down to the field names; the
divergences live entirely in :data:`BASE_URL`.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from pydantic import ValidationError
from tqdm import tqdm

from ...core.base import BaseScraper
from ...core.exceptions import BotChallengeBlockedError
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
from .schemas import InputCpopgTRF1

logger = logging.getLogger("juscraper.trf1")


class TRF1Scraper(BaseScraper):
    """TRF1 PJe consulta pública (1º grau)."""

    BASE_URL = "https://pje1g-consultapublica.trf1.jus.br/consultapublica/"

    def __init__(
        self,
        verbose: int = 0,
        download_path: str | None = None,
        sleep_time: float = 1.0,
        **kwargs: Any,
    ):
        super().__init__("TRF1")
        self.session = requests.Session()
        self.session.headers.update(BROWSER_HEADERS)
        self.set_verbose(verbose)
        self.set_download_path(download_path)
        self.sleep_time = sleep_time
        self.args = kwargs
        self._field_ids: FormFieldIds | None = None  # cached after first form fetch

    # --- internal helpers -----------------------------------------------

    def _ensure_field_ids(self):
        """Fetch the form once per session and memoize the auto-generated IDs."""
        if self._field_ids is None:
            form_html = fetch_form(self.session)
            self._field_ids = extract_form_field_ids(form_html)
            logger.debug("TRF1 field IDs: %s", self._field_ids)
        return self._field_ids

    def _coerce_id_cnj(self, id_cnj: str | list[str], **kwargs: Any) -> list[str]:
        """Validate via pydantic and return a list of cleaned 20-digit CNJs."""
        try:
            inp = InputCpopgTRF1(id_cnj=id_cnj, **kwargs)
        except ValidationError as exc:
            extras = [err for err in exc.errors() if err["type"] == "extra_forbidden"]
            if extras and len(extras) == len(exc.errors()):
                names = ", ".join(repr(err["loc"][-1]) for err in extras)
                raise TypeError(
                    f"TRF1Scraper.cpopg got unexpected keyword argument(s): {names}"
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
        payload = build_search_payload(format_cnj(id_cnj_clean), ids)
        search_html = submit_search(self.session, payload)
        ca = extract_ca_token(search_html)
        if not ca:
            return None
        detail = fetch_detail(self.session, ca)
        movs_info = extract_movs_pagination(detail)
        if movs_info is not None and movs_info.max_pages > 1:
            extras: list[str] = []
            for page in range(2, movs_info.max_pages + 1):
                extras.append(fetch_movs_page(self.session, movs_info, page, ca))
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
                    fetch_movs_page(self.session, docs_info, page, ca)
                )
                if self.sleep_time:
                    time.sleep(self.sleep_time)
            detail = merge_docs_pages(detail, extras_docs)
        return detail

    # --- public API ------------------------------------------------------

    def cpopg_download(
        self,
        id_cnj: str | list[str],
        **kwargs: Any,
    ) -> list[str | None]:
        """Download the detail HTML for each ``id_cnj``.

        Returns a list aligned with the input order. ``None`` entries indicate
        processes the public consultation could not return — typically sigilo,
        invalid CNJ, ou qualquer erro transiente (rede, payload inesperado do
        PJe, falha de extração de token). Falhas individuais não interrompem o
        batch: o CNJ problemático vira ``None`` e o loop segue para o próximo,
        igual ao padrão do TJSP.
        """
        cnjs = self._coerce_id_cnj(id_cnj, **kwargs)
        results: list[str | None] = []
        for i, cnj in enumerate(tqdm(cnjs, desc="TRF1 cpopg")):
            try:
                results.append(self._fetch_one(cnj))
            except BotChallengeBlockedError:
                raise  # session-wide; nenhum item do batch passaria
            except Exception as exc:  # noqa: BLE001 — resiliência por item
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
        "looked up but missing" from "never tried". Um HTML que sobreviveu ao
        download mas falhou no parse vira o mesmo formato (linha só com
        ``id_cnj``) e o batch continua — assim um erro pontual não derruba
        a coleta inteira.
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
                continue
            try:
                record = parse_detail(html)
            except BotChallengeBlockedError:
                raise  # session-wide; nenhum item do batch passaria
            except Exception as exc:  # noqa: BLE001 — resiliência por item
                logger.warning("Erro ao parsear detalhe de %s: %s", cnj, exc)
                rows.append({"id_cnj": cnj})
                continue
            record["id_cnj"] = cnj
            rows.append(record)
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
            ``jurisdicao``, ``polo_ativo``, ``polo_passivo``, ``movimentacoes``,
            ``documentos`` (metadados). Quando ``download_pecas=True``, ganha
            ainda a coluna ``pecas`` com a lista de caminhos salvos.

        Raises:
            TypeError: Kwarg desconhecido.
            BotChallengeBlockedError: Akamai bloqueou o IP (HTTP 403 "Access
                Denied"). Aguarde alguns minutos ou troque de IP.
        """
        cnjs = self._coerce_id_cnj(
            id_cnj,
            download_pecas=download_pecas,
            diretorio=diretorio,
            **kwargs,
        )
        htmls = self.cpopg_download(id_cnj, **kwargs)
        pecas_paths: list[list[str]] | None = None
        if download_pecas:
            base_dir = diretorio if diretorio is not None else self.download_path
            Path(base_dir).mkdir(parents=True, exist_ok=True)
            pecas_paths = self._download_pecas(htmls, cnjs, base_dir)
        df = self.cpopg_parse(htmls, cnjs)
        if pecas_paths is not None:
            df["pecas"] = pecas_paths
        return df

    def _download_pecas(
        self,
        htmls: list[str | None],
        cnjs: list[str],
        base_dir: str,
    ) -> list[list[str]]:
        """Baixa as peças de cada detalhe HTML usando a sessão atual.

        Cada peça vira ``<base_dir>/<cnj>/<id_processo_doc>.html``. Erros por
        peça viram warning e seguem; um :class:`BotChallengeBlockedError`
        propaga (session-wide).
        """
        results: list[list[str]] = []
        for i, (cnj, html) in enumerate(zip(cnjs, htmls, strict=False)):
            if html is None:
                results.append([])
                continue
            urls = extract_documento_urls(html)
            proc_dir = str(Path(base_dir) / cnj)
            Path(proc_dir).mkdir(parents=True, exist_ok=True)
            paths: list[str] = []
            for ca, doc_id in urls:
                try:
                    content = fetch_documento(self.session, ca, doc_id)
                except BotChallengeBlockedError:
                    raise  # session-wide; nenhum item passaria
                except Exception as exc:  # noqa: BLE001 — resiliência por peça
                    logger.warning(
                        "Erro ao baixar peça %s do %s: %s", doc_id, cnj, exc
                    )
                    continue
                path = str(Path(proc_dir) / f"{doc_id}.html")
                with Path(path).open("wb") as fh:
                    fh.write(content)
                paths.append(path)
                if self.sleep_time:
                    time.sleep(self.sleep_time)
            results.append(paths)
            if i + 1 < len(cnjs) and self.sleep_time:
                time.sleep(self.sleep_time)
        return results
