"""Client publico do agregador PDPJ.

Wrapper sobre a API ``DATALAKE - API Processos`` do PDPJ
(``https://api-processo-integracao.data-lake.pdpj.jus.br/processo-api/api/v1``).
A autenticacao e via JWT no header ``Authorization: Bearer <token>``.
"""
from __future__ import annotations

import logging
import time
import warnings
from collections.abc import Callable, Iterator
from typing import Any, cast

import jwt
import pandas as pd
import requests
from pydantic import ValidationError

from ...core.base import BaseScraper
from ...utils.cnj import clean_cnj
from ...utils.params import normalize_paginas, raise_on_extra_kwargs
from .download import (
    BASE_URL,
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


# 401/403 indicam token ausente, expirado ou sem permissao. Esse erro vale
# para todos os documentos do lote, entao propaga em vez de virar linha vazia:
# engolir o erro produziria um DataFrame inteiro de ``texto=None``, sem que o
# usuario percebesse que precisa renovar o token.
_STATUS_DE_AUTENTICACAO = frozenset({401, 403})

# Quantas falhas o aviso agregado de :meth:`PdpjScraper.download_documents`
# cita por extenso; as demais entram so na contagem.
_EXEMPLOS_NO_AVISO = 3


def _buscar_conteudo(
    buscar: Callable[..., Any],
    session: requests.Session,
    cnj_limpo: str,
    id_documento: str,
    base_url: str,
    falhas: list[str],
    descricao: str,
) -> Any:
    """Busca texto ou binario; em falha, anota ``descricao`` e devolve ``None``.

    O ``None`` devolvido por ``fetch_documento_*`` so aparece quando
    ``_request_with_retry`` desistiu (retry de 429/503/timeout esgotado ou
    erro de conexao): uma resposta 200 com corpo vazio chega como ``""`` ou
    ``b""``. Por isso ``None`` conta como falha, e nao como documento vazio.
    """
    try:
        conteudo = buscar(session, cnj_limpo, id_documento, base_url=base_url)
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status in _STATUS_DE_AUTENTICACAO:
            raise
        falhas.append(f"{descricao}: HTTP {status}")
        return None
    if conteudo is None:
        falhas.append(f"{descricao}: sem resposta (retry esgotado ou erro de conexão)")
    return conteudo


def _avisar_falhas(falhas: list[str]) -> None:
    """Emite um unico ``UserWarning`` com a contagem e alguns exemplos."""
    if not falhas:
        return
    exemplos = falhas[:_EXEMPLOS_NO_AVISO]
    if len(falhas) > len(exemplos):
        exemplos = [*exemplos, f"e mais {len(falhas) - len(exemplos)}"]
    lista = "; ".join(exemplos)
    warnings.warn(
        f"PdpjScraper.download_documents: {len(falhas)} download(s) de documento falharam, "
        f"e as linhas correspondentes saem com o conteúdo None. Falhas: {lista}.",
        UserWarning,
        stacklevel=3,
    )


class PdpjScraper(BaseScraper):
    """Raspador para a API DATALAKE - Processos do PDPJ.

    A API consome JWT do SSO PJe (mesmo provedor do JusBR), entao o uso
    tipico e: obter o token via portal do PDPJ logado, chamar
    :meth:`auth` e usar os endpoints de consulta/download.
    """

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
    ) -> None:
        super().__init__("pdpj")
        self.set_verbose(verbose)
        self.set_download_path(download_path)
        self.sleep_time = sleep_time
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
        })
        self.token: str | None = None
        if token:
            self.auth(token)

    def auth(self, token: str) -> bool:
        """Define o JWT usado em todas as chamadas autenticadas.

        Decodifica sem verificar assinatura (algoritmo gerado pelo PDPJ)
        para validar o formato e capturar tokens expirados antes de
        tentar usar.

        Raises:
            ValueError: Quando o token e malformado ou ja expirou.
        """
        InputAuthPdpj(token=token)
        try:
            # Decodifica so para validar formato/expiracao; o conteudo do JWT
            # nao e logado (hardening, #270).
            jwt.decode(
                token,
                options={"verify_signature": False, "verify_aud": False},
                algorithms=["RS256", "HS256", "ES256", "none"],
            )
        except jwt.ExpiredSignatureError as exc:
            raise ValueError("Token JWT expirado.") from exc
        except jwt.InvalidTokenError as exc:
            raise ValueError(f"Token JWT invalido: {exc}") from exc

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

    def existe(self, id_cnj: str | list[str]) -> bool | pd.DataFrame:
        """Checa presenca de processo(s) no Data Lake.

        Args:
            id_cnj: Numero CNJ unico (``str``) ou lista de numeros.

        Returns:
            ``bool`` quando ``id_cnj`` e ``str``; ``pd.DataFrame`` com
            colunas ``processo`` e ``existe`` quando e ``list``.

        See also:
            :class:`InputCnjPdpj` -- schema pydantic.
        """
        self._check_auth()
        cnjs = self._normalize_cnj_input(id_cnj)
        results: list[dict[str, Any]] = []
        for cnj in cnjs:
            existe = fetch_processo_existe(self.session, cnj, base_url=self.BASE_URL)
            results.append({"processo": cnj, "existe": existe})
            if self.sleep_time:
                time.sleep(self.sleep_time)
        if isinstance(id_cnj, str):
            return bool(results[0]["existe"])
        return pd.DataFrame(results)

    def cpopg(self, id_cnj: str | list[str]) -> pd.DataFrame:
        """Recupera os detalhes de processo(s) via API ``/processos/{n}``.

        Args:
            id_cnj: Numero CNJ ou lista de numeros.

        Returns:
            DataFrame com uma linha por tramitacao do processo. Colunas
            principais: ``processo`` (CNJ pesquisado, dignos de digito),
            ``numero_processo`` (formatado pela API), ``sigla_tribunal``,
            ``segmento_justica``, ``data_atualizacao``, ``detalhes``
            (dict com a resposta completa).

        See also:
            :class:`InputCnjPdpj` -- schema pydantic.
        """
        self._check_auth()
        cnjs = self._normalize_cnj_input(id_cnj)
        rows: list[dict[str, Any]] = []
        for cnj in cnjs:
            detalhes = fetch_processo_detalhes(self.session, cnj, base_url=self.BASE_URL)
            if not detalhes:
                rows.append({
                    "processo": cnj,
                    "numero_processo": None,
                    "id": None,
                    "sigla_tribunal": None,
                    "segmento_justica": None,
                    "nivel_sigilo": None,
                    "data_atualizacao": None,
                    "detalhes": None,
                    "status_consulta": "Nao encontrado",
                })
            else:
                rows.extend(build_processo_row(det, cnj) for det in detalhes)
            if self.sleep_time:
                time.sleep(self.sleep_time)
        return pd.DataFrame(rows)

    def documentos(self, id_cnj: str | list[str]) -> pd.DataFrame:
        """Lista documentos do(s) processo(s) (sem baixar conteudo)."""
        self._check_auth()
        cnjs = self._normalize_cnj_input(id_cnj)
        rows: list[dict[str, Any]] = []
        for cnj in cnjs:
            data = fetch_processo_documentos(self.session, cnj, base_url=self.BASE_URL)
            rows.extend(build_documento_rows(data, cnj))
            if self.sleep_time:
                time.sleep(self.sleep_time)
        return pd.DataFrame(rows)

    def movimentos(self, id_cnj: str | list[str]) -> pd.DataFrame:
        """Lista movimentos do(s) processo(s)."""
        self._check_auth()
        cnjs = self._normalize_cnj_input(id_cnj)
        rows: list[dict[str, Any]] = []
        for cnj in cnjs:
            data = fetch_processo_movimentos(self.session, cnj, base_url=self.BASE_URL)
            rows.extend(build_movimento_rows(data, cnj))
            if self.sleep_time:
                time.sleep(self.sleep_time)
        return pd.DataFrame(rows)

    def partes(self, id_cnj: str | list[str]) -> pd.DataFrame:
        """Lista partes do(s) processo(s)."""
        self._check_auth()
        cnjs = self._normalize_cnj_input(id_cnj)
        rows: list[dict[str, Any]] = []
        for cnj in cnjs:
            data = fetch_processo_partes(self.session, cnj, base_url=self.BASE_URL)
            rows.extend(build_parte_rows(data, cnj))
            if self.sleep_time:
                time.sleep(self.sleep_time)
        return pd.DataFrame(rows)

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
            data = fetch_pesquisa(self.session, params, base_url=self.BASE_URL)
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
        total = fetch_contar(self.session, params, base_url=self.BASE_URL)
        return total or 0

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

        Um documento cujo download falha (erro HTTP que nao seja 401/403,
        ou retry de 429/503/timeout esgotado) nao interrompe a coleta: a
        linha sai com ``texto``/``_raw_texto`` e/ou ``binario`` iguais a
        ``None`` e o metodo segue para o proximo documento. Ao fim, um unico
        ``UserWarning`` informa quantos downloads falharam e cita alguns,
        com processo, documento e motivo (status HTTP ou retry esgotado).

        Args:
            base_df: DataFrame fonte das chamadas.
            max_docs_per_process: Limite de linhas devolvidas por processo,
                na ordem de ``base_df``. Linhas sem ``id_documento`` sao
                puladas sem ocupar vaga do limite; um documento cujo
                download falhou ocupa vaga, porque sua linha sai no
                resultado (com conteudo ``None``) e a requisicao ja foi
                feita. ``None`` = sem limite; ``0`` devolve DataFrame vazio
                sem fazer requisicao.
            with_text: Se ``True`` (default), baixa o texto via
                ``/documentos/{id}/texto``.
            with_binary: Se ``True``, baixa o binario via
                ``/documentos/{id}/binario``. Default ``False`` para nao
                consumir banda quando o usuario so quer texto.

        Returns:
            DataFrame com uma linha por documento. Inclui colunas
            ``texto`` e ``binario`` (quando solicitados), ``None`` nos
            documentos cujo download falhou.

        Raises:
            ValidationError: Quando ``base_df`` nao e um DataFrame ou
                ``max_docs_per_process`` e negativo.
            ValueError: Quando ``with_text`` e ``with_binary`` sao ambos
                ``False``, ou quando ``base_df`` nao tem coluna
                ``id_documento`` nem ``detalhes``.
            requests.HTTPError: Quando a API responde 401 ou 403 (token
                expirado ou sem permissao). O erro atinge o lote inteiro,
                entao propaga e as linhas ja baixadas se perdem.

        Warns:
            UserWarning: Quando pelo menos um download de documento falhou.
                Um aviso por chamada, com a contagem e alguns exemplos.

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
        for processo, grupo in docs_df.groupby("processo", sort=False):
            rows.extend(self._download_process_documents(
                grupo, processo, max_docs_per_process, with_text, with_binary, falhas,
            ))
        _avisar_falhas(falhas)
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
        entrada em ``falhas``; 401/403 propagam (ver
        ``_STATUS_DE_AUTENTICACAO``).
        """
        row = cast(dict[str, Any], doc_row.to_dict())
        id_documento = row.get("id_documento")
        numero_processo = row.get("numero_processo") or processo
        if not id_documento:
            logger.warning(
                "Documento sem id_documento no processo %s; pulando.",
                numero_processo,
            )
            return None
        cnj_clean = clean_cnj(str(numero_processo))
        descricao = f"processo {numero_processo}, documento {id_documento}"
        if with_text:
            raw = _buscar_conteudo(
                fetch_documento_texto, self.session, cnj_clean, str(id_documento),
                self.BASE_URL, falhas, f"{descricao}, texto",
            )
            row["texto"] = clean_document_text(raw)
            row["_raw_texto"] = raw
        if with_binary:
            row["binario"] = _buscar_conteudo(
                fetch_documento_binario, self.session, cnj_clean, str(id_documento),
                self.BASE_URL, falhas, f"{descricao}, binario",
            )
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
