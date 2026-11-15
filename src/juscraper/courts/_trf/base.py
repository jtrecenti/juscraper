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
from typing import Any, NamedTuple

import pandas as pd
from pydantic import BaseModel, ValidationError
from tqdm import tqdm

from ...core.exceptions import BotChallengeBlockedError
from ...core.failures import (
    COLUNA_MOTIVO_FALHA,
    MOTIVO_BLOQUEIO_ANTI_BOT,
    avisar_falhas,
    avisar_falhas_de_processos,
    consultar_em_lote,
    consultar_processo,
    linhas_de_processos,
    motivo_falha_ou_inesperada,
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
from .parse import COLUNAS_DETALHE, parse_detail
from .schemas import InputCpopgTRF

logger = logging.getLogger("juscraper._trf")


class _Consulta(NamedTuple):
    """Resultado da consulta de um CNJ (peças só com ``download_pecas``)."""

    html: str | None
    motivo: str | None
    pecas: list[str]
    pecas_falhas: list[dict[str, str]]


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

    def _baixar(self, cnjs: list[str], pecas_dir: str | None = None) -> list[_Consulta]:
        """A consulta de cada CNJ, na ordem da entrada.

        Com ``pecas_dir``, as peças de cada processo são baixadas logo depois
        do seu detalhe, na mesma sessão. Um CNJ que falha sai com ``html``
        ``None`` e o motivo, e o lote segue. O bloqueio anti-bot vale para a sessão
        inteira: ele encerra o lote, e o CNJ bloqueado (no detalhe ou nas
        peças) e os seguintes saem com ``bloqueio_anti_bot`` sem novos
        pedidos; os anteriores ficam com detalhe e peças. Processo ausente da
        consulta pública sai com ``html`` ``None`` sem motivo. Uma peça que falha fora do
        bloqueio vai para a lista de peças que falharam, com o motivo, e as
        demais seguem. ``ImportError`` (extra ``juscraper[waf]`` ausente)
        propaga.
        """
        return consultar_em_lote(
            tqdm(cnjs, desc=f"{self.TRIBUNAL_NAME} cpopg"),
            lambda cnj: self._consultar(cnj, pecas_dir),
            lambda motivo: _Consulta(None, motivo, [], []),
            sleep_time=self.sleep_time,
        )

    def _consultar(self, cnj: str, pecas_dir: str | None) -> _Consulta:
        """A consulta de um CNJ (peças só com ``pecas_dir``)."""
        html, motivo = consultar_processo(self._fetch_one, cnj, tribunal=self.TRIBUNAL_NAME, logger=logger)
        if html is None or pecas_dir is None:
            return _Consulta(html, motivo, [], [])
        return self._pecas_do_processo(cnj, html, pecas_dir)

    def _avisar(self, cnjs: list[str], motivos: list[str | None], metodo: str) -> None:
        """Um ``UserWarning`` com os CNJs que falharam, atribuído ao método público ``metodo``."""
        avisar_falhas_de_processos(cnjs, motivos, f"{self.TRIBUNAL_NAME}Scraper.{metodo}")

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
        missing" from "never tried". Um HTML que sobreviveu ao download mas
        falhou no parse vira linha só com ``id_cnj`` preenchido, com
        ``UserWarning``, e o batch continua. As colunas do detalhe existem
        mesmo quando nenhum HTML foi lido. Sem a coluna ``motivo_falha``: um ``None`` vindo de
        :meth:`cpopg_download` pode ser processo ausente ou requisição que
        falhou, e só :meth:`cpopg` sabe qual.
        """
        if len(htmls) != len(id_cnj_list):
            raise ValueError(
                "htmls and id_cnj_list must have the same length "
                f"({len(htmls)} != {len(id_cnj_list)})"
            )
        rows = linhas_de_processos(id_cnj_list, htmls, [None] * len(htmls), parse=parse_detail, logger=logger)
        self._avisar(id_cnj_list, [r.pop(COLUNA_MOTIVO_FALHA) for r in rows], "cpopg_parse")
        return pd.DataFrame(rows, columns=[*COLUNAS_DETALHE, "id_cnj"])

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
                a lista de caminhos salvos e a coluna ``pecas_falhas`` com as peças
                que não puderam ser baixadas, cada uma como
                ``{"id": <id da peça>, "motivo_falha": <motivo>}``, no mesmo
                vocabulário. A falha de uma peça não afeta ``motivo_falha`` do
                processo nem as outras peças, e as falhas de peça saem num
                ``UserWarning`` próprio ao fim. Num bloqueio anti-bot nas peças,
                a bloqueada e as seguintes, que não são pedidas, entram em
                ``pecas_falhas`` com ``bloqueio_anti_bot``; esse bloqueio sai só
                no aviso dos processos, pelo ``motivo_falha`` da linha.

                ``motivo_falha`` é ``None`` quando a consulta respondeu, inclusive
                para processo ausente ou sob sigilo (linha só com ``id_cnj``
                preenchido). Quando a requisição de um CNJ falha, a linha sai só
                com ``id_cnj`` e o motivo preenchidos, no vocabulário de
                :data:`juscraper.core.failures.MOTIVOS_FALHA`, e o lote segue; o
                HTML fora do formato conhecido sai ``resposta_inesperada``. As
                falhas entram num único ``UserWarning`` ao fim
                (:class:`~juscraper.core.exceptions.BloqueioAntiBotWarning` quando
                há bloqueio anti-bot).

                Um bloqueio anti-bot vale para a sessão inteira: o lote para no
                CNJ bloqueado, sem novos pedidos, e ele e os seguintes saem com
                ``bloqueio_anti_bot``. As linhas anteriores são preservadas. Com
                ``download_pecas=True``, as peças de cada processo são baixadas
                logo depois do seu detalhe: os processos anteriores ao bloqueio
                saem com detalhe e peças, e o bloqueado nas peças sai com
                ``bloqueio_anti_bot``, o detalhe e as peças já salvas. Aguarde
                alguns minutos ou troque de IP e peça de novo só as linhas com
                ``motivo_falha``.

        Raises:
            TypeError: Kwarg desconhecido.
        """
        cnjs = self._coerce_id_cnj(
            id_cnj,
            download_pecas=download_pecas,
            diretorio=diretorio,
            **kwargs,
        )
        pecas_dir: str | None = None
        if download_pecas:
            pecas_dir = diretorio if diretorio is not None else self.download_path
            Path(pecas_dir).mkdir(parents=True, exist_ok=True)
        consultas = self._baixar(cnjs, pecas_dir)
        htmls = [c.html for c in consultas]
        motivos = [c.motivo for c in consultas]
        rows = linhas_de_processos(cnjs, htmls, motivos, parse=parse_detail, logger=logger)
        self._avisar(cnjs, [r[COLUNA_MOTIVO_FALHA] for r in rows], "cpopg")
        df = pd.DataFrame(rows, columns=[*COLUNAS_DETALHE, "id_cnj", COLUNA_MOTIVO_FALHA])
        if download_pecas:
            df["pecas"] = [c.pecas for c in consultas]
            df["pecas_falhas"] = [c.pecas_falhas for c in consultas]
            self._avisar_pecas(cnjs, consultas)
        return df

    def _avisar_pecas(self, cnjs: list[str], consultas: list[_Consulta]) -> None:
        """Um ``UserWarning`` com as peças que falharam fora do bloqueio anti-bot."""
        # O bloqueio já está no aviso dos processos, pelo motivo_falha da linha.
        falhas = [
            f"processo {cnj}, peça {f['id']}: {f[COLUNA_MOTIVO_FALHA]}"
            for cnj, c in zip(cnjs, consultas, strict=True)
            for f in c.pecas_falhas
            if f[COLUNA_MOTIVO_FALHA] != MOTIVO_BLOQUEIO_ANTI_BOT
        ]
        avisar_falhas(
            falhas,
            f"{self.TRIBUNAL_NAME}Scraper.cpopg",
            "download(s) de peça",
            "As peças que faltam estão na coluna pecas_falhas.",
        )

    def _pecas_do_processo(
        self, cnj: str, html: str, base_dir: str
    ) -> _Consulta:
        """A consulta de um processo com as peças; ``bloqueio_anti_bot`` quando o download parou num bloqueio."""
        proc_dir = Path(base_dir) / cnj
        proc_dir.mkdir(parents=True, exist_ok=True)
        paths: list[str] = []
        falhas: list[dict[str, str]] = []
        documentos = extract_documento_urls(html)
        for i, (ca, doc_id) in enumerate(documentos):
            # Pausa também antes da 1ª peça, que vem logo depois do detalhe.
            if self.sleep_time:
                time.sleep(self.sleep_time)
            try:
                content = fetch_documento(self, self.BASE_URL, ca, doc_id)
            except BotChallengeBlockedError as exc:
                logger.warning(
                    "%s: bloqueio anti-bot na peça %s do %s; as peças param aqui: %s",
                    self.TRIBUNAL_NAME, doc_id, cnj, exc,
                )
                # A bloqueada e as seguintes, que não serão pedidas, também faltam.
                falhas.extend({"id": d, COLUNA_MOTIVO_FALHA: MOTIVO_BLOQUEIO_ANTI_BOT} for _, d in documentos[i:])
                return _Consulta(html, MOTIVO_BLOQUEIO_ANTI_BOT, paths, falhas)
            except ImportError:
                raise
            except Exception as exc:  # noqa: BLE001 — resiliência por peça
                logger.warning("Erro ao baixar peça %s do %s: %s", doc_id, cnj, exc)
                falhas.append({"id": doc_id, COLUNA_MOTIVO_FALHA: motivo_falha_ou_inesperada(exc)})
                continue
            path = proc_dir / f"{doc_id}.html"
            path.write_bytes(content)
            paths.append(str(path))
        return _Consulta(html, None, paths, falhas)
