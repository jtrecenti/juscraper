"""Cliente público do JusBR para a Plataforma Digital do Poder Judiciário."""

import logging
import time
import urllib
from typing import Any, TypeAlias

import browser_cookie3
import jwt
import numpy as np
import pandas as pd
import requests
from pydantic import ValidationError

from ...core.http import HTTPScraper
from ...utils.cnj import clean_cnj
from ...utils.params import raise_on_extra_kwargs
from .download import USER_AGENT, fetch_document_binary, fetch_document_text, fetch_process_details, fetch_process_list
from .parse import clean_document_text, parse_process_details_response, parse_process_list_response
from .schemas import InputAuthJusBR, InputCPOPGJusBR, InputDownloadDocumentsJusBR

logger = logging.getLogger(__name__)

_DocumentMetadata: TypeAlias = dict[str, Any]
_DocumentDataRow: TypeAlias = dict[str, Any]

_PREFERRED_DOCUMENT_COLUMNS = (
    'numero_processo', 'idDocumento', 'idCodex', 'sequencia', 'descricao', 'nome',
    'tipoDocumento', 'tipo', 'dataHoraJuntada', 'dataJuntada', 'nivelSigilo',
    'hrefTexto', 'hrefBinario', 'texto', '_raw_text_api', '_raw_binary_api',
)


def _metadata_is_empty(metadata: Any) -> bool:
    """Testa vazio sem avaliar ``ndarray`` como booleano ambíguo."""
    if isinstance(metadata, np.ndarray):
        return bool(metadata.size == 0)
    return not bool(metadata)


def _coerce_document_metadata_list(
    metadata: Any,
    numero_processo: str,
    detalhes: dict[str, Any],
) -> list[_DocumentMetadata]:
    """Normaliza a coleção externa e elimina itens sem shape de metadata."""
    if isinstance(metadata, np.ndarray):
        metadata = metadata.tolist()
    if not isinstance(metadata, list):
        logger.warning(
            "Lista de metadados de documentos não encontrada ou não é uma lista "
            "para o processo %s. Conteúdo de 'detalhes' (início): %s",
            numero_processo, str(detalhes)[:200]
        )
        return []

    valid_metadata = []
    for item in metadata:
        if not isinstance(item, dict):
            logger.warning(
                "Item na lista de documentos não é um dicionário para o processo %s. Item: %s",
                numero_processo, str(item)[:100]
            )
            continue
        valid_metadata.append(item)
    return valid_metadata


def _resolve_document_metadata_list(
    detalhes: dict[str, Any],
    numero_processo: str,
) -> list[_DocumentMetadata]:
    """Resolve a primeira lista não vazia na precedência exposta pelo JusBR."""
    metadata: Any = []
    dados_basicos = detalhes.get('dadosBasicos')
    if isinstance(dados_basicos, dict):
        metadata = dados_basicos.get('documentos', [])

    if _metadata_is_empty(metadata):
        direct_metadata = detalhes.get('documentos')
        if isinstance(direct_metadata, list):
            metadata = direct_metadata

    if _metadata_is_empty(metadata):
        tramitacao_atual = detalhes.get('tramitacaoAtual')
        if isinstance(tramitacao_atual, dict):
            metadata = tramitacao_atual.get('documentos', [])

    return _coerce_document_metadata_list(metadata, numero_processo, detalhes)


def _extract_document_uuid(href: Any) -> str | None:
    """Extrai o identificador situado após o segmento ``/documentos/``."""
    if not isinstance(href, str):
        return None
    _, marker, path_after_marker = href.partition('/documentos/')
    if not marker:
        return None
    document_uuid, _, _ = path_after_marker.partition('/')
    return document_uuid or None


def _log_document_text_result(
    document_uuid: str | None,
    numero_processo: str,
    raw_text: str | None,
    cleaned_text: str | None,
) -> None:
    """Registra o resultado do ramo textual sem misturá-lo à orquestração."""
    if not document_uuid:
        return
    if cleaned_text:
        logger.debug(
            "Sucesso ao baixar e limpar texto do doc UUID %s (processo %s), tamanho limpo: %d",
            document_uuid, numero_processo, len(cleaned_text),
        )
        return
    if raw_text:
        logger.debug(
            "Texto baixado para doc UUID %s (processo %s) mas resultou em "
            "None/vazio após limpeza. Raw tamanho: %d",
            document_uuid, numero_processo, len(raw_text),
        )
        return
    logger.warning(
        "Falha ao baixar texto do doc UUID %s (processo %s), ou texto vazio.",
        document_uuid, numero_processo,
    )


def _build_documents_dataframe(rows: list[_DocumentDataRow]) -> pd.DataFrame:
    """Monta o DataFrame preservando a ordem pública e os campos auxiliares."""
    if not rows:
        logger.info("Nenhum documento foi baixado ou processado.")
        return pd.DataFrame()

    dataframe = pd.DataFrame(rows)
    final_columns = []
    remaining_columns = set(dataframe.columns)
    for column in _PREFERRED_DOCUMENT_COLUMNS:
        if column in remaining_columns:
            final_columns.append(column)
            remaining_columns.remove(column)
    final_columns.extend(sorted(remaining_columns))
    dataframe = dataframe[final_columns]

    for column in _PREFERRED_DOCUMENT_COLUMNS:
        if column not in dataframe.columns:
            dataframe[column] = None

    logger.info(
        "Download de documentos finalizado. Total de linhas de documentos: %d.",
        len(dataframe)
    )
    return dataframe


class JusbrScraper(HTTPScraper):
    """Raspador para o JusBR (consulta unificada da PDPJ-CNJ).

    Este scraper interage com a API da Plataforma Digital do Poder Judiciario (PDPJ).
    """

    BASE_API_URL_V2 = "https://portaldeservicos.pdpj.jus.br/api/v2/processos/"
    BASE_API_URL_V1_DOCS = (
        "https://api-processo.data-lake.pdpj.jus.br/processo-api/api/v1/processos/"
    )

    # Schemas pydantic da API publica (``extra="forbid"``). Expostos como
    # atributos de classe — fonte da verdade dos parametros aceitos e marcador
    # de "wired" para ``tests/schemas/test_signature_parity.py`` (mesmo padrao
    # do agregador irmao PDPJ).
    INPUT_AUTH = InputAuthJusBR
    INPUT_CPOPG = InputCPOPGJusBR
    INPUT_DOWNLOAD_DOCUMENTS = InputDownloadDocumentsJusBR

    def __init__(
        self,
        verbose: int = 0,
        download_path: str | None = None,
        sleep_time: float = 0.5,
        token: str | None = None
    ):
        super().__init__(
            "jusbr", verbose=verbose, download_path=download_path, sleep_time=sleep_time
        )
        self.token = token
        if self.token:
            self.session.headers.update({'authorization': f'Bearer {self.token}'})

    def _configure_session(self, session: requests.Session) -> None:
        # PDPJ rejeita User-Agent não-browser; sobrescreve o default do
        # HTTPScraper (``juscraper/<version>``) por uma string Chrome/Edg.
        session.headers.update({'user-agent': USER_AGENT})

    def auth(self, token: str, **kwargs: Any) -> bool:
        """
        Define o token JWT para autenticacao e o decodifica para verificacao.

        Raises:
            TypeError: Quando um kwarg desconhecido e passado (schema
                :class:`InputAuthJusBR`, ``extra="forbid"``).
            ValueError: Quando o token e invalido ou esta expirado.
        """
        try:
            inp = self.INPUT_AUTH(token=token, **kwargs)
        except ValidationError as exc:
            raise_on_extra_kwargs(exc, "JusbrScraper.auth()", schema_cls=self.INPUT_AUTH)
            raise
        token = inp.token
        try:
            # ``verify_exp: True`` e explicito porque com ``verify_signature=False``
            # o PyJWT desativa ``verify_exp`` por padrao — sem isso, o ramo
            # ``except jwt.ExpiredSignatureError`` abaixo seria dead code.
            decoded = jwt.decode(token,
                                 options={
                                     "verify_signature": False,
                                     "verify_aud": False,
                                     "verify_exp": True,
                                 },
                                 algorithms=["RS256", "HS256", "ES256", "none"])
            self.token = token
            self.session.headers.update({'authorization': f'Bearer {self.token}'})
            if self.verbose > 0:
                logger.info("Token JWT definido e decodificado com sucesso!")
                if self.verbose > 1:
                    logger.debug("  Token decodificado com %d claims.", len(decoded))
            return True
        except jwt.ExpiredSignatureError as exc:
            logger.error("Token JWT expirado.")
            raise ValueError("Token JWT expirado.") from exc
        except jwt.InvalidTokenError as exc:
            logger.error("Token JWT inválido: %s", exc)
            raise ValueError(f"Token JWT inválido: {exc}") from exc

    def auth_firefox(self):
        """
        Authentication via Firefox.
        """
        # url de autenticação
        u = (
            "https://sso.cloud.pje.jus.br/auth/realms/pje/protocol/"
            "openid-connect/auth?client_id=portalexterno-frontend"
            "&redirect_uri=https://portaldeservicos.pdpj.jus.br/home?state=meu_state"
            "&session_state=1234&state=1234&response_mode=fragment&response_type=code"
            "&scope=openid&nonce=1234&prompt=none"
        )

        # pega cookies do firefox
        cookies = browser_cookie3.firefox(domain_name="sso.cloud.pje.jus.br")
        session = requests.Session()
        session.cookies.update(cookies)

        # faz request para obter o token
        resp = session.get(u, allow_redirects=False)
        location_url = resp.headers.get("Location")
        if location_url is None:
            raise RuntimeError("JusBR: cabeçalho 'Location' ausente na resposta de auth.")
        fragment = urllib.parse.urlparse(location_url).fragment
        params = urllib.parse.parse_qs(fragment)
        codes = params.get("code", [])
        if not codes:
            raise RuntimeError("JusBR: parâmetro 'code' ausente no fragmento de auth.")
        code = codes[0]
        token_url = "https://sso.cloud.pje.jus.br/auth/realms/pje/protocol/openid-connect/token"  # nosec
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": "portalexterno-frontend",
            "redirect_uri": (
                "https://portaldeservicos.pdpj.jus.br/home?state=meu_state&session_state=1234"
            )
        }
        resp = session.post(token_url, data=data)
        token = resp.json()["access_token"]
        self.token = token
        self.session.headers.update({'authorization': f'Bearer {self.token}'})
        return True

    def cpopg(self, id_cnj: str | list[str], **kwargs: Any) -> pd.DataFrame:
        """
        Consulta processos pelo numero CNJ (ou lista de numeros CNJ) via API nacional.

        Raises:
            TypeError: Quando um kwarg desconhecido e passado (schema
                :class:`InputCPOPGJusBR`, ``extra="forbid"``).
            RuntimeError: Quando ``auth(token)`` nao foi chamado antes.
        """
        try:
            inp = self.INPUT_CPOPG(id_cnj=id_cnj, **kwargs)
        except ValidationError as exc:
            raise_on_extra_kwargs(exc, "JusbrScraper.cpopg()", schema_cls=self.INPUT_CPOPG)
            raise
        id_cnj = inp.id_cnj
        if not self.token:
            raise RuntimeError("Autenticacao necessaria. Chame o metodo auth(token) primeiro.")

        id_cnj_list = [id_cnj] if isinstance(id_cnj, str) else id_cnj
        all_process_data = []

        for cnj_input in id_cnj_list:
            cnj_cleaned = clean_cnj(cnj_input)
            if not cnj_cleaned:
                logger.warning("CNJ inválido fornecido e não pôde ser limpo: %s", cnj_input)
                all_process_data.append({
                    'processo': cnj_input,
                    'processo_pesquisado': cnj_input,
                    'status_consulta': 'CNJ Invalido'
                })
                continue

            logger.info("Consultando processo CNJ: %s", cnj_cleaned)

            raw_list_data = fetch_process_list(self._request_with_retry, cnj_cleaned, self.BASE_API_URL_V2)
            processos_content = parse_process_list_response(raw_list_data)

            if not processos_content:
                logger.warning("Nenhum processo encontrado para o CNJ: %s", cnj_cleaned)
                all_process_data.append({
                    'processo': cnj_cleaned,
                    'processo_pesquisado': cnj_cleaned,
                    'status_consulta': 'Nao encontrado na lista inicial'
                })
                time.sleep(self.sleep_time)
                continue

            for processo_item in processos_content:
                numero_processo_oficial = processo_item.get('numeroProcesso')
                if not numero_processo_oficial:
                    logger.warning(
                        "Item de processo sem 'numeroProcesso' para CNJ %s. Item: %s",
                        cnj_cleaned, processo_item
                    )
                    continue

                raw_details_data = fetch_process_details(
                    self._request_with_retry, numero_processo_oficial, self.BASE_API_URL_V2
                )
                parsed_details = parse_process_details_response(raw_details_data, cnj_cleaned)
                if parsed_details:
                    all_process_data.append(parsed_details)
                else:
                    all_process_data.append({
                        'processo': cnj_cleaned,
                        'processo_pesquisado': cnj_cleaned,
                        'numeroProcessoOficial': numero_processo_oficial,
                        'status_consulta': 'Erro ao obter ou parsear detalhes'
                    })
            time.sleep(self.sleep_time)

        if not all_process_data:
            return pd.DataFrame()
        df_resultados = pd.DataFrame(all_process_data)
        if 'processo_pesquisado' in df_resultados.columns:
            cols1 = [col for col in df_resultados.columns if col != 'processo_pesquisado']
            cols = ['processo_pesquisado', *cols1]
            df_resultados = df_resultados[cols]
        return df_resultados

    def _fetch_document_contents(
        self,
        numero_processo: str,
        text_uuid: str | None,
        binary_uuid: str | None,
        authorization: str,
    ) -> tuple[str | None, str | None, bytes | None]:
        """Baixa texto e binário de forma independente para um documento."""
        numero_processo_clean = clean_cnj(numero_processo)
        raw_text = None
        cleaned_text = None
        if text_uuid:
            logger.debug(
                "Tentando baixar texto do documento UUID %s para processo %s.",
                text_uuid, numero_processo,
            )
            raw_text = fetch_document_text(
                self._request_with_retry,
                numero_processo_clean,
                text_uuid,
                self.BASE_API_URL_V1_DOCS,
                authorization=authorization,
            )
            cleaned_text = clean_document_text(raw_text)

        raw_binary = None
        if binary_uuid:
            raw_binary = fetch_document_binary(
                self._request_with_retry,
                numero_processo_clean,
                binary_uuid,
                self.BASE_API_URL_V2,
            )
        return raw_text, cleaned_text, raw_binary

    def _process_single_document(
        self,
        document_metadata: _DocumentMetadata,
        numero_processo: str,
    ) -> _DocumentDataRow | None:
        """Processa uma metadata já validada e produz no máximo uma linha."""
        text_uuid = _extract_document_uuid(document_metadata.get('hrefTexto'))
        binary_uuid = _extract_document_uuid(document_metadata.get('hrefBinario'))
        if not text_uuid and not binary_uuid:
            logger.warning(
                "Documento sem UUID extraível em hrefTexto nem hrefBinario "
                "para o processo %s. Metadados: %s",
                numero_processo, str(document_metadata)[:200]
            )
            return None

        logger.debug(
            "[JUSBR DEBUG] doc_meta para processo %s: %r",
            numero_processo, document_metadata,
        )
        authorization = self.session.headers.get('authorization', '')
        if isinstance(authorization, bytes):
            authorization = authorization.decode('latin-1')
        raw_text, cleaned_text, raw_binary = self._fetch_document_contents(
            numero_processo, text_uuid, binary_uuid, authorization
        )
        _log_document_text_result(text_uuid, numero_processo, raw_text, cleaned_text)

        document_row = {
            'numero_processo': numero_processo,
            'texto': cleaned_text,
            '_raw_text_api': raw_text,
            '_raw_binary_api': raw_binary,
        }
        document_row.update(document_metadata)
        return document_row

    def _download_process_documents(
        self,
        index: Any,
        row: pd.Series,
        max_docs_per_process: int | None,
    ) -> list[_DocumentDataRow]:
        """Baixa as linhas válidas de um único processo do DataFrame de entrada."""
        numero_processo = row.get('numeroProcesso')
        processo_pesquisado = row.get('processo')
        if not numero_processo:
            logger.warning(
                "Linha %s (CNJ: %s) sem 'numeroProcesso' para download de documentos",
                index, processo_pesquisado,
            )
            return []

        detalhes = row.get('detalhes')
        if not isinstance(detalhes, dict):
            logger.warning(
                "Campo 'detalhes' não é um dicionário para o processo %s "
                "(linha %s). Tipo: %s. Pulando documentos.",
                numero_processo, index, type(detalhes).__name__,
            )
            return []

        metadata_list = _resolve_document_metadata_list(detalhes, numero_processo)
        logger.info(
            "Processo %s (pesquisado: %s): %d documentos encontrados na metadata.",
            numero_processo, processo_pesquisado, len(metadata_list),
        )

        document_rows: list[_DocumentDataRow] = []
        for document_metadata in metadata_list:
            if max_docs_per_process is not None and len(document_rows) >= max_docs_per_process:
                logger.info(
                    "Limite de %d documentos atingido para o processo %s.",
                    max_docs_per_process, numero_processo,
                )
                break
            document_row = self._process_single_document(document_metadata, numero_processo)
            if document_row is None:
                continue
            document_rows.append(document_row)
            time.sleep(self.sleep_time)
        return document_rows

    def download_documents(
        self,
        base_df: pd.DataFrame,
        max_docs_per_process: int | None = None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """
        Downloads document texts for processes in base_df.
        Iterates through processes in base_df, extracts document metadata from the
        'detalhes' column, fetches, and cleans document texts.
        Returns a DataFrame where each row is a document.

        Raises:
            TypeError: Quando um kwarg desconhecido e passado (schema
                :class:`InputDownloadDocumentsJusBR`, ``extra="forbid"``).
            RuntimeError: Quando ``auth(token)`` nao foi chamado antes.
        """
        try:
            inp = self.INPUT_DOWNLOAD_DOCUMENTS(
                base_df=base_df, max_docs_per_process=max_docs_per_process, **kwargs
            )
        except ValidationError as exc:
            raise_on_extra_kwargs(
                exc, "JusbrScraper.download_documents()", schema_cls=self.INPUT_DOWNLOAD_DOCUMENTS
            )
            raise
        base_df = inp.base_df
        max_docs_per_process = inp.max_docs_per_process
        if not self.token:
            raise RuntimeError("Autenticação necessária. Chame o método auth(token) primeiro.")

        all_docs_data: list[_DocumentDataRow] = []
        logger.info("Iniciando download de documentos para %d processos...", len(base_df))

        for index, row in base_df.iterrows():
            all_docs_data.extend(
                self._download_process_documents(index, row, max_docs_per_process)
            )
        return _build_documents_dataframe(all_docs_data)
