"""Base dos raspadores da consulta pública do PJe que consome a API JSON ``/v1``.

A subclasse declara a instalação de 1º grau (:attr:`PJeAPIScraper.APLICACAO_1G`),
a sigla e o schema de entrada; o ``cpopg`` e o par ``cpopg_download``/
``cpopg_parse`` ficam aqui. O TRF3 acrescenta o ``cposg`` (2º grau) e o TLS de
navegador; o TRF1 usa a base como está.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, ClassVar, NamedTuple

import pandas as pd
import requests
from pydantic import ValidationError
from tqdm import tqdm

from ...core.download import gravar_arquivo
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
from ...core.http import HTTPScraper
from ...schemas import CnjInputBase
from ...utils.cnj import clean_cnj, format_cnj
from ...utils.params import raise_on_extra_kwargs, resolve_deprecated_alias
from .download import API_HEADERS, AplicacaoPJe, baixar_documento, baixar_processo, token_valido
from .parse import COLUNAS_DETALHE, _itens, parse_processo


class _Consulta(NamedTuple):
    """Resultado da consulta de um CNJ (peças só com ``download_pecas``)."""

    bruto: dict[str, Any] | None
    motivo: str | None
    pecas: list[str]
    pecas_falhas: list[dict[str, Any]]


def _id_documento(doc: object) -> object:
    """O ``id`` de um item de ``documentos``, sem validar; ``None`` fora de dicionário."""
    return doc.get("id") if isinstance(doc, dict) else None


class PJeAPIScraper(HTTPScraper):
    """Consulta processual de 1º grau na consulta pública do PJe (API JSON).

    A subclasse define :attr:`TRIBUNAL_NAME`, :attr:`APLICACAO_1G`,
    :attr:`INPUT_CPOPG` e os perfis HTTP ``"api"`` (busca e detalhe) e
    ``"documento"`` (PDF das peças) em ``perfis_http``.
    """

    #: Sigla do tribunal: logger ``juscraper.<sigla>``, barra de progresso e mensagens.
    TRIBUNAL_NAME: str = ""
    #: Instalação consultada pelo ``cpopg``.
    APLICACAO_1G: ClassVar[AplicacaoPJe]
    #: Schema dos argumentos do ``cpopg`` (``extra="forbid"``).
    INPUT_CPOPG: type[CnjInputBase]

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
        self._logger = self.APLICACAO_1G.logger

    def _configure_session(self, session: requests.Session) -> None:
        """Cabeçalhos de uma chamada XHR do Chrome."""
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

    # Gancho: o TRF3 escolhe a instalação de 2º grau pelo endpoint; a base só tem o ``cpopg``.
    def _alvo(self, endpoint: str) -> tuple[type[CnjInputBase], AplicacaoPJe]:  # noqa: ARG002
        """Schema de entrada e instalação que atendem o ``endpoint``."""
        return self.INPUT_CPOPG, self.APLICACAO_1G

    def _baixar(
        self, cnjs: list[str], app: AplicacaoPJe, endpoint: str, pecas_dir: str | None = None
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
            lambda cnj: self._consultar(cnj, app, pecas_dir),
            lambda motivo: _Consulta(None, motivo, [], []),
            sleep_time=self.sleep_time,
        )

    def _consultar(self, cnj: str, app: AplicacaoPJe, pecas_dir: str | None) -> _Consulta:
        """A consulta de um CNJ (peças só com ``pecas_dir``)."""
        bruto, motivo = consultar_processo(
            lambda c: baixar_processo(self._request_with_retry, app, format_cnj(c), sleep_time=self.sleep_time),
            cnj,
            tribunal=self.TRIBUNAL_NAME,
            logger=self._logger,
        )
        if bruto is None or pecas_dir is None:
            return _Consulta(bruto, motivo, [], [])
        return self._pecas_do_processo(cnj, bruto, app, pecas_dir)

    def _linhas(
        self, brutos: list[dict[str, Any] | None], id_cnj_list: list[str], motivos: list[str | None]
    ) -> list[dict[str, Any]]:
        """Uma linha por CNJ, com ``id_cnj`` primeiro e ``motivo_falha`` por último.

        Bruto ``None`` ou recusado pelo parser vira linha com ``id_cnj`` e as
        colunas de :data:`COLUNAS_DETALHE` em ``None``; o recusado ganha
        ``resposta_inesperada`` quando não trazia motivo.
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
                f"o *_download devolve, não o HTML do portal antigo (recebido: {', '.join(invalidos)}). "
                "Baixe de novo com o *_download."
            )
        rows = linhas_de_processos(id_cnj_list, brutos, motivos, parse=parse_processo, logger=self._logger)
        return [{"id_cnj": row["id_cnj"], **dict.fromkeys(COLUNAS_DETALHE), **row} for row in rows]

    def _avisar(self, cnjs: list[str], motivos: list[str | None], metodo: str) -> None:
        """Um ``UserWarning`` com os CNJs que falharam, atribuído ao método público ``metodo``."""
        avisar_falhas_de_processos(cnjs, motivos, f"{type(self).__name__}.{metodo}")

    def _parse(self, brutos: list[dict[str, Any] | None], id_cnj_list: list[str], metodo: str) -> pd.DataFrame:
        """DataFrame do fluxo em duas etapas, sem a coluna ``motivo_falha``.

        Um ``None`` vindo do download pode ser processo ausente ou consulta que
        falhou, e só o método composto sabe qual. O bruto que o parser recusa
        entra no aviso.
        """
        rows = self._linhas(brutos, id_cnj_list, [None] * len(brutos))
        self._avisar(id_cnj_list, [row.pop(COLUNA_MOTIVO_FALHA) for row in rows], metodo)
        return pd.DataFrame(rows)

    def _download(
        self, endpoint: str, metodo: str, id_cnj: str | list[str], **kwargs: Any
    ) -> list[dict[str, Any] | None]:
        """Os brutos de ``*_download``, com as falhas num aviso."""
        schema, app = self._alvo(endpoint)
        cnjs = self._coerce_id_cnj(schema, metodo, id_cnj, **kwargs)
        consultas = self._baixar(cnjs, app, endpoint)
        self._avisar(cnjs, [c.motivo for c in consultas], metodo)
        return [c.bruto for c in consultas]

    def _consulta(
        self,
        endpoint: str,
        id_cnj: str | list[str],
        *,
        download_pecas: bool,
        diretorio: str | None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        schema, app = self._alvo(endpoint)
        cnjs = self._coerce_id_cnj(
            schema, endpoint, id_cnj, download_pecas=download_pecas, diretorio=diretorio, **kwargs
        )
        pecas_dir: str | None = None
        if download_pecas:
            pecas_dir = diretorio if diretorio is not None else self.download_path
            Path(pecas_dir).mkdir(parents=True, exist_ok=True)
        consultas = self._baixar(cnjs, app, endpoint, pecas_dir)
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

    def _pecas_do_processo(self, cnj: str, bruto: dict[str, Any], app: AplicacaoPJe, base_dir: str) -> _Consulta:
        """Grava o PDF de cada documento em ``<base_dir>/<cnj>/<id do documento>.pdf``.

        A peça que falha vai para ``pecas_falhas`` com o motivo, e as demais
        seguem. O bloqueio anti-bot vale para a sessão inteira: a bloqueada e
        as seguintes, que não são pedidas, entram em ``pecas_falhas`` com
        ``bloqueio_anti_bot``, e a consulta sai com esse motivo. Erro ao gravar
        no disco (cheio, sem permissão) tende a se repetir: as peças do
        processo param ali, a da vez e as seguintes entram em ``pecas_falhas``
        com ``resposta_inesperada``, a consulta sai com esse motivo e o lote
        segue, como na família ``_trf``. Lista de documentos fora do formato
        esperado vira aviso no log e o processo fica sem peças, sem derrubar o
        lote.
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
                resultado = self._baixar_peca(cnj, doc, proc_dir, app, id_processo)
            except (BotChallengeBlockedError, OSError) as exc:
                return self._encerrar_pecas(cnj, _Consulta(bruto, None, paths, falhas), documentos[i:], exc)
            if isinstance(resultado, str):
                paths.append(resultado)
            else:
                falhas.append(resultado)
        return _Consulta(bruto, None, paths, falhas)

    def _encerrar_pecas(self, cnj: str, parcial: _Consulta, restantes: list[object], exc: Exception) -> _Consulta:
        """A consulta cujas peças pararam num bloqueio ou num erro ao gravar.

        ``parcial`` traz o que já foi gravado e as falhas até aqui. A peça da
        vez e as seguintes (``restantes``), que não serão pedidas, também faltam.
        """
        bloqueio = isinstance(exc, BotChallengeBlockedError)
        motivo = MOTIVO_BLOQUEIO_ANTI_BOT if bloqueio else MOTIVO_RESPOSTA_INESPERADA
        self._logger.warning(
            "%s: %s na peça %s do %s; as peças do processo param aqui: %s",
            self.TRIBUNAL_NAME, "bloqueio anti-bot" if bloqueio else "erro ao gravar",
            _id_documento(restantes[0]), cnj, exc,
        )
        falhas = [*parcial.pecas_falhas, *({"id": _id_documento(d), COLUNA_MOTIVO_FALHA: motivo} for d in restantes)]
        return parcial._replace(motivo=motivo, pecas_falhas=falhas)

    def _documentos_do_processo(self, cnj: str, bruto: dict[str, Any]) -> tuple[str, list[object]] | None:
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
            self._logger.warning("Peças do %s puladas: documentos fora do formato esperado: %s", cnj, exc)
            return None
        return id_processo, documentos

    def _baixar_peca(
        self, cnj: str, doc: object, proc_dir: Path, app: AplicacaoPJe, id_processo: str
    ) -> str | dict[str, Any]:
        """Grava o PDF de um documento e devolve o caminho, ou a falha da peça.

        O ``id`` do documento vem do servidor e vira nome de arquivo: ``id``
        ausente ou recusado por :func:`token_valido` (alfabeto ou comprimento)
        sai ``resposta_inesperada`` antes de qualquer requisição, e o caminho
        final ainda é conferido contra o diretório do processo. Bloqueio
        anti-bot, dependência ausente e erro de gravação (``OSError`` de
        :func:`~juscraper.core.download.gravar_arquivo`, que não deixa arquivo
        truncado) sobem; os demais erros saem com o motivo.
        """
        id_documento = _id_documento(doc)
        falha = {"id": id_documento, COLUNA_MOTIVO_FALHA: MOTIVO_RESPOSTA_INESPERADA}
        if not token_valido(id_documento):
            self._logger.warning("Peça do %s pulada: id de documento inválido %r", cnj, id_documento)
            return falha
        path = proc_dir / f"{id_documento}.pdf"
        if path.resolve().parent != proc_dir.resolve():
            self._logger.warning("Peça do %s pulada: %r sai do diretório do processo", cnj, id_documento)
            return falha
        # Pausa também antes da 1ª peça, que vem logo depois dos envelopes.
        if self.sleep_time:
            time.sleep(self.sleep_time)
        try:
            content = baixar_documento(self._request_with_retry, app, id_documento, id_processo)
        except (BotChallengeBlockedError, ImportError):
            raise
        except Exception as exc:  # noqa: BLE001 (resiliência por peça)
            self._logger.warning("Erro ao baixar peça %s do %s: %s", id_documento, cnj, exc)
            return {"id": id_documento, COLUNA_MOTIVO_FALHA: motivo_falha_ou_inesperada(exc)}
        gravar_arquivo(content, path)
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
        """Consulta processos de 1º grau na consulta pública do PJe.

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

                Um bloqueio anti-bot vale para a sessão inteira: o lote para
                no CNJ bloqueado, sem novos pedidos, e ele e os seguintes saem
                com ``bloqueio_anti_bot``. As linhas anteriores são
                preservadas, com as peças já gravadas. O processo bloqueado
                nas peças sai com os dados lidos, as peças já gravadas e
                ``bloqueio_anti_bot``; a bloqueada e as seguintes entram em
                ``pecas_falhas``. Aguarde alguns minutos ou troque de IP e peça
                de novo só as linhas com ``motivo_falha``. Um erro ao gravar
                uma peça (disco cheio, sem permissão) para as peças daquele
                processo do mesmo jeito, com ``resposta_inesperada``, e o lote
                segue.

        Raises:
            TypeError: Kwarg desconhecido.
        """
        return self._consulta("cpopg", id_cnj, download_pecas=download_pecas, diretorio=diretorio, **kwargs)
