"""Raspador do Tribunal Regional Federal da 3ª Região (TRF3).

Consulta processual pública do PJe do TRF3, pela API JSON que a aplicação
``pje1g-consultapublica.trf3.jus.br`` (1º grau) e
``pje2g-consultapublica.trf3.jus.br`` (2º grau) consome. O endereço JSF antigo
(``pje1g.trf3.jus.br/pje/ConsultaPublica/listView.seam``) passou a redirecionar
para essa aplicação, por isso o TRF3 deixou a família ``_trf``, que segue
servindo TRF1 e TRF5. Detalhes do protocolo em
:mod:`juscraper.courts.trf3.download`.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar

import pandas as pd
from pydantic import BaseModel, ValidationError
from tqdm import tqdm

from ...core.exceptions import BotChallengeBlockedError
from ...core.http import HTTPScraper, RequestPolicy
from ...utils.cnj import clean_cnj, format_cnj
from .download import API_HEADERS, BASE_URL_1G, BASE_URL_2G, baixar_documento, baixar_processo
from .parse import parse_processo
from .schemas import InputCpopgTRF3, InputCposgTRF3

logger = logging.getLogger("juscraper.trf3")

# Parte das requisições fica sem resposta atrás do Akamai até o cliente
# desistir; uma nova tentativa costuma responder em menos de um segundo. Por
# isso o timeout de leitura é curto e timeout e erro de conexão são retentados.
_PERFIS_HTTP: dict[str, RequestPolicy] = {
    "api": RequestPolicy(
        timeout=(10.0, 20.0),
        max_retries=4,
        retry_on_timeout=True,
        retry_on_connection_error=True,
    ),
    "documento": RequestPolicy(
        timeout=(10.0, 60.0),
        max_retries=3,
        retry_on_timeout=True,
        retry_on_connection_error=True,
    ),
}


class TRF3Scraper(HTTPScraper):
    """Consulta pública do PJe do TRF3 (1º e 2º grau).

    Perfis HTTP ajustáveis com ``politica=``: ``"api"`` (busca e detalhe,
    timeout de leitura de 20 s, 4 tentativas) e ``"documento"`` (PDF das
    peças, timeout de leitura de 60 s, 3 tentativas).
    """

    #: Raiz da aplicação de 1º grau, usada pelo ``cpopg``.
    BASE_URL: str = BASE_URL_1G
    #: Raiz da aplicação de 2º grau, usada pelo ``cposg``.
    BASE_URL_2G: str = BASE_URL_2G
    TRIBUNAL_NAME: str = "TRF3"
    INPUT_CPOPG: type[BaseModel] = InputCpopgTRF3
    INPUT_CPOSG: type[BaseModel] = InputCposgTRF3
    perfis_http: ClassVar[Mapping[str, RequestPolicy]] = _PERFIS_HTTP

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

    def _configure_session(self, session) -> None:
        """Usa os cabeçalhos de uma chamada XHR do Chrome no lugar do User-Agent do juscraper."""
        session.headers.update(API_HEADERS)

    # --- internos -------------------------------------------------------

    def _coerce_id_cnj(
        self, schema: type[BaseModel], endpoint: str, id_cnj: str | list[str], **kwargs: Any
    ) -> list[str]:
        """Valida pelo schema e devolve a lista de CNJs com 20 dígitos."""
        try:
            inp = schema(id_cnj=id_cnj, **kwargs)
        except ValidationError as exc:
            extras = [err for err in exc.errors() if err["type"] == "extra_forbidden"]
            if extras and len(extras) == len(exc.errors()):
                names = ", ".join(repr(err["loc"][-1]) for err in extras)
                raise TypeError(
                    f"{type(self).__name__}.{endpoint} got unexpected keyword argument(s): {names}"
                ) from exc
            raise
        raw = inp.id_cnj if isinstance(inp.id_cnj, list) else [inp.id_cnj]
        return [clean_cnj(c) for c in raw]

    def _download(self, cnjs: list[str], base_url: str, endpoint: str) -> list[dict[str, Any] | None]:
        """Baixa os envelopes de cada CNJ, alinhados à ordem de entrada.

        ``None`` marca o CNJ que a busca não achou ou cuja consulta falhou;
        a falha vira aviso no log e o lote segue. Bloqueio do Akamai e
        dependência ausente interrompem o lote, porque nenhum item passaria.
        """
        results: list[dict[str, Any] | None] = []
        for i, cnj in enumerate(tqdm(cnjs, desc=f"{self.TRIBUNAL_NAME} {endpoint}")):
            try:
                results.append(
                    baixar_processo(
                        self._request_with_retry,
                        base_url,
                        format_cnj(cnj),
                        tribunal=self.TRIBUNAL_NAME,
                        sleep_time=self.sleep_time,
                    )
                )
            except (BotChallengeBlockedError, ImportError):
                raise
            except Exception as exc:  # noqa: BLE001 (resiliência por item)
                logger.warning("Erro ao consultar %s: %s", cnj, exc)
                results.append(None)
            if i + 1 < len(cnjs) and self.sleep_time:
                time.sleep(self.sleep_time)
        return results

    def _parse(self, brutos: list[dict[str, Any] | None], id_cnj_list: list[str]) -> pd.DataFrame:
        """Uma linha por CNJ; CNJ sem dados ou com erro de parse vira linha só com ``id_cnj``."""
        if len(brutos) != len(id_cnj_list):
            raise ValueError(
                f"brutos e id_cnj_list precisam ter o mesmo tamanho ({len(brutos)} != {len(id_cnj_list)})"
            )
        rows: list[dict[str, Any]] = []
        for cnj, bruto in zip(id_cnj_list, brutos, strict=True):
            if bruto is None:
                rows.append({"id_cnj": cnj})
                continue
            try:
                record = parse_processo(bruto)
            except Exception as exc:  # noqa: BLE001 (resiliência por item)
                logger.warning("Erro ao parsear %s: %s", cnj, exc)
                rows.append({"id_cnj": cnj})
                continue
            rows.append({"id_cnj": cnj, **record})
        return pd.DataFrame(rows)

    def _consulta(
        self,
        endpoint: str,
        schema: type[BaseModel],
        base_url: str,
        id_cnj: str | list[str],
        download_pecas: bool,
        diretorio: str | None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        cnjs = self._coerce_id_cnj(
            schema, endpoint, id_cnj, download_pecas=download_pecas, diretorio=diretorio, **kwargs
        )
        brutos = self._download(cnjs, base_url, endpoint)
        df = self._parse(brutos, cnjs)
        if download_pecas:
            base_dir = diretorio if diretorio is not None else self.download_path
            Path(base_dir).mkdir(parents=True, exist_ok=True)
            df["pecas"] = self._download_pecas(brutos, cnjs, base_url, base_dir)
        return df

    def _download_pecas(
        self,
        brutos: list[dict[str, Any] | None],
        cnjs: list[str],
        base_url: str,
        base_dir: str,
    ) -> list[list[str]]:
        """Grava o PDF de cada documento em ``<base_dir>/<cnj>/<id do documento>.pdf``.

        Falha numa peça vira aviso no log e as demais seguem; bloqueio do
        Akamai interrompe, porque vale para a sessão inteira.
        """
        results: list[list[str]] = []
        for cnj, bruto in zip(cnjs, brutos, strict=True):
            if bruto is None:
                results.append([])
                continue
            id_processo = bruto["busca"]["idProcesso"]
            ids = [doc["id"] for pagina in bruto.get("documentos") or [] for doc in pagina.get("result") or []]
            proc_dir = Path(base_dir) / cnj
            proc_dir.mkdir(parents=True, exist_ok=True)
            paths: list[str] = []
            for id_documento in ids:
                try:
                    content = baixar_documento(
                        self._request_with_retry, base_url, id_documento, id_processo, tribunal=self.TRIBUNAL_NAME
                    )
                except BotChallengeBlockedError:
                    raise
                except Exception as exc:  # noqa: BLE001 (resiliência por peça)
                    logger.warning("Erro ao baixar peça %s do %s: %s", id_documento, cnj, exc)
                    continue
                path = proc_dir / f"{id_documento}.pdf"
                path.write_bytes(content)
                paths.append(str(path))
                if self.sleep_time:
                    time.sleep(self.sleep_time)
            results.append(paths)
        return results

    # --- API pública ----------------------------------------------------

    def cpopg_download(self, id_cnj: str | list[str], **kwargs: Any) -> list[dict[str, Any] | None]:
        """Baixa os envelopes JSON de 1º grau de cada CNJ, sem parsear.

        Aceita os mesmos argumentos de :meth:`cpopg`, menos o download das
        peças. Devolve uma lista alinhada à entrada: um dicionário por
        processo (chaves ``busca``, ``dados`` e uma por recurso paginado) ou
        ``None`` para o CNJ que a consulta pública não devolveu ou cuja
        consulta falhou.
        """
        cnjs = self._coerce_id_cnj(self.INPUT_CPOPG, "cpopg_download", id_cnj, **kwargs)
        return self._download(cnjs, self.BASE_URL, "cpopg")

    def cpopg_parse(self, brutos: list[dict[str, Any] | None], id_cnj_list: list[str]) -> pd.DataFrame:
        """Transforma a saída de :meth:`cpopg_download` num DataFrame, uma linha por CNJ.

        ``id_cnj_list`` traz os CNJs na mesma ordem de ``brutos``. Entradas
        ``None`` viram linha só com ``id_cnj``.
        """
        return self._parse(brutos, id_cnj_list)

    def cpopg(
        self,
        id_cnj: str | list[str],
        download_pecas: bool = False,
        diretorio: str | None = None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """Consulta processos de 1º grau na consulta pública do PJe do TRF3.

        Args:
            id_cnj: CNJ único ou lista, com ou sem máscara.
            download_pecas: Se ``True``, baixa o PDF de cada documento listado
                no processo. Default ``False``.
            diretorio: Onde gravar as peças, em ``<diretorio>/<cnj>/<id>.pdf``.
                Quando omitido, usa ``download_path`` do construtor.

        Returns:
            DataFrame com uma linha por CNJ e as colunas ``id_cnj``,
            ``processo``, ``classe``, ``assunto``, ``data_distribuicao``
            (``DD/MM/AAAA``), ``orgao_julgador``, ``orgao_julgador_colegiado``,
            ``jurisdicao``, ``endereco_orgao``, ``polo_ativo``,
            ``polo_passivo``, ``outros_interessados``, ``movimentacoes`` e
            ``documentos``. Com ``download_pecas=True``, ganha ``pecas``, a
            lista de caminhos gravados. O CNJ que a consulta pública não
            devolve (inexistente ou em segredo de justiça) vira linha só com
            ``id_cnj``.

        Raises:
            TypeError: Kwarg desconhecido.
            BotChallengeBlockedError: O Akamai bloqueou o IP (HTTP 403
                ``Access Denied``). Aguarde alguns minutos ou troque de IP.

        See also:
            :class:`InputCpopgTRF3`: schema dos argumentos aceitos.
        """
        return self._consulta("cpopg", self.INPUT_CPOPG, self.BASE_URL, id_cnj, download_pecas, diretorio, **kwargs)

    def cposg_download(self, id_cnj: str | list[str], **kwargs: Any) -> list[dict[str, Any] | None]:
        """Baixa os envelopes JSON de 2º grau de cada CNJ, sem parsear.

        Mesmo retorno de :meth:`cpopg_download`, consultando a aplicação de
        2º grau. Os argumentos são os de :meth:`cposg`.
        """
        cnjs = self._coerce_id_cnj(self.INPUT_CPOSG, "cposg_download", id_cnj, **kwargs)
        return self._download(cnjs, self.BASE_URL_2G, "cposg")

    def cposg_parse(self, brutos: list[dict[str, Any] | None], id_cnj_list: list[str]) -> pd.DataFrame:
        """Transforma a saída de :meth:`cposg_download` num DataFrame, uma linha por CNJ."""
        return self._parse(brutos, id_cnj_list)

    def cposg(
        self,
        id_cnj: str | list[str],
        download_pecas: bool = False,
        diretorio: str | None = None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """Consulta processos de 2º grau na consulta pública do PJe do TRF3.

        O CNJ do recurso costuma ser o mesmo do processo de origem; a consulta
        de 2º grau devolve o recurso (apelação, agravo, remessa) que tramita
        no tribunal com esse número.

        Args:
            id_cnj: CNJ único ou lista, com ou sem máscara.
            download_pecas: Se ``True``, baixa o PDF de cada documento listado
                no processo. Default ``False``.
            diretorio: Onde gravar as peças, em ``<diretorio>/<cnj>/<id>.pdf``.
                Quando omitido, usa ``download_path`` do construtor.

        Returns:
            DataFrame com as mesmas colunas de :meth:`cpopg`. No 2º grau,
            ``orgao_julgador_colegiado`` traz a turma.

        Raises:
            TypeError: Kwarg desconhecido.
            BotChallengeBlockedError: O Akamai bloqueou o IP (HTTP 403
                ``Access Denied``). Aguarde alguns minutos ou troque de IP.

        See also:
            :class:`InputCposgTRF3`: schema dos argumentos aceitos.
        """
        return self._consulta("cposg", self.INPUT_CPOSG, self.BASE_URL_2G, id_cnj, download_pecas, diretorio, **kwargs)
