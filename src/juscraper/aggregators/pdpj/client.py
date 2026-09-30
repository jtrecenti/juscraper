"""Client publico do agregador PDPJ.

Wrapper sobre a API ``DATALAKE - API Processos`` do PDPJ
(``https://api-processo-integracao.data-lake.pdpj.jus.br/processo-api/api/v1``).
A autenticacao e via JWT no header ``Authorization: Bearer <token>``.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable, Iterator, Mapping
from typing import Any, ClassVar, cast

import pandas as pd
import requests
from pydantic import ValidationError

from ...core.auth import validar_jwt
from ...core.failures import (
    COLUNA_MOTIVO_FALHA,
    EXCECOES_DE_FALHA_POR_LINHA,
    STATUS_CONSULTA_FALHA,
    anotar_falhas_anteriores,
    avisar_falhas,
    e_token_invalido,
    motivo_falha,
)
from ...core.http import HTTPScraper, RequestFn, RequestPolicy
from ...utils.cnj import clean_cnj
from ...utils.params import normalize_paginas, raise_on_extra_kwargs
from .download import (
    BASE_URL,
    PERFIL_DOCUMENTO,
    PERFIL_LISTAGEM,
    USER_AGENT,
    fetch_contar,
    fetch_documento_binario,
    fetch_documento_texto,
    fetch_pesquisa,
    fetch_processo_detalhes,
    fetch_processo_documentos,
    fetch_processo_existe,
    fetch_processo_movimentos,
    fetch_processo_partes,
)
from .parse import (
    build_documento_rows,
    build_movimento_rows,
    build_parte_rows,
    build_processo_row,
    clean_document_text,
    parse_pesquisa_response,
)
from .schemas import InputAuthPdpj, InputCnjPdpj, InputContarPdpj, InputDownloadDocumentsPdpj, InputPesquisaPdpj

logger = logging.getLogger(__name__)


# Mapeia nomes canonicos snake_case -> nomes camelCase aceitos pela API.
# Mantido como modulo-level porque e compartilhado entre :meth:`pesquisa`
# e :meth:`contar` (mesmo conjunto de filtros).
_QUERY_PARAM_MAP: dict[str, str] = {
    "numero_processo": "numeroProcesso",
    "numero_processo_sintetico": "numeroProcessoSintetico",
    "id": "id",
    "id_fonte_dados_codex": "idFonteDadosCodex",
    "cpf_cnpj_parte": "cpfCnpjParte",
    "nome_parte": "nomeParte",
    "outro_nome_parte": "outroNomeParte",
    "polo_parte": "poloParte",
    "situacao_parte": "situacaoParte",
    "nome_representante": "nomeRepresentante",
    "oab_representante": "oabRepresentante",
    "href": "href",
    "id_assunto_judicial": "idAssuntoJudicial",
    "id_classe": "idClasse",
    "id_orgao_julgador": "idOrgaoJulgador",
    "instancia": "instancia",
    "fase": "fase",
    "situacao_atual": "situacaoAtual",
    "segmento_justica": "segmentoJustica",
    "tribunal": "tribunal",
    "tipo_operacao": "tipoOperacao",
    "numero_historico": "numeroHistorico",
    "data_atualizacao_inicio": "dataHoraAtualizacaoInicio",
    "data_atualizacao_fim": "dataHoraAtualizacaoFim",
    "data_primeiro_ajuizamento_inicio": "dataHoraPrimeiroAjuizamentoInicio",
    "data_primeiro_ajuizamento_fim": "dataHoraPrimeiroAjuizamentoFim",
    "campo_ordenacao": "campoOrdenacao",
}


def _to_query_params(model_data: dict[str, Any]) -> dict[str, Any]:
    """Converte um dict com nomes canonicos para querystring camelCase.

    Valores ``None`` sao ignorados; listas viram strings com itens
    separados por virgula (formato esperado pela API).
    """
    out: dict[str, Any] = {}
    for key, value in model_data.items():
        if value is None:
            continue
        api_key = _QUERY_PARAM_MAP.get(key, key)
        if isinstance(value, list):
            out[api_key] = ",".join(str(v) for v in value)
        else:
            out[api_key] = value
    return out


def _iter_documents(details: dict[str, Any]) -> Iterator[Any]:
    """Itera documentos do topo e das tramitacoes na ordem da API."""
    top_documents = details.get("documentos")
    if isinstance(top_documents, list):
        yield from top_documents
    traversals = details.get("tramitacoes")
    if not isinstance(traversals, list):
        return
    for traversal in traversals:
        if isinstance(traversal, dict) and isinstance(traversal.get("documentos"), list):
            yield from traversal["documentos"]


def _document_to_row(
    document: Any,
    process: Any,
    process_number: Any,
) -> dict[str, Any] | None:
    """Achata um documento PDPJ bem-formado no formato de download."""
    if not isinstance(document, dict):
        return None
    file_data = document.get("arquivo") or {}
    document_type = document.get("tipo") or {}
    return {
        "processo": process,
        "numero_processo": process_number,
        "id_documento": document.get("id"),
        "id_codex": document.get("idCodex"),
        "sequencia": document.get("sequencia"),
        "data_juntada": document.get("dataHoraJuntada"),
        "nome": document.get("nome"),
        "nivel_sigilo": document.get("nivelSigilo"),
        "tipo_codigo": document_type.get("codigo"),
        "tipo_nome": document_type.get("nome"),
        "arquivo_id": file_data.get("id"),
        "arquivo_tipo": file_data.get("tipo"),
        "arquivo_tamanho": file_data.get("tamanho"),
        "arquivo_paginas": file_data.get("quantidadePaginas"),
    }


_ITEM_CONSULTA = "consulta(s) de processo"
_ITEM_DOWNLOAD = "download(s) de documento"

# Status retentáveis dos dois perfis: os do core sem o 403. No PDPJ, com token
# válido, o 403 nega um recurso só (um documento sigiloso, por exemplo), e
# retentar gastaria as tentativas numa resposta que não muda.
_STATUS_RETENTAVEIS = frozenset({429, 500, 502, 503, 504})

# 6 tentativas com base 2.0 esperam 2, 4, 8, 16 e 32 s entre elas, perto do
# retry que o agregador tinha antes da política do core. Menos tentativas
# contariam como instabilidade da API o que antes passava na quarta.
_PERFIS_HTTP: dict[str, RequestPolicy] = {
    PERFIL_LISTAGEM: RequestPolicy(
        timeout=30.0,
        max_retries=6,
        base_backoff=2.0,
        retryable_statuses=_STATUS_RETENTAVEIS,
        retry_on_timeout=True,
    ),
    PERFIL_DOCUMENTO: RequestPolicy(
        timeout=60.0,
        max_retries=6,
        base_backoff=2.0,
        retryable_statuses=_STATUS_RETENTAVEIS,
        retry_on_timeout=True,
    ),
}


def _buscar_conteudo(
    buscar: Callable[..., Any],
    request_fn: RequestFn,
    cnj_limpo: str,
    id_documento: str,
    base_url: str,
) -> tuple[Any, str | None]:
    """Busca texto ou binario; devolve ``(conteudo, None)`` ou ``(None, motivo)``.

    O 401 propaga (ver ``e_token_invalido``). Uma resposta 200 com corpo vazio
    chega como ``""`` ou ``b""`` e não é falha.
    """
    try:
        return buscar(request_fn, cnj_limpo, id_documento, base_url=base_url), None
    except EXCECOES_DE_FALHA_POR_LINHA as exc:
        if e_token_invalido(exc):
            raise
        return None, motivo_falha(exc)


_COLUNAS_CPOPG_VAZIA = (
    "numero_processo",
    "id",
    "sigla_tribunal",
    "segmento_justica",
    "nivel_sigilo",
    "data_atualizacao",
    "detalhes",
)


def _linha_cpopg_vazia(cnj: str, status_consulta: str) -> dict[str, Any]:
    """Linha de ``cpopg`` sem tramitacao: processo ausente ou consulta que falhou."""
    return {"processo": cnj, **dict.fromkeys(_COLUNAS_CPOPG_VAZIA), "status_consulta": status_consulta}


def _linha_processo(cnj: str) -> dict[str, Any]:
    """Linha de falha de movimentos e partes: so o processo, o motivo entra depois."""
    return {"processo": cnj}


def _linha_documentos(cnj: str) -> dict[str, Any]:
    """Linha de falha de :meth:`PdpjScraper.documentos`.

    Leva ``id_documento`` vazio para que o DataFrame continue aceito por
    ``download_documents`` mesmo quando todos os processos falharam; a linha
    sem id é pulada lá.
    """
    return {"processo": cnj, "id_documento": None}


class PdpjScraper(HTTPScraper):
    """Raspador para a API DATALAKE - Processos do PDPJ.

    A API consome JWT do SSO PJe (mesmo provedor do JusBR), entao o uso
    tipico e: obter o token via portal do PDPJ logado, chamar
    :meth:`auth` e usar os endpoints de consulta/download.

    Os metodos por processo (:meth:`cpopg`, :meth:`documentos`,
    :meth:`movimentos`, :meth:`partes` e :meth:`existe` com lista) e
    :meth:`download_documents` devolvem uma linha de falha quando a requisicao
    de um item falha, com o motivo na coluna ``motivo_falha`` (vocabulario em
    :mod:`juscraper.core.failures`) e um ``UserWarning`` agregado ao fim. O 401
    interrompe a coleta. Metodos sem linha por item (:meth:`existe` com
    ``str``, :meth:`contar` e :meth:`pesquisa`) levantam o erro.

    As requisicoes usam os perfis ``"listagem"`` e ``"documento"`` de
    :class:`~juscraper.core.http.RequestPolicy`, ajustaveis no construtor com
    ``politica=``.
    """

    perfis_http: ClassVar[Mapping[str, RequestPolicy]] = _PERFIS_HTTP

    BASE_URL = BASE_URL

    INPUT_AUTH = InputAuthPdpj
    INPUT_CPOPG = InputCnjPdpj
    INPUT_DOCUMENTOS = InputCnjPdpj
    INPUT_MOVIMENTOS = InputCnjPdpj
    INPUT_PARTES = InputCnjPdpj
    INPUT_EXISTE = InputCnjPdpj
    INPUT_PESQUISA = InputPesquisaPdpj
    INPUT_CONTAR = InputContarPdpj
    INPUT_DOWNLOAD_DOCUMENTS = InputDownloadDocumentsPdpj

    def __init__(
        self,
        verbose: int = 0,
        download_path: str | None = None,
        sleep_time: float = 0.5,
        token: str | None = None,
        politica: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> None:
        """Cria o raspador; ``token`` passa por :meth:`auth`.

        Args:
            verbose: Nivel de log.
            download_path: Diretorio de download.
            sleep_time: Pausa entre requisicoes de itens, em segundos.
            token: JWT opcional, validado por :meth:`auth`.
            politica: Ajustes por campo dos perfis ``"listagem"`` e
                ``"documento"``, como ``{"documento": {"timeout": 20}}``. O
                que nao for passado fica como o raspador declara.
        """
        super().__init__(
            "pdpj",
            verbose=verbose,
            download_path=download_path,
            sleep_time=sleep_time,
            politica=politica,
        )
        self.token: str | None = None
        if token:
            self.auth(token)

    def _configure_session(self, session: requests.Session) -> None:
        # A API recusa User-Agent que não é de navegador; troca o default do
        # HTTPScraper (``juscraper/<version>``).
        session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
        })

    def auth(self, token: str) -> bool:
        """Define o JWT usado em todas as chamadas autenticadas.

        O token passa por :func:`juscraper.core.auth.validar_jwt`, que recusa
        token malformado ou vencido antes do primeiro uso. O conteudo do JWT
        nao e logado.

        Raises:
            ValueError: Quando o token e malformado ou ja expirou. O token e o
                header anteriores ficam como estavam.
        """
        InputAuthPdpj(token=token)
        validar_jwt(token)
        self.token = token
        self.session.headers["Authorization"] = f"Bearer {token}"
        if self.verbose:
            logger.info("PDPJ: token JWT aceito.")
        return True

    def _check_auth(self) -> None:
        if not self.token:
            raise RuntimeError(
                "Autenticacao necessaria. Chame PdpjScraper.auth(token) primeiro."
            )

    @staticmethod
    def _normalize_cnj_input(id_cnj: str | list[str]) -> list[str]:
        InputCnjPdpj(id_cnj=id_cnj)
        items = [id_cnj] if isinstance(id_cnj, str) else list(id_cnj)
        return [clean_cnj(c) for c in items]

    def _coletar_por_processo(
        self,
        origem: str,
        cnjs: Iterable[str],
        buscar: Callable[..., Any],
        montar: Callable[[Any, str], list[dict[str, Any]]],
        linha_falha: Callable[[str], dict[str, Any]],
    ) -> pd.DataFrame:
        """Uma requisicao por CNJ; a que falha vira linha com ``motivo_falha``.

        ``montar`` transforma a resposta nas linhas do processo e
        ``linha_falha`` da as colunas da linha de um processo cuja requisicao
        falhou. O 401 interrompe, com as falhas anteriores numa nota do erro;
        exceção fora de ``EXCECOES_DE_FALHA_POR_LINHA`` propaga como veio.
        """
        rows: list[dict[str, Any]] = []
        falhas: list[str] = []
        try:
            for cnj in cnjs:
                try:
                    data = buscar(self._request_with_retry, cnj, base_url=self.BASE_URL)
                except EXCECOES_DE_FALHA_POR_LINHA as exc:
                    if e_token_invalido(exc):
                        raise
                    motivo = motivo_falha(exc)
                    falhas.append(f"processo {cnj}: {motivo}")
                    rows.append({**linha_falha(cnj), COLUNA_MOTIVO_FALHA: motivo})
                else:
                    rows.extend({**row, COLUNA_MOTIVO_FALHA: None} for row in montar(data, cnj))
                if self.sleep_time:
                    time.sleep(self.sleep_time)
        except requests.HTTPError as erro:
            anotar_falhas_anteriores(erro, falhas, _ITEM_CONSULTA)
            raise
        # stacklevel 4: warn -> avisar_falhas -> este metodo -> metodo publico -> usuario.
        avisar_falhas(falhas, origem, _ITEM_CONSULTA, stacklevel=4)
        df = pd.DataFrame(rows)
        # O pandas ordena as colunas pela chegada, e a linha de falha tem menos
        # colunas que a de sucesso: se ela viesse primeiro, as colunas dela
        # (``id_documento``, o motivo) passariam na frente das de conteúdo, e a
        # ordem dependeria de qual processo falhou. As linhas de sucesso dão a
        # ordem, as colunas só da linha de falha vêm depois e o motivo por último.
        ordem = list(dict.fromkeys(
            coluna
            for row in rows if row[COLUNA_MOTIVO_FALHA] is None
            for coluna in row if coluna != COLUNA_MOTIVO_FALHA
        ))
        ordem += [c for c in df.columns if c not in ordem and c != COLUNA_MOTIVO_FALHA]
        if COLUNA_MOTIVO_FALHA in df.columns:
            ordem.append(COLUNA_MOTIVO_FALHA)
        return df[ordem]

    def existe(self, id_cnj: str | list[str]) -> bool | pd.DataFrame:
        """Checa presenca de processo(s) no Data Lake.

        Args:
            id_cnj: Numero CNJ unico (``str``) ou lista de numeros.

        Returns:
            ``bool`` quando ``id_cnj`` e ``str``; ``pd.DataFrame`` com
            colunas ``processo``, ``existe`` e ``motivo_falha`` quando e
            ``list``. Na lista, o processo cuja consulta falhou sai com
            ``existe=None`` e o motivo.

        Raises:
            requests.HTTPError: No 401, e com ``str`` em qualquer erro HTTP.
            RetryExhaustedError, requests.Timeout, requests.ConnectionError,
            InvalidJSONResponseError: Com ``str``, quando a consulta falha;
                a resposta sem ``true``/``false`` levanta o ultimo.

        See also:
            :class:`InputCnjPdpj` -- schema pydantic.
        """
        self._check_auth()
        cnjs = self._normalize_cnj_input(id_cnj)
        if isinstance(id_cnj, str):
            return fetch_processo_existe(self._request_with_retry, cnjs[0], base_url=self.BASE_URL)
        return self._coletar_por_processo(
            "PdpjScraper.existe",
            cnjs,
            fetch_processo_existe,
            lambda existe, cnj: [{"processo": cnj, "existe": existe}],
            lambda cnj: {"processo": cnj, "existe": None},
        )

    def cpopg(self, id_cnj: str | list[str]) -> pd.DataFrame:
        """Recupera os detalhes de processo(s) via API ``/processos/{n}``.

        Args:
            id_cnj: Numero CNJ ou lista de numeros.

        Returns:
            DataFrame com uma linha por tramitacao do processo. Colunas
            principais: ``processo`` (CNJ pesquisado, dignos de digito),
            ``numero_processo`` (formatado pela API), ``sigla_tribunal``,
            ``segmento_justica``, ``data_atualizacao``, ``detalhes``
            (dict com a resposta completa) e ``motivo_falha``. A API que
            responde lista vazia gera uma linha com
            ``status_consulta="Nao encontrado"``; a consulta que falha,
            inclusive com 404, gera uma linha com ``status_consulta`` igual a
            :data:`juscraper.core.failures.STATUS_CONSULTA_FALHA` e o motivo.

        Raises:
            requests.HTTPError: No 401 (token ausente, expirado ou invalido),
                com as falhas anteriores numa nota do erro.

        Warns:
            UserWarning: Quando pelo menos uma consulta falhou.

        See also:
            :class:`InputCnjPdpj` -- schema pydantic.
        """
        self._check_auth()
        return self._coletar_por_processo(
            "PdpjScraper.cpopg",
            self._normalize_cnj_input(id_cnj),
            fetch_processo_detalhes,
            lambda detalhes, cnj: (
                [build_processo_row(det, cnj) for det in detalhes]
                if detalhes
                else [_linha_cpopg_vazia(cnj, "Nao encontrado")]
            ),
            lambda cnj: _linha_cpopg_vazia(cnj, STATUS_CONSULTA_FALHA),
        )

    def documentos(self, id_cnj: str | list[str]) -> pd.DataFrame:
        """Lista documentos do(s) processo(s) (sem baixar conteudo).

        O processo cuja consulta falha sai numa linha so, com ``processo`` e
        ``motivo_falha`` preenchidos e as demais colunas vazias. O 401
        interrompe; ver :meth:`cpopg`.
        """
        self._check_auth()
        return self._coletar_por_processo(
            "PdpjScraper.documentos",
            self._normalize_cnj_input(id_cnj),
            fetch_processo_documentos,
            build_documento_rows,
            _linha_documentos,
        )

    def movimentos(self, id_cnj: str | list[str]) -> pd.DataFrame:
        """Lista movimentos do(s) processo(s).

        Falha por processo como em :meth:`documentos`.
        """
        self._check_auth()
        return self._coletar_por_processo(
            "PdpjScraper.movimentos",
            self._normalize_cnj_input(id_cnj),
            fetch_processo_movimentos,
            build_movimento_rows,
            _linha_processo,
        )

    def partes(self, id_cnj: str | list[str]) -> pd.DataFrame:
        """Lista partes do(s) processo(s).

        Falha por processo como em :meth:`documentos`.
        """
        self._check_auth()
        return self._coletar_por_processo(
            "PdpjScraper.partes",
            self._normalize_cnj_input(id_cnj),
            fetch_processo_partes,
            build_parte_rows,
            _linha_processo,
        )

    def pesquisa(
        self,
        paginas: int | list[int] | range | None = None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """Busca profunda em ``GET /api/v1/processos`` (com paginacao).

        Args:
            paginas: Intervalo 1-based. Aceita ``int`` (``3`` -> primeiras
                3 paginas), ``list``, ``range`` ou ``None`` (todas).
            **kwargs: Filtros aceitos pelo schema
                :class:`InputPesquisaPdpj` (todos opcionais; ``None`` =
                sem filtro):

                * ``numero_processo`` (str)
                * ``numero_processo_sintetico`` (str)
                * ``id`` (str): id interno do processo no Data Lake
                * ``cpf_cnpj_parte`` (str): com formatacao
                * ``nome_parte`` (str)
                * ``polo_parte`` (str): "ATIVO" ou "PASSIVO"
                * ``situacao_parte`` (str)
                * ``nome_representante`` / ``oab_representante`` (str)
                * ``id_classe`` (str): codigos separados por virgula
                * ``id_assunto_judicial`` (str): ids separados por virgula
                * ``id_orgao_julgador`` (str | list[str])
                * ``instancia`` (str): "PRIMEIRO_GRAU"/"SEGUNDO_GRAU"/etc.
                * ``segmento_justica`` (str): "JUSTICA_FEDERAL"/"JUSTICA_ESTADUAL"/etc.
                * ``tribunal`` (str): siglas separadas por virgula (max 5)
                * ``data_atualizacao_inicio`` / ``_fim`` (str): ISO datetime
                * ``data_primeiro_ajuizamento_inicio`` / ``_fim`` (str): ISO datetime
                * ``campo_ordenacao`` (str): campo de ordenacao decrescente
                * ``itens_por_pagina`` (int): default 100, max 100

        Returns:
            DataFrame com uma linha por processo retornado.

        Raises:
            requests.HTTPError, RetryExhaustedError, requests.Timeout,
            requests.ConnectionError, InvalidJSONResponseError: Quando a
                requisicao de qualquer pagina falha. Pagina nao vira linha de
                falha, e devolver as paginas anteriores truncaria o resultado
                sem aviso.

        See also:
            :class:`InputPesquisaPdpj` -- schema pydantic e a fonte da
            verdade dos filtros aceitos.
        """
        self._check_auth()
        paginas_norm = normalize_paginas(paginas)
        try:
            inp = InputPesquisaPdpj(paginas=paginas_norm, **kwargs)
        except ValidationError as exc:
            raise_on_extra_kwargs(
                exc, "PdpjScraper.pesquisa()", schema_cls=InputPesquisaPdpj,
            )
            raise

        base_data = inp.model_dump(exclude={"paginas", "itens_por_pagina"})
        base_params = _to_query_params(base_data)
        base_params["maxElementsSize"] = inp.itens_por_pagina

        # paginacao via searchAfter: a API devolve o cursor a ser usado
        # na proxima pagina. Coletamos ate exaurir ou atingir o limite
        # solicitado pelo usuario.
        if paginas_norm is None:
            max_paginas = None
            allowed: set[int] | None = None
        elif isinstance(paginas_norm, range):
            max_paginas = paginas_norm.stop - 1
            allowed = set(paginas_norm)
        else:
            max_paginas = max(paginas_norm) if paginas_norm else 0
            allowed = set(paginas_norm)

        rows: list[dict[str, Any]] = []
        pagina = 1
        search_after: list[Any] | None = None
        while True:
            params = dict(base_params)
            if search_after is not None:
                # API espera searchAfter como string CSV: timestamp,id
                params["searchAfter"] = ",".join(str(v) for v in search_after)
            data = fetch_pesquisa(self._request_with_retry, params, base_url=self.BASE_URL)
            page_rows, search_after, _total = parse_pesquisa_response(data)
            if allowed is None or pagina in allowed:
                rows.extend(page_rows)
            if not search_after or not page_rows:
                break
            if max_paginas is not None and pagina >= max_paginas:
                break
            pagina += 1
            if self.sleep_time:
                time.sleep(self.sleep_time)
        return pd.DataFrame(rows)

    def contar(self, **kwargs: Any) -> int:
        """Total de processos que casam com os filtros (``/processos:contar``).

        Aceita o mesmo subconjunto de filtros de :meth:`pesquisa` exceto
        os relacionados a paginacao/ordenacao. Retorna ``int``.

        Raises:
            requests.HTTPError, RetryExhaustedError, requests.Timeout,
            requests.ConnectionError: Quando a requisicao falha.
            InvalidJSONResponseError: Quando a resposta nao traz um inteiro.
        """
        self._check_auth()
        try:
            inp = InputContarPdpj(**kwargs)
        except ValidationError as exc:
            raise_on_extra_kwargs(
                exc, "PdpjScraper.contar()", schema_cls=InputContarPdpj,
            )
            raise
        params = _to_query_params(inp.model_dump())
        return fetch_contar(self._request_with_retry, params, base_url=self.BASE_URL)

    def download_documents(
        self,
        base_df: pd.DataFrame,
        max_docs_per_process: int | None = None,
        with_text: bool = True,
        with_binary: bool = False,
    ) -> pd.DataFrame:
        """Baixa textos e/ou binarios dos documentos listados.

        ``base_df`` pode vir de :meth:`documentos` (uma linha por
        documento, ja com ``id_documento`` e ``numero_processo``) ou de
        :meth:`cpopg` (uma linha por processo com ``detalhes`` -- nesse
        caso a lista de documentos e extraida de
        ``detalhes['documentos']``).

        Um documento cujo download falha não interrompe a coleta: a linha
        sai com ``texto``/``_raw_texto`` e/ou ``binario`` iguais a ``None``
        e o método segue para o próximo documento. Conta como falha qualquer
        erro HTTP diferente de 401 (inclusive o 403, que a API pode devolver
        para um documento isolado, como um sigiloso, e que por isso não é
        retentado), o retry de 429/5xx/timeout esgotado e o erro de conexão.
        A coluna ``motivo_falha`` guarda o motivo, no vocabulário de
        :mod:`juscraper.core.failures`; com texto e binário, guarda o do texto
        quando o texto falhou, senão o do binário, e o ``None`` de cada coluna
        diz qual conteúdo faltou. Ao fim, um único ``UserWarning`` informa
        quantos downloads falharam e cita alguns, com processo, documento,
        conteúdo e motivo. O 401 propaga, porque token inválido atinge o lote
        inteiro.

        Args:
            base_df: DataFrame fonte das chamadas.
            max_docs_per_process: Limite de linhas devolvidas por processo,
                na ordem de ``base_df``. Linhas sem ``id_documento`` sao
                puladas sem ocupar vaga do limite; um documento cujo
                download falhou ocupa vaga, como no JusBR, porque sua linha
                sai no resultado (com conteúdo ``None``) e a requisição já
                foi feita. ``None`` = sem limite; ``0`` devolve DataFrame vazio
                sem fazer requisicao.
            with_text: Se ``True`` (default), baixa o texto via
                ``/documentos/{id}/texto``.
            with_binary: Se ``True``, baixa o binario via
                ``/documentos/{id}/binario``. Default ``False`` para nao
                consumir banda quando o usuario so quer texto.

        Returns:
            DataFrame com uma linha por documento. Inclui colunas
            ``texto`` e ``binario`` (quando solicitados), ``None`` nos
            documentos cujo download falhou, e ``motivo_falha``.

        Raises:
            ValidationError: Quando ``base_df`` nao e um DataFrame ou
                ``max_docs_per_process`` e negativo.
            ValueError: Quando ``with_text`` e ``with_binary`` sao ambos
                ``False``, ou quando ``base_df`` nao tem coluna
                ``id_documento`` nem ``detalhes``.
            requests.HTTPError: Quando a API responde 401 (token ausente,
                expirado ou inválido). O erro atinge o lote inteiro, então
                propaga e as linhas já baixadas se perdem; as falhas
                anteriores ao 401 vão numa nota do próprio erro
                (``__notes__``), não no ``UserWarning``.

        Warns:
            UserWarning: Quando pelo menos um download de documento falhou.
                Um aviso por chamada, com a contagem e alguns exemplos,
                emitido só quando a coleta termina.

        See also:
            :class:`InputDownloadDocumentsPdpj`: schema pydantic e fonte
            da verdade dos parametros aceitos.
        """
        self._check_auth()
        # Validacao via schema -- garante que kwargs desconhecidos viram TypeError.
        try:
            inp = InputDownloadDocumentsPdpj(
                base_df=base_df,
                max_docs_per_process=max_docs_per_process,
                with_text=with_text,
                with_binary=with_binary,
            )
        except ValidationError as exc:
            raise_on_extra_kwargs(
                exc,
                "PdpjScraper.download_documents()",
                schema_cls=InputDownloadDocumentsPdpj,
            )
            raise
        base_df = inp.base_df
        max_docs_per_process = inp.max_docs_per_process
        with_text = inp.with_text
        with_binary = inp.with_binary
        if not with_text and not with_binary:
            raise ValueError(
                "Pelo menos um de 'with_text' ou 'with_binary' deve ser True."
            )

        docs_df = self._coerce_to_documentos_df(base_df)
        if docs_df.empty:
            return pd.DataFrame()

        rows: list[dict[str, Any]] = []
        falhas: list[str] = []
        try:
            for processo, grupo in docs_df.groupby("processo", sort=False):
                rows.extend(self._download_process_documents(
                    grupo, processo, max_docs_per_process, with_text, with_binary, falhas,
                ))
        except requests.HTTPError as erro:
            anotar_falhas_anteriores(erro, falhas, _ITEM_DOWNLOAD)
            raise
        avisar_falhas(falhas, "PdpjScraper.download_documents", _ITEM_DOWNLOAD)
        return pd.DataFrame(rows)

    def _download_process_documents(
        self,
        grupo: pd.DataFrame,
        processo: Any,
        max_docs_per_process: int | None,
        with_text: bool,
        with_binary: bool,
        falhas: list[str],
    ) -> list[dict[str, Any]]:
        """Baixa os documentos de um processo ate o limite de linhas devolvidas.

        O limite e conferido antes de cada documento, e nao com ``head(N)``
        sobre ``grupo``: assim uma linha sem ``id_documento``, que
        :meth:`_download_document` pula, nao ocupa uma vaga do limite.
        """
        rows: list[dict[str, Any]] = []
        for _, doc_row in grupo.iterrows():
            if max_docs_per_process is not None and len(rows) >= max_docs_per_process:
                break
            row = self._download_document(doc_row, processo, with_text, with_binary, falhas)
            if row is not None:
                rows.append(row)
        return rows

    def _download_document(
        self,
        doc_row: pd.Series,
        processo: Any,
        with_text: bool,
        with_binary: bool,
        falhas: list[str],
    ) -> dict[str, Any] | None:
        """Baixa os conteúdos selecionados para uma linha de documento.

        Falha de download de texto ou binario vira ``None`` na coluna e uma
        entrada em ``falhas``; o 401 propaga (ver ``e_token_invalido``).
        """
        row = cast(dict[str, Any], doc_row.to_dict())
        id_documento = row.get("id_documento")
        numero_processo = row.get("numero_processo") or processo
        # ``pd.isna`` cobre o ``NaN`` que o pandas põe no id ausente; ``NaN`` é
        # truthy e passaria por ``not id_documento`` como id válido.
        if pd.isna(id_documento) or id_documento == "":
            # A linha de falha de ``documentos`` não tem id e já foi contada no
            # aviso daquela chamada; o log fica para o documento que veio sem id.
            if pd.isna(row.get(COLUNA_MOTIVO_FALHA)):
                logger.warning(
                    "Documento sem id_documento no processo %s; pulando.",
                    numero_processo,
                )
            return None
        cnj_clean = clean_cnj(str(numero_processo))
        descricao = f"processo {numero_processo}, documento {id_documento}"
        motivo_texto = motivo_binario = None
        if with_text:
            raw, motivo_texto = _buscar_conteudo(
                fetch_documento_texto, self._request_with_retry, cnj_clean, str(id_documento), self.BASE_URL,
            )
            if motivo_texto is not None:
                falhas.append(f"{descricao}, texto: {motivo_texto}")
            row["texto"] = clean_document_text(raw)
            row["_raw_texto"] = raw
        if with_binary:
            row["binario"], motivo_binario = _buscar_conteudo(
                fetch_documento_binario, self._request_with_retry, cnj_clean, str(id_documento), self.BASE_URL,
            )
            if motivo_binario is not None:
                falhas.append(f"{descricao}, binario: {motivo_binario}")
        # Uma coluna de motivo para duas requisições: o texto tem precedência.
        row[COLUNA_MOTIVO_FALHA] = motivo_texto if motivo_texto is not None else motivo_binario
        if self.sleep_time:
            time.sleep(self.sleep_time)
        return row

    def _coerce_to_documentos_df(self, base_df: pd.DataFrame) -> pd.DataFrame:
        """Aceita tanto o DataFrame de :meth:`documentos` quanto o de :meth:`cpopg`.

        No primeiro caso o df ja vem no shape esperado. No segundo, cada
        linha tem ``detalhes['documentos']`` que precisamos achatar antes
        de baixar conteudo.
        """
        if base_df.empty:
            return pd.DataFrame()
        if "id_documento" in base_df.columns:
            return base_df
        if "detalhes" not in base_df.columns:
            raise ValueError(
                "base_df precisa ter coluna 'id_documento' (de PdpjScraper.documentos) "
                "ou 'detalhes' (de PdpjScraper.cpopg)."
            )
        rows: list[dict[str, Any]] = []
        for _, linha in base_df.iterrows():
            cnj = linha.get("processo")
            detalhes = linha.get("detalhes") or {}
            if not isinstance(detalhes, dict):
                continue
            for document in _iter_documents(detalhes):
                row = _document_to_row(document, cnj, detalhes.get("numeroProcesso"))
                if row is not None:
                    rows.append(row)
        return pd.DataFrame(rows)
