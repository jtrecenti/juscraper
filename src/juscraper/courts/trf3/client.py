"""Raspador do Tribunal Regional Federal da 3ª Região (TRF3).

Consulta processual pública do PJe do TRF3, pela API JSON que a aplicação
``pje1g-consultapublica.trf3.jus.br`` (1º grau) e
``pje2g-consultapublica.trf3.jus.br`` (2º grau) consome. O endereço JSF antigo
(``pje1g.trf3.jus.br/pje/ConsultaPublica/listView.seam``) passou a redirecionar
para essa aplicação, por isso o TRF3 deixou a família ``_trf``, que segue
servindo TRF1 e TRF5. Detalhes do protocolo em
:mod:`juscraper.courts.trf3.download`.

``cjsg`` pesquisa jurisprudência em ``web.trf3.jus.br/jurisprudencia``, uma
aplicação ASP.NET separada do PJe, também atrás do Akamai. Não usa a sessão
da consulta processual: cada busca abre a sua ``requests.Session`` com
cabeçalhos próprios. Do raspador usa o retry de ``HTTPScraper``, o
``sleep_time`` do construtor e o perfil HTTP ``perfis_http["cjsg"]``. O código
fica em :mod:`.cjsg_download`, :mod:`.cjsg_parse` e :mod:`.cjsg_schemas`.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar, NamedTuple

import pandas as pd
import requests
from pydantic import ValidationError
from tqdm import tqdm

from ...core.exceptions import BotChallengeBlockedError
from ...core.failures import (
    COLUNA_MOTIVO_FALHA,
    MOTIVO_BLOQUEIO_ANTI_BOT,
    MOTIVO_RESPOSTA_INESPERADA,
    avisar_falhas,
    avisar_falhas_de_processos,
    consultar_em_lote,
    consultar_processo,
    linhas_de_processos,
    motivo_falha_ou_inesperada,
)
from ...core.http import HTTPScraper, RequestPolicy
from ...schemas import CnjInputBase
from ...utils.cnj import clean_cnj, format_cnj
from ...utils.params import apply_input_pipeline_search, raise_on_extra_kwargs, resolve_deprecated_alias
from .cjsg_download import PERFIL_CJSG, build_cjsg_session, cjsg_download_manager
from .cjsg_parse import cjsg_parse_manager
from .cjsg_schemas import InputCJSGTRF3, validar_combinacoes
from .download import API_HEADERS, BASE_URL_1G, BASE_URL_2G, baixar_documento, baixar_processo, token_valido
from .parse import _itens, parse_processo
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
    # Busca de jurisprudência: parte das requisições ao portal também fica
    # pendurada atrás do Akamai; o timeout curto com nova tentativa recupera
    # esses casos em segundos.
    PERFIL_CJSG: RequestPolicy(
        timeout=(10, 60),
        max_retries=4,
        retry_on_timeout=True,
        retry_on_connection_error=True,
    ),
}


class _Consulta(NamedTuple):
    """Resultado da consulta de um CNJ (peças só com ``download_pecas``)."""

    bruto: dict[str, Any] | None
    motivo: str | None
    pecas: list[str]
    pecas_falhas: list[dict[str, Any]]


def _id_documento(doc: object) -> object:
    """O ``id`` de um item de ``documentos``, sem validar; ``None`` fora de dicionário."""
    return doc.get("id") if isinstance(doc, dict) else None


class TRF3Scraper(HTTPScraper):
    """Raspador do TRF3: consulta pública do PJe (1º e 2º grau) e jurisprudência.

    ``cpopg`` e ``cposg`` consultam a API JSON da consulta pública do PJe.
    ``cjsg`` pesquisa ``web.trf3.jus.br/jurisprudencia``, sistema separado com
    sessão própria.

    Perfis HTTP ajustáveis com ``politica=``: ``"api"`` (busca e detalhe,
    timeout de leitura de 20 s, 4 tentativas), ``"documento"`` (PDF das
    peças, timeout de leitura de 60 s, 3 tentativas) e ``"cjsg"`` (busca de
    jurisprudência, timeout de leitura de 60 s, 4 tentativas).
    """

    #: Raiz da aplicação de 1º grau, usada pelo ``cpopg``.
    BASE_URL: str = BASE_URL_1G
    #: Raiz da aplicação de 2º grau, usada pelo ``cposg``.
    BASE_URL_2G: str = BASE_URL_2G
    TRIBUNAL_NAME: str = "TRF3"
    INPUT_CPOPG: type[CnjInputBase] = InputCpopgTRF3
    INPUT_CPOSG: type[CnjInputBase] = InputCposgTRF3
    perfis_http: ClassVar[Mapping[str, RequestPolicy]] = _PERFIS_HTTP

    def __init__(
        self,
        verbose: int = 0,
        download_path: str | None = None,
        sleep_time: float = 1.0,
        **kwargs: Any,
    ) -> None:
        """Cria o raspador; ``kwargs`` seguem para :class:`HTTPScraper` (``politica=``, por exemplo)."""
        super().__init__(
            self.TRIBUNAL_NAME,
            verbose=verbose,
            download_path=download_path,
            sleep_time=sleep_time,
            **kwargs,
        )

    def _configure_session(self, session: requests.Session) -> None:
        """Usa os cabeçalhos de uma chamada XHR do Chrome no lugar do User-Agent do juscraper."""
        session.headers.update(API_HEADERS)

    # --- internos -------------------------------------------------------

    def _coerce_id_cnj(
        self, schema: type[CnjInputBase], endpoint: str, id_cnj: str | list[str], **kwargs: Any
    ) -> list[str]:
        """Valida pelo schema e devolve a lista de CNJs com 20 dígitos."""
        try:
            inp = schema(id_cnj=id_cnj, **kwargs)
        except ValidationError as exc:
            raise_on_extra_kwargs(exc, f"{type(self).__name__}.{endpoint}", schema_cls=schema)
            raise
        raw = inp.id_cnj if isinstance(inp.id_cnj, list) else [inp.id_cnj]
        return [clean_cnj(c) for c in raw]

    def _baixar(
        self, cnjs: list[str], base_url: str, endpoint: str, pecas_dir: str | None = None
    ) -> list[_Consulta]:
        """A consulta de cada CNJ, na ordem da entrada.

        Com ``pecas_dir``, as peças de cada processo são baixadas logo depois
        dos seus envelopes. Um CNJ que falha sai com ``bruto`` ``None`` e o
        motivo, e o lote segue. O bloqueio anti-bot vale para a sessão inteira:
        ele encerra o lote, e o CNJ bloqueado (nos envelopes ou nas peças) e os
        seguintes saem com ``bloqueio_anti_bot`` sem novos pedidos. Processo
        que a busca não acha sai com ``bruto`` ``None`` sem motivo.
        ``ImportError`` propaga.
        """
        return consultar_em_lote(
            tqdm(cnjs, desc=f"{self.TRIBUNAL_NAME} {endpoint}"),
            lambda cnj: self._consultar(cnj, base_url, pecas_dir),
            lambda motivo: _Consulta(None, motivo, [], []),
            sleep_time=self.sleep_time,
        )

    def _consultar(self, cnj: str, base_url: str, pecas_dir: str | None) -> _Consulta:
        """A consulta de um CNJ (peças só com ``pecas_dir``)."""
        bruto, motivo = consultar_processo(
            lambda c: baixar_processo(self._request_with_retry, base_url, format_cnj(c), sleep_time=self.sleep_time),
            cnj,
            tribunal=self.TRIBUNAL_NAME,
            logger=logger,
        )
        if bruto is None or pecas_dir is None:
            return _Consulta(bruto, motivo, [], [])
        return self._pecas_do_processo(cnj, bruto, base_url, pecas_dir)

    def _linhas(
        self, brutos: list[dict[str, Any] | None], id_cnj_list: list[str], motivos: list[str | None]
    ) -> list[dict[str, Any]]:
        """Uma linha por CNJ, com ``id_cnj`` primeiro e ``motivo_falha`` por último.

        Bruto ``None`` ou recusado pelo parser vira linha só com ``id_cnj``; o
        recusado ganha ``resposta_inesperada`` quando não trazia motivo.
        """
        if len(brutos) != len(id_cnj_list):
            raise ValueError(
                f"brutos e id_cnj_list precisam ter o mesmo tamanho ({len(brutos)} != {len(id_cnj_list)})"
            )
        # O HTML do portal JSF antigo (o que ``cpopg_download`` devolvia antes
        # da API) viraria linha só com ``id_cnj``. Recusar a entrada inteira
        # deixa a migração explícita.
        invalidos = sorted({type(b).__name__ for b in brutos if b is not None and not isinstance(b, dict)})
        if invalidos:
            raise TypeError(
                f"{self.TRIBUNAL_NAME}: os brutos agora são os dicionários com os envelopes JSON da API que "
                f"cpopg_download/cposg_download devolvem, não o HTML do portal antigo (recebido: "
                f"{', '.join(invalidos)}). Baixe de novo com cpopg_download ou cposg_download."
            )
        rows = linhas_de_processos(id_cnj_list, brutos, motivos, parse=parse_processo, logger=logger)
        return [{"id_cnj": row["id_cnj"], **row} for row in rows]

    def _avisar(self, cnjs: list[str], motivos: list[str | None], metodo: str) -> None:
        """Um ``UserWarning`` com os CNJs que falharam, atribuído ao método público ``metodo``."""
        avisar_falhas_de_processos(cnjs, motivos, f"{type(self).__name__}.{metodo}")

    def _parse(self, brutos: list[dict[str, Any] | None], id_cnj_list: list[str], metodo: str) -> pd.DataFrame:
        """DataFrame do fluxo em duas etapas, sem a coluna ``motivo_falha``.

        Um ``None`` vindo do download pode ser processo ausente ou consulta que
        falhou, e só :meth:`cpopg`/:meth:`cposg` sabem qual. O bruto que o
        parser recusa entra no aviso.
        """
        rows = self._linhas(brutos, id_cnj_list, [None] * len(brutos))
        self._avisar(id_cnj_list, [row.pop(COLUNA_MOTIVO_FALHA) for row in rows], metodo)
        return pd.DataFrame(rows)

    def _download(
        self, endpoint: str, metodo: str, id_cnj: str | list[str], **kwargs: Any
    ) -> list[dict[str, Any] | None]:
        """Os brutos de ``cpopg_download``/``cposg_download``, com as falhas num aviso."""
        schema, base_url = self._alvo(endpoint)
        cnjs = self._coerce_id_cnj(schema, metodo, id_cnj, **kwargs)
        consultas = self._baixar(cnjs, base_url, endpoint)
        self._avisar(cnjs, [c.motivo for c in consultas], metodo)
        return [c.bruto for c in consultas]

    def _alvo(self, endpoint: str) -> tuple[type[CnjInputBase], str]:
        """Schema de entrada e raiz da aplicação que atendem ``cpopg`` ou ``cposg``."""
        if endpoint == "cposg":
            return self.INPUT_CPOSG, self.BASE_URL_2G
        return self.INPUT_CPOPG, self.BASE_URL

    def _consulta(
        self,
        endpoint: str,
        id_cnj: str | list[str],
        *,
        download_pecas: bool,
        diretorio: str | None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        schema, base_url = self._alvo(endpoint)
        cnjs = self._coerce_id_cnj(
            schema, endpoint, id_cnj, download_pecas=download_pecas, diretorio=diretorio, **kwargs
        )
        pecas_dir: str | None = None
        if download_pecas:
            pecas_dir = diretorio if diretorio is not None else self.download_path
            Path(pecas_dir).mkdir(parents=True, exist_ok=True)
        consultas = self._baixar(cnjs, base_url, endpoint, pecas_dir)
        rows = self._linhas([c.bruto for c in consultas], cnjs, [c.motivo for c in consultas])
        self._avisar(cnjs, [row[COLUNA_MOTIVO_FALHA] for row in rows], endpoint)
        df = pd.DataFrame(rows)
        # Sem isto, o primeiro CNJ que falha põe motivo_falha logo depois de id_cnj.
        df[COLUNA_MOTIVO_FALHA] = df.pop(COLUNA_MOTIVO_FALHA)
        if download_pecas:
            df["pecas"] = [c.pecas for c in consultas]
            df["pecas_falhas"] = [c.pecas_falhas for c in consultas]
            self._avisar_pecas(cnjs, consultas, endpoint)
        return df

    def _avisar_pecas(self, cnjs: list[str], consultas: list[_Consulta], endpoint: str) -> None:
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
            f"{type(self).__name__}.{endpoint}",
            "download(s) de peça",
            "As peças que faltam estão na coluna pecas_falhas.",
        )

    def _pecas_do_processo(self, cnj: str, bruto: dict[str, Any], base_url: str, base_dir: str) -> _Consulta:
        """Grava o PDF de cada documento em ``<base_dir>/<cnj>/<id do documento>.pdf``.

        A peça que falha vai para ``pecas_falhas`` com o motivo, e as demais
        seguem. O bloqueio anti-bot vale para a sessão inteira: a bloqueada e
        as seguintes, que não são pedidas, entram em ``pecas_falhas`` com
        ``bloqueio_anti_bot``, e a consulta sai com esse motivo. Erro ao gravar
        no disco sobe, porque vale para o lote inteiro. Lista de documentos
        fora do formato esperado vira aviso no log e o processo fica sem
        peças, sem derrubar o lote.
        """
        alvo = self._documentos_do_processo(cnj, bruto)
        if alvo is None:
            return _Consulta(bruto, None, [], [])
        id_processo, documentos = alvo
        proc_dir = Path(base_dir) / cnj
        proc_dir.mkdir(parents=True, exist_ok=True)
        paths: list[str] = []
        falhas: list[dict[str, Any]] = []
        for i, doc in enumerate(documentos):
            try:
                resultado = self._baixar_peca(cnj, doc, proc_dir, base_url, id_processo)
            except BotChallengeBlockedError as exc:
                logger.warning(
                    "%s: bloqueio anti-bot na peça %s do %s; as peças param aqui: %s",
                    self.TRIBUNAL_NAME, _id_documento(doc), cnj, exc,
                )
                # A bloqueada e as seguintes, que não serão pedidas, também faltam.
                falhas.extend(
                    {"id": _id_documento(d), COLUNA_MOTIVO_FALHA: MOTIVO_BLOQUEIO_ANTI_BOT} for d in documentos[i:]
                )
                return _Consulta(bruto, MOTIVO_BLOQUEIO_ANTI_BOT, paths, falhas)
            if isinstance(resultado, str):
                paths.append(resultado)
            else:
                falhas.append(resultado)
        return _Consulta(bruto, None, paths, falhas)

    @staticmethod
    def _documentos_do_processo(cnj: str, bruto: dict[str, Any]) -> tuple[str, list[object]] | None:
        """``idProcesso`` e documentos de um processo; ``None`` quando não há peças a baixar.

        ``linhas_de_processos`` já transformou o processo com envelope
        malformado em linha só com ``id_cnj``; sem este ``try`` o mesmo
        envelope levantaria aqui e a chamada perderia o DataFrame do lote
        inteiro. ``baixar_processo`` já recusou ``idProcesso`` inválido, e
        ``baixar_documento`` confere de novo antes de montar a URL.
        """
        try:
            id_processo = bruto["busca"]["idProcesso"]
            documentos: list[object] = list(_itens(bruto.get("documentos") or []))
        except Exception as exc:  # noqa: BLE001 (resiliência por item)
            logger.warning("Peças do %s puladas: documentos fora do formato esperado: %s", cnj, exc)
            return None
        return id_processo, documentos

    def _baixar_peca(
        self, cnj: str, doc: object, proc_dir: Path, base_url: str, id_processo: str
    ) -> str | dict[str, Any]:
        """Grava o PDF de um documento e devolve o caminho, ou a falha da peça.

        O ``id`` do documento vem do servidor e vira nome de arquivo: ``id``
        ausente ou recusado por :func:`token_valido` (alfabeto ou comprimento)
        sai ``resposta_inesperada`` antes de qualquer requisição, e o caminho
        final ainda é conferido contra o diretório do processo. Bloqueio
        anti-bot, dependência ausente e erro de gravação sobem; os demais
        erros saem com o motivo.
        """
        id_documento = _id_documento(doc)
        falha = {"id": id_documento, COLUNA_MOTIVO_FALHA: MOTIVO_RESPOSTA_INESPERADA}
        if not token_valido(id_documento):
            logger.warning("Peça do %s pulada: id de documento inválido %r", cnj, id_documento)
            return falha
        path = proc_dir / f"{id_documento}.pdf"
        if path.resolve().parent != proc_dir.resolve():
            logger.warning("Peça do %s pulada: %r sai do diretório do processo", cnj, id_documento)
            return falha
        # Pausa também antes da 1ª peça, que vem logo depois dos envelopes.
        if self.sleep_time:
            time.sleep(self.sleep_time)
        try:
            content = baixar_documento(self._request_with_retry, base_url, id_documento, id_processo)
        except (BotChallengeBlockedError, ImportError):
            raise
        except Exception as exc:  # noqa: BLE001 (resiliência por peça)
            logger.warning("Erro ao baixar peça %s do %s: %s", id_documento, cnj, exc)
            return {"id": id_documento, COLUNA_MOTIVO_FALHA: motivo_falha_ou_inesperada(exc)}
        path.write_bytes(content)
        return str(path)

    # --- API pública ----------------------------------------------------

    def cpopg_download(self, id_cnj: str | list[str], **kwargs: Any) -> list[dict[str, Any] | None]:
        """Baixa os envelopes JSON de 1º grau de cada CNJ, sem parsear.

        Aceita os mesmos argumentos de :meth:`cpopg`. ``download_pecas`` e
        ``diretorio`` passam pela validação e são ignorados, porque este
        método não baixa peças. Devolve uma lista alinhada à entrada: um
        dicionário por processo (chaves ``busca``, ``dados`` e uma por recurso
        paginado) ou ``None`` para o CNJ que a consulta pública não devolveu
        ou cuja consulta falhou. As falhas entram num único ``UserWarning`` ao
        fim; :meth:`cpopg` traz o motivo de cada uma em ``motivo_falha``. Um
        bloqueio anti-bot encerra o lote, e os CNJs restantes saem ``None``.
        """
        return self._download("cpopg", "cpopg_download", id_cnj, **kwargs)

    def cpopg_parse(
        self,
        brutos: list[dict[str, Any] | None] | None = None,
        id_cnj_list: list[str] | None = None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """Transforma a saída de :meth:`cpopg_download` num DataFrame, uma linha por CNJ.

        Sem a coluna ``motivo_falha``: um ``None`` vindo de
        :meth:`cpopg_download` pode ser processo ausente ou consulta que
        falhou, e só :meth:`cpopg` sabe qual. O bruto que o parser recusa vira
        linha só com ``id_cnj`` e entra num ``UserWarning``.

        Args:
            brutos: Lista devolvida por :meth:`cpopg_download`, com um
                dicionário de envelopes JSON ou ``None`` por CNJ. Entradas
                ``None`` viram linha só com ``id_cnj``.
            id_cnj_list: CNJs na mesma ordem de ``brutos``.
            **kwargs: Só o alias deprecado ``htmls``, descrito abaixo. Qualquer
                outro nome levanta ``TypeError``.

        Aliases deprecados:
            * ``htmls`` -> ``brutos`` (DeprecationWarning). O nome vem da
              época em que o ``cpopg_download`` devolvia HTML; o conteúdo
              agora precisa ser o dicionário da API.

        Raises:
            TypeError: ``brutos`` ou ``id_cnj_list`` ausentes, kwarg
                desconhecido, ou item de ``brutos`` que não é dicionário nem
                ``None`` (o HTML do portal antigo, por exemplo).
            ValueError: ``brutos`` e ``id_cnj_list`` de tamanhos diferentes,
                ou ``brutos`` e ``htmls`` passados juntos.
        """
        brutos = resolve_deprecated_alias(kwargs, "htmls", "brutos", brutos)
        if kwargs:
            names = ", ".join(repr(k) for k in kwargs)
            raise TypeError(f"{type(self).__name__}.cpopg_parse got unexpected keyword argument(s): {names}")
        if brutos is None or id_cnj_list is None:
            raise TypeError(f"{type(self).__name__}.cpopg_parse exige brutos e id_cnj_list")
        return self._parse(brutos, id_cnj_list, "cpopg_parse")

    def cpopg(
        self,
        id_cnj: str | list[str],
        *,
        download_pecas: bool = False,
        diretorio: str | None = None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """Consulta processos de 1º grau na consulta pública do PJe do TRF3.

        Args:
            id_cnj: CNJ único ou lista, com ou sem máscara.
            download_pecas: Se ``True``, baixa o PDF de cada documento listado
                no processo, logo depois dos dados do processo. Só por nome.
                Default ``False``.
            diretorio: Onde gravar as peças, em ``<diretorio>/<cnj>/<id>.pdf``.
                Quando omitido, usa ``download_path`` do construtor.
            **kwargs: Nenhum outro argumento é aceito; nome desconhecido
                levanta ``TypeError``.

        Returns:
            DataFrame com uma linha por CNJ e as colunas ``id_cnj``,
                ``processo``, ``classe``, ``assunto``, ``data_distribuicao``
                (``DD/MM/AAAA``), ``orgao_julgador``, ``orgao_julgador_colegiado``,
                ``jurisdicao``, ``endereco_orgao``, ``polo_ativo``,
                ``polo_passivo``, ``outros_interessados``, ``movimentacoes``,
                ``documentos`` e ``motivo_falha``. Com ``download_pecas=True``,
                ganha ``pecas``, a lista de caminhos gravados, e
                ``pecas_falhas``, as peças que não puderam ser baixadas, cada
                uma como ``{"id": <id da peça>, "motivo_falha": <motivo>}``; as
                falhas de peça saem num ``UserWarning`` próprio ao fim e não
                mudam ``motivo_falha`` do processo, salvo o bloqueio anti-bot
                (abaixo).

                ``motivo_falha`` é ``None`` quando a consulta respondeu,
                inclusive para o CNJ que a consulta pública não devolve
                (inexistente ou em segredo de justiça), que sai como linha só
                com ``id_cnj``. Quando a consulta de um CNJ falha, a linha sai
                só com ``id_cnj`` e o motivo, no vocabulário de
                :data:`juscraper.core.failures.MOTIVOS_FALHA` (erro HTTP ou de
                rede na busca ou em ``/dados`` depois das tentativas;
                ``resposta_inesperada`` para resposta fora do formato
                esperado), e o lote segue. As falhas entram num único
                ``UserWarning`` ao fim
                (:class:`~juscraper.core.exceptions.BloqueioAntiBotWarning`
                quando há bloqueio anti-bot).

                Um bloqueio do Akamai vale para a sessão inteira: o lote para
                no CNJ bloqueado, sem novos pedidos, e ele e os seguintes saem
                com ``bloqueio_anti_bot``. As linhas anteriores são
                preservadas, com as peças já gravadas. O processo bloqueado
                nas peças sai com os dados lidos, as peças já gravadas e
                ``bloqueio_anti_bot``; a bloqueada e as seguintes entram em
                ``pecas_falhas``. Aguarde alguns minutos ou troque de IP e peça
                de novo só as linhas com ``motivo_falha``.

        Raises:
            TypeError: Kwarg desconhecido.

        See Also:
            :class:`InputCpopgTRF3`: schema dos argumentos aceitos.
        """
        return self._consulta("cpopg", id_cnj, download_pecas=download_pecas, diretorio=diretorio, **kwargs)

    def cposg_download(self, id_cnj: str | list[str], **kwargs: Any) -> list[dict[str, Any] | None]:
        """Baixa os envelopes JSON de 2º grau de cada CNJ, sem parsear.

        Mesmo retorno e mesmos avisos de :meth:`cpopg_download`, consultando a
        aplicação de 2º grau. Os argumentos são os de :meth:`cposg`;
        ``download_pecas`` e ``diretorio`` passam pela validação e são
        ignorados, porque este método não baixa peças.
        """
        return self._download("cposg", "cposg_download", id_cnj, **kwargs)

    def cposg_parse(self, brutos: list[dict[str, Any] | None], id_cnj_list: list[str]) -> pd.DataFrame:
        """Transforma a saída de :meth:`cposg_download` num DataFrame, uma linha por CNJ.

        Como :meth:`cpopg_parse`, sem a coluna ``motivo_falha``.
        """
        return self._parse(brutos, id_cnj_list, "cposg_parse")

    def cposg(
        self,
        id_cnj: str | list[str],
        *,
        download_pecas: bool = False,
        diretorio: str | None = None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """Consulta processos de 2º grau na consulta pública do PJe do TRF3.

        O CNJ do recurso costuma ser o mesmo do processo de origem; a consulta
        de 2º grau devolve o recurso (apelação, agravo, remessa) que tramita
        no tribunal com esse número. Se a busca devolver mais de um processo
        com o número pedido, só o primeiro é consultado, e o logger
        ``juscraper.trf3`` avisa quantos a busca devolveu; nas consultas
        observadas a busca devolveu no máximo um.

        Args:
            id_cnj: CNJ único ou lista, com ou sem máscara.
            download_pecas: Se ``True``, baixa o PDF de cada documento listado
                no processo, logo depois dos dados do processo. Só por nome.
                Default ``False``.
            diretorio: Onde gravar as peças, em ``<diretorio>/<cnj>/<id>.pdf``.
                Quando omitido, usa ``download_path`` do construtor.
            **kwargs: Nenhum outro argumento é aceito; nome desconhecido
                levanta ``TypeError``.

        Returns:
            DataFrame com as mesmas colunas e o mesmo tratamento de falhas de
                :meth:`cpopg`. No 2º grau, ``orgao_julgador_colegiado`` traz a
                turma, e o CNJ sem recurso no 2º grau sai como linha só com
                ``id_cnj`` e ``motivo_falha`` ``None``.

        Raises:
            TypeError: Kwarg desconhecido.

        See Also:
            :class:`InputCposgTRF3`: schema dos argumentos aceitos.
        """
        return self._consulta("cposg", id_cnj, download_pecas=download_pecas, diretorio=diretorio, **kwargs)

    def cjsg(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """Pesquisa jurisprudência no portal do TRF3 (``web.trf3.jus.br/jurisprudencia``).

        Cada chamada abre uma sessão própria no portal, executa a busca e lê
        a lista resumida, que já traz ementa e inteiro teor de cada documento.
        Custa três requisições fixas (abertura da aba, ``POST`` da busca e
        ``GET`` do redirect que traz a página 1) e uma por página adicional,
        com ``sleep_time`` entre páginas.

        Args:
            pesquisa (str | None): Texto da pesquisa livre, com os operadores do
                portal (operador padrão ``e``). Pode ficar vazio quando outro
                critério for informado.
            paginas (int | list | range | None): Páginas 1-based; ``None`` baixa
                todas. Páginas além do total são ignoradas sem requisição.
            **kwargs: Filtros aceitos por :class:`InputCJSGTRF3`:

                * ``base`` (str): ``"acordaos"`` (default; acórdãos do TRF3),
                  ``"turmas_recursais"`` (acórdãos das Turmas Recursais dos
                  JEFs), ``"monocraticas"`` (decisões monocráticas do TRF3) ou
                  ``"monocraticas_turmas_recursais"`` (decisões monocráticas
                  das Turmas Recursais).
                * ``numero_processo`` (str): Número do processo, com ou sem
                  máscara.
                * ``relator`` (str): Nome do relator ou do relator para o
                  acórdão, como o portal indexa (ex.: ``"NERY JUNIOR"``, a
                  forma do dropdown do formulário). O portal casa nomes
                  parciais.
                * ``classe`` (str): Classe como no dropdown, com sigla (ex.:
                  ``"AI - AGRAVO DE INSTRUMENTO"``).
                * ``orgao_julgador`` (str): Órgão julgador, pelo rótulo do
                  dropdown do formulário (``"3ª Turma"``,
                  ``"11ª Turma Recursal da Seção Judiciária de São Paulo"``)
                  ou pelo nome indexado da opção (``"TERCEIRA TURMA"``,
                  ``"11ª TURMA RECURSAL DE SÃO PAULO"``), sem diferença de
                  caixa e de espaços. O valor da coluna ``orgao_julgador``
                  do resultado também serve: "1a. seção" vira "1A", como no
                  formulário, então ``"QUINTA TURMA - 1A. SEÇÃO"`` casa com
                  a opção ``QUINTA TURMA - 1a. SEÇÃO``. A busca manda o par
                  que o navegador mandaria, rótulo e nome indexado da opção,
                  lido do formulário da aba, e traz os documentos gravados
                  com qualquer dos dois (medido com "medicamento":
                  ``"QUINTA TURMA"`` traz 576 documentos, contra 443 do
                  rótulo sozinho e 133 do nome indexado sozinho). Rótulo de
                  mais de uma opção, como ``"5ª Turma"`` nos acórdãos, levanta
                  ``ValueError``; texto que não casa com nenhuma opção vai
                  como está e só encontra o que o portal grava com essa
                  grafia. Não existe nas bases de monocráticas.
                * ``ementa`` (str): Texto pesquisado só na ementa. Não existe
                  nas bases de monocráticas.
                * ``indexacao`` (str): Texto pesquisado na indexação ("Objeto
                  do Processo" nas Turmas Recursais). Não existe nas bases de
                  monocráticas.
                * ``data_julgamento_inicio`` / ``data_julgamento_fim`` (str):
                  Data de julgamento; nas monocráticas, data da decisão.
                * ``data_publicacao_inicio`` / ``data_publicacao_fim`` (str):
                  Data de publicação. Não combina com ``data_julgamento_*``.
                * ``tamanho_pagina`` (int): 10 (default), 30 ou 50 documentos
                  por página.

        Aliases deprecados (popados com ``DeprecationWarning`` antes do pydantic):
            * ``query`` / ``termo`` -> ``pesquisa``
            * ``data_inicio`` / ``data_fim`` -> ``data_julgamento_inicio`` / ``_fim``
            * ``data_julgamento_de`` / ``_ate`` -> ``data_julgamento_inicio`` / ``_fim``
            * ``data_publicacao_de`` / ``_ate`` -> ``data_publicacao_inicio`` / ``_fim``

        Raises:
            TypeError: Quando todos os erros são kwargs desconhecidos.
            ValidationError: Para os demais erros do schema (base ou
                ``tamanho_pagina`` fora do domínio, data inválida).
            ValueError: Datas de julgamento e de publicação juntas; filtro que a
                base de monocráticas não tem; nenhum critério;
                ``orgao_julgador`` que corresponde a mais de uma opção do
                formulário (a mensagem lista os nomes indexados que
                desfazem a ambiguidade); com ``paginas=None``, primeira
                página com documentos e total de resultados ilegível.
            BotChallengeBlockedError: A Akamai bloqueou o IP (HTTP 403
                ``Access Denied``).
            RuntimeError: O portal devolveu a página de sessão expirada, ou
                respondeu 200 com uma página que não é a lista de resultados
                (formulário de busca, manutenção), na primeira página ou nas
                seguintes; ou, da página 2 em diante, com o aviso de nenhum
                resultado quando a primeira página informou total maior que
                zero. Busca sem resultados não é erro: devolve DataFrame
                vazio.

        Returns:
            Uma linha por documento, com ``processo``,
                ``classe``, ``orgao_julgador``, ``relator``, ``relator_acordao``,
                ``data_julgamento``, ``data_publicacao``, ``meio_publicacao``
                (``DJEN``, ``Intimação via sistema``, ``e-DJF3 Judicial 1``...),
                ``ementa`` (nas monocráticas, o texto da decisão), ``base``,
                ``url_inteiro_teor`` (íntegra do acórdão no site do TRF3; vazio
                nas monocráticas) e ``inteiro_teor`` (texto completo). Em parte
                dos acórdãos antigos das Turmas Recursais, ``ementa`` vem nula
                porque o portal manda o bloco da ementa vazio; ``inteiro_teor``
                vem preenchido. Na medição, com "medicamento", foram nulas todas
                as ementas de 2013 e 2014 e parte das de 2011.

        Examples: Exemplo
            >>> import juscraper as jus
            >>> trf3 = jus.scraper("trf3")
            >>> df = trf3.cjsg(
            ...     "medicamento", base="turmas_recursais", paginas=range(1, 3),
            ...     data_julgamento_inicio="2026-01-01", data_julgamento_fim="2026-06-30",
            ... )

        See Also:
            :class:`InputCJSGTRF3`: fonte dos filtros aceitos.
        """
        return self.cjsg_parse(self.cjsg_download(pesquisa=pesquisa, paginas=paginas, **kwargs))

    def cjsg_download(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        **kwargs: Any,
    ) -> list[str]:
        """Baixa as páginas da lista resumida da busca de jurisprudência do TRF3.

        Aceita os mesmos filtros de :meth:`cjsg`; veja lá a lista completa.

        Returns:
            HTML de cada página baixada, na ordem pedida.
        """
        inp = apply_input_pipeline_search(
            InputCJSGTRF3,
            "TRF3Scraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            nullable_pesquisa=True,
        )
        validar_combinacoes(inp)
        return cjsg_download_manager(
            inp,
            request_fn=self._request_with_retry,
            session=build_cjsg_session(),
            sleep_time=self.sleep_time,
        )

    def cjsg_parse(self, resultados_brutos: list[str]) -> pd.DataFrame:
        """Converte as páginas de :meth:`cjsg_download` em DataFrame.

        Returns:
            Uma linha por documento; colunas descritas em :meth:`cjsg`.
        """
        return cjsg_parse_manager(resultados_brutos)
