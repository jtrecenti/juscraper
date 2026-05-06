"""Client publico do agregador PDPJ.

Wrapper sobre a API ``DATALAKE - API Processos`` do PDPJ
(``https://api-processo-integracao.data-lake.pdpj.jus.br/processo-api/api/v1``).
A autenticacao e via JWT no header ``Authorization: Bearer <token>``.
"""
from __future__ import annotations

import logging
import time
from typing import Any

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
from .schemas import (
    InputAuthPdpj,
    InputCnjPdpj,
    InputContarPdpj,
    InputDownloadDocumentsPdpj,
    InputPesquisaPdpj,
)

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
            decoded = jwt.decode(
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
            logger.info("PDPJ: token JWT aceito (sub=%s).", decoded.get("sub"))
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
        """Verifica se o(s) processo(s) existe(m) no Data Lake.

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
                for det in detalhes:
                    rows.append(build_processo_row(det, cnj))
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

        Args:
            base_df: DataFrame fonte das chamadas.
            max_docs_per_process: Limite de documentos baixados por
                processo. ``None`` = sem limite.
            with_text: Se ``True`` (default), baixa o texto via
                ``/documentos/{id}/texto``.
            with_binary: Se ``True``, baixa o binario via
                ``/documentos/{id}/binario``. Default ``False`` para nao
                consumir banda quando o usuario so quer texto.

        Returns:
            DataFrame com uma linha por documento. Inclui colunas
            ``texto`` e ``binario`` (quando solicitados).

        Raises:
            ValueError: Quando ``with_text`` e ``with_binary`` sao ambos
                ``False``.
        """
        self._check_auth()
        # Validacao via schema -- garante que kwargs desconhecidos viram TypeError.
        try:
            InputDownloadDocumentsPdpj(
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
        if not with_text and not with_binary:
            raise ValueError(
                "Pelo menos um de 'with_text' ou 'with_binary' deve ser True."
            )

        docs_df = self._coerce_to_documentos_df(base_df)
        if docs_df.empty:
            return pd.DataFrame()

        rows: list[dict[str, Any]] = []
        for processo, grupo in docs_df.groupby("processo", sort=False):
            limite = (
                len(grupo)
                if max_docs_per_process is None
                else min(max_docs_per_process, len(grupo))
            )
            for _, doc_row in grupo.head(limite).iterrows():
                row = doc_row.to_dict()
                id_documento = row.get("id_documento")
                numero_processo = row.get("numero_processo") or processo
                if not id_documento:
                    logger.warning(
                        "Documento sem id_documento no processo %s; pulando.",
                        numero_processo,
                    )
                    continue
                cnj_clean = clean_cnj(str(numero_processo))
                if with_text:
                    raw = fetch_documento_texto(
                        self.session, cnj_clean, str(id_documento),
                        base_url=self.BASE_URL,
                    )
                    row["texto"] = clean_document_text(raw)
                    row["_raw_texto"] = raw
                if with_binary:
                    row["binario"] = fetch_documento_binario(
                        self.session, cnj_clean, str(id_documento),
                        base_url=self.BASE_URL,
                    )
                rows.append(row)
                if self.sleep_time:
                    time.sleep(self.sleep_time)
        return pd.DataFrame(rows)

    def _coerce_to_documentos_df(self, base_df: pd.DataFrame) -> pd.DataFrame:
        """Aceita tanto o DataFrame de :meth:`documentos` quanto o de :meth:`cpopg`.

        No primeiro caso o df ja vem no shape esperado. No segundo, cada
        linha tem ``detalhes['documentos']`` que precisamos achatar antes
        de baixar conteudo.
        """
        if base_df is None or base_df.empty:
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
            # Os documentos podem estar no topo (legacy) ou aninhados em
            # tramitacoes[*].documentos (shape atual da PDPJ).
            doc_lists: list[list[dict[str, Any]]] = []
            top_docs = detalhes.get("documentos")
            if isinstance(top_docs, list):
                doc_lists.append(top_docs)
            for tram in detalhes.get("tramitacoes", []) or []:
                if isinstance(tram, dict) and isinstance(tram.get("documentos"), list):
                    doc_lists.append(tram["documentos"])

            for docs in doc_lists:
                for doc in docs:
                    if not isinstance(doc, dict):
                        continue
                    arquivo = doc.get("arquivo") or {}
                    tipo = doc.get("tipo") or {}
                    rows.append({
                        "processo": cnj,
                        "numero_processo": detalhes.get("numeroProcesso"),
                        "id_documento": doc.get("id"),
                        "id_codex": doc.get("idCodex"),
                        "sequencia": doc.get("sequencia"),
                        "data_juntada": doc.get("dataHoraJuntada"),
                        "nome": doc.get("nome"),
                        "nivel_sigilo": doc.get("nivelSigilo"),
                        "tipo_codigo": tipo.get("codigo"),
                        "tipo_nome": tipo.get("nome"),
                        "arquivo_id": arquivo.get("id"),
                        "arquivo_tipo": arquivo.get("tipo"),
                        "arquivo_tamanho": arquivo.get("tamanho"),
                        "arquivo_paginas": arquivo.get("quantidadePaginas"),
                    })
        return pd.DataFrame(rows)
