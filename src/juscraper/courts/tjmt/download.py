"""
Baixa resultados brutos da pesquisa de jurisprudência do TJMT.
"""
import math
import re
import time
import unicodedata
from collections import deque
from collections.abc import Iterator
from datetime import date, timedelta
from urllib.parse import urljoin, urlparse

import requests
from tqdm import tqdm

from juscraper.core.http import RequestFn
from juscraper.utils.params import coerce_brazilian_date

PORTAL_URL = "https://jurisprudencia.tjmt.jus.br/"
PORTAL_HOST = "jurisprudencia.tjmt.jus.br"
PRODUCTION_API_URL = "https://hellsgate.tjmt.jus.br/jurisprudencia"
MAX_CONFIG_RESOURCES = 32
DEFAULT_PAGE_SIZE = 10


class TJMTConfigError(ValueError):
    """Indica que a configuração pública do TJMT está ausente ou inválida."""


class TJMTResponseError(ValueError):
    """Indica que a API de jurisprudência retornou uma resposta inválida."""


_SCRIPT_SRC_RE = re.compile(r"<script[^>]+src=[\"']([^\"']+)", re.IGNORECASE)
_MODULE_PRELOAD_RE = re.compile(
    r"<link(?=[^>]+\brel=[\"']modulepreload[\"'])(?=[^>]+\bhref=[\"']([^\"']+)[\"'])[^>]*>",
    re.IGNORECASE,
)
_IMPORT_RE = re.compile(
    r"(?:from\s*|import\s*(?:\(\s*)?)[\"']([^\"']+\.js(?:\?[^\"']*)?)[\"']"
)
_CONFIG_PROPERTY_RE = re.compile(
    r"(?<![\w$])(?:\"(?P<double>api_url|api_hellsgate_token)\"|"
    r"'(?P<single>api_url|api_hellsgate_token)'|"
    r"(?P<bare>api_url|api_hellsgate_token))\s*:\s*"
    r"(?P<quote>[\"'])(?P<value>.*?)(?P=quote)"
)


def _skip_js_string(script: str, start: int) -> int:
    """Retorna o índice após uma string JavaScript entre aspas."""
    quote = script[start]
    escaped = False
    index = start + 1
    while index < len(script):
        char = script[index]
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == quote:
            return index + 1
        index += 1
    return len(script)


def _skip_js_comment(script: str, start: int) -> int:
    """Retorna o índice após um comentário JavaScript."""
    if script.startswith("//", start):
        newline = script.find("\n", start + 2)
        return len(script) if newline == -1 else newline
    end = script.find("*/", start + 2)
    return len(script) if end == -1 else end + 2


def _iter_js_object_bodies(script: str) -> Iterator[str]:
    """Produz corpos de objetos JavaScript ignorando chaves em strings e comentários."""
    stack: list[int] = []
    index = 0
    while index < len(script):
        char = script[index]
        if char in "\"'`":
            index = _skip_js_string(script, index)
            continue
        if script.startswith("//", index) or script.startswith("/*", index):
            index = _skip_js_comment(script, index)
            continue
        if char == "{":
            stack.append(index)
        elif char == "}" and stack:
            start = stack.pop()
            yield script[start + 1:index]
        index += 1


def _extract_top_level_config(body: str) -> dict[str, str]:
    """Extrai propriedades de configuração pertencentes diretamente a um objeto."""
    values: dict[str, str] = {}
    depth = 0
    index = 0
    while index < len(body):
        if body.startswith("//", index) or body.startswith("/*", index):
            index = _skip_js_comment(body, index)
            continue
        if depth == 0:
            property_value = _config_property_at(body, index)
            if property_value is not None:
                name, value, end = property_value
                values[name] = value
                index = end
                continue
        char = body[index]
        if char in "\"'`":
            index = _skip_js_string(body, index)
            continue
        if char == "{":
            depth += 1
            index += 1
            continue
        if char == "}":
            depth -= 1
            index += 1
            continue
        index += 1
    return values


def _config_property_at(body: str, index: int) -> tuple[str, str, int] | None:
    """Retorna a propriedade de configuração iniciada no índice informado."""
    match = _CONFIG_PROPERTY_RE.match(body, index)
    if match is None:
        return None
    for group in ("double", "single", "bare"):
        name = match.group(group)
        if name is not None:
            return name, match.group("value"), match.end()
    return None


def _extract_api_config(script: str) -> dict[str, str] | None:
    """Extrai as duas configurações da API do mesmo objeto JavaScript."""
    for body in _iter_js_object_bodies(script):
        config = _extract_top_level_config(body)
        if "api_url" in config and "api_hellsgate_token" in config:
            return {
                "api_url": config["api_url"],
                "api_hellsgate_token": config["api_hellsgate_token"],
            }
    return None


def _validate_api_config(config: dict[str, str]) -> dict[str, str]:
    """Valida a URL descoberta sem expor o token."""
    api_url = config.get("api_url", "").strip()
    token = config.get("api_hellsgate_token", "").strip()
    if api_url != PRODUCTION_API_URL:
        raise TJMTConfigError("URL da API do TJMT ausente ou fora do endpoint de produção esperado.")
    if not token:
        raise TJMTConfigError("Token da API do TJMT ausente na configuração pública.")
    return {"api_url": api_url, "token": token}


def _get_api_config(request_fn: RequestFn) -> dict:
    """Descobre e valida a configuração pública atual da API."""
    home = request_fn("GET", PORTAL_URL, timeout=30).text
    initial_resources = _SCRIPT_SRC_RE.findall(home) + _MODULE_PRELOAD_RE.findall(home)
    resources = deque(urljoin(PORTAL_URL, src) for src in initial_resources)
    visited: set[str] = set()

    while resources and len(visited) < MAX_CONFIG_RESOURCES:
        resource = resources.popleft()
        parsed = urlparse(resource)
        if parsed.scheme != "https" or parsed.hostname != PORTAL_HOST or resource in visited:
            continue
        visited.add(resource)
        script = request_fn("GET", resource, timeout=30).text
        config = _extract_api_config(script)
        if config is not None:
            return _validate_api_config(config)
        for imported in _IMPORT_RE.findall(script):
            imported_url = urljoin(resource, imported)
            if imported_url not in visited:
                resources.append(imported_url)

    if len(visited) >= MAX_CONFIG_RESOURCES:
        raise TJMTConfigError("Limite de recursos excedido ao descobrir a configuração do TJMT.")
    raise TJMTConfigError("Configuração da API do TJMT não encontrada nos scripts públicos.")


def _build_params(
    pesquisa: str,
    pagina: int,
    quantidade: int,
    tipo_consulta: str,
    thesaurus: bool,
    data_publicacao_inicio: str | None,
    data_publicacao_fim: str | None,
    relator: str | None,
    orgao_julgador: str | None,
    tipo_processo: str | None,
) -> dict:
    """Monta os parâmetros da query para o endpoint de consulta."""
    tipo_param = {"Acordao": "1", "DecisaoMonocratica": "2"}.get(tipo_consulta)
    if tipo_param is None:
        raise ValueError(f"Tipo de consulta não suportado pelo TJMT: {tipo_consulta}.")
    params = {
        "indicePagina": pagina,
        "quantidadePagina": quantidade,
        "tipoConsulta": tipo_param,
        "termoDeBusca": pesquisa,
        "tipoBusca": "1",
        "OrdenarPor": "Relevancia",
        "Decrescente": "true",
        "thesaurus": str(thesaurus).lower(),
        "exibirArquivados": "true",
    }
    if data_publicacao_inicio is not None:
        params["periodoDataDe"] = data_publicacao_inicio
    if data_publicacao_fim is not None:
        params["periodoDataAte"] = data_publicacao_fim
    if relator is not None:
        params["fqRelator"] = relator
    if orgao_julgador is not None:
        params["fqOrgaoJulgador"] = orgao_julgador
    if tipo_processo is not None:
        params["tipoProcesso"] = tipo_processo
    return params


def _validate_response(data: object, tipo_consulta: str) -> tuple[dict, int]:
    """Valida o envelope da API e retorna a página e sua contagem específica."""
    if not isinstance(data, dict):
        raise TJMTResponseError("Resposta da API do TJMT não é um objeto JSON.")
    if data.get("success") is not True:
        raise TJMTResponseError("API de jurisprudência do TJMT retornou erro.")
    if data.get("errorMessage") is not None:
        raise TJMTResponseError("API de jurisprudência do TJMT retornou uma mensagem de erro.")
    value = data.get("value")
    if not isinstance(value, dict) or not isinstance(value.get("resultados"), list):
        raise TJMTResponseError("Resposta da API do TJMT não contém value.resultados válido.")
    count_key = "countAcordaoDocumento" if tipo_consulta == "Acordao" else "countDecisaoMonocratica"
    count = value.get(count_key)
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise TJMTResponseError(f"Resposta da API do TJMT não contém {count_key} válido.")
    return data, count


def _reject_unsupported_filters(
    data_julgamento_inicio: str | None,
    data_julgamento_fim: str | None,
    classe: str | None,
) -> None:
    """Rejeita filtros ainda não implementados pela API nova."""
    filters = {
        "data_julgamento_inicio": data_julgamento_inicio,
        "data_julgamento_fim": data_julgamento_fim,
        "classe": classe,
    }
    provided = [name for name, value in filters.items() if value not in (None, "")]
    if provided:
        raise NotImplementedError(
            "Filtros do TJMT ainda não implementados nesta etapa: "
            + ", ".join(provided)
            + "."
        )


def _normalize_text_filter(value: str | int | None, name: str) -> str | None:
    """Normaliza nome textual de relator ou órgão julgador."""
    if value is None or value == "":
        return None
    if isinstance(value, int):
        raise TypeError(f"{name} deve ser um nome textual, não um identificador numérico.")
    if not isinstance(value, str):
        raise TypeError(f"{name} deve ser informado como texto.")
    normalized = " ".join(value.strip().split())
    normalized = "".join(
        char for char in unicodedata.normalize("NFKD", normalized)
        if not unicodedata.combining(char)
    ).upper()
    if normalized.isdigit():
        raise ValueError(f"{name} não aceita identificadores numéricos.")
    return normalized or None


def _normalize_tipo_processo(value: str | None) -> str | None:
    """Converte o tipo público de processo para o código da API."""
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise TypeError("tipo_processo deve ser informado como texto.")
    try:
        return {"Criminal": "1", "Civel": "2", "Cível": "2"}[value]
    except KeyError as exc:
        raise ValueError(f"tipo_processo desconhecido: {value}.") from exc


def _to_tjmt_date(value) -> str | None:
    """Converte uma data aceita pelo projeto para ISO e valida seu valor."""
    normalized = coerce_brazilian_date(value, "%Y-%m-%d")
    if normalized is None:
        return None
    if normalized == "":
        return ""
    if not isinstance(normalized, str):
        raise TypeError(f"Data deve ser texto ou data, recebido: {value!r}.")
    try:
        return date.fromisoformat(normalized).isoformat()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Data inválida para o TJMT: {value!r}.") from exc


def _to_exclusive_end_date(value) -> str | None:
    """Converte a data final inclusiva para o limite exclusivo da API."""
    normalized = _to_tjmt_date(value)
    if not normalized:
        return normalized
    return (date.fromisoformat(normalized) + timedelta(days=1)).isoformat()


def _validate_download_inputs(quantidade: int, paginas, tipo_consulta: str) -> list[int] | None:
    """Valida paginação e tipo antes de iniciar requisições HTTP."""
    if isinstance(quantidade, bool) or not isinstance(quantidade, int):
        raise TypeError("quantidade_por_pagina deve ser um inteiro positivo.")
    if quantidade < 1:
        raise ValueError("quantidade_por_pagina deve ser maior que zero.")
    if tipo_consulta not in {"Acordao", "DecisaoMonocratica"}:
        raise ValueError(f"Tipo de consulta não suportado pelo TJMT: {tipo_consulta}.")
    if paginas is None:
        return None
    if isinstance(paginas, bool):
        raise TypeError("paginas deve conter inteiros positivos.")
    if isinstance(paginas, int):
        if paginas < 1:
            raise ValueError("paginas deve conter apenas valores maiores que zero.")
        paginas = range(1, paginas + 1)
    try:
        paginas_list = list(paginas)
    except TypeError as exc:
        raise TypeError("paginas deve conter inteiros positivos.") from exc
    if any(isinstance(pagina, bool) or not isinstance(pagina, int) for pagina in paginas_list):
        raise TypeError("paginas deve conter inteiros positivos.")
    if any(pagina < 1 for pagina in paginas_list):
        raise ValueError("paginas deve conter apenas valores maiores que zero.")
    return paginas_list


def cjsg_download(
    pesquisa: str,
    paginas=None,
    tipo_consulta: str = "Acordao",
    data_julgamento_inicio: str | None = None,
    data_julgamento_fim: str | None = None,
    data_publicacao_inicio: str | None = None,
    data_publicacao_fim: str | None = None,
    relator: str | None = None,
    orgao_julgador: str | None = None,
    classe: str | None = None,
    tipo_processo: str | None = None,
    thesaurus: bool = False,
    quantidade_por_pagina: int = DEFAULT_PAGE_SIZE,
    *,
    request_fn: RequestFn,
    session: requests.Session,
) -> list:
    """Baixa resultados JSON brutos da API de jurisprudência do TJMT.

    Argumentos:
    pesquisa: Termo de pesquisa.
    paginas: Páginas a baixar, baseadas em 1. ``None`` baixa todas.
    tipo_consulta: ``"Acordao"`` ou ``"DecisaoMonocratica"``.
    data_julgamento_inicio: Data inicial (``yyyy-mm-dd`` ou ``dd/mm/yyyy``).
    data_julgamento_fim: Data final (``yyyy-mm-dd`` ou ``dd/mm/yyyy``).
    data_publicacao_inicio: Data inicial de publicação.
    data_publicacao_fim: Data final inclusiva de publicação.
    relator: Filtro pelo nome do relator.
    orgao_julgador: Filtro pela câmara julgadora.
    classe: Filtro pela classe processual.
    tipo_processo: ``"Cível"`` ou ``"Criminal"``.
    thesaurus: Define se a pesquisa deve usar sinônimos.
    quantidade_por_pagina: Itens por página (padrão 10).
    request_fn: Callable HTTP que trata retries e ``raise_for_status`` —
        normalmente ``TJMTScraper._request_with_retry`` (via
        ``core.http.HTTPScraper``), centralizando o backoff exponencial
        para 429/5xx.
    session: ``requests.Session`` compartilhada por ``HTTPScraper``;
        recebida explicitamente para manter os headers ``Token``,
        ``Accept`` e ``Referer`` obtidos por ``_get_api_config``. As
        requisições subsequentes via ``request_fn`` usam essa mesma sessão.

    Retorno:
    Lista de dicionários JSON brutos, um por página.
    """
    paginas_list = _validate_download_inputs(quantidade_por_pagina, paginas, tipo_consulta)
    _reject_unsupported_filters(
        data_julgamento_inicio,
        data_julgamento_fim,
        classe,
    )
    data_publicacao_inicio = _to_tjmt_date(data_publicacao_inicio)
    data_publicacao_fim = _to_exclusive_end_date(data_publicacao_fim)
    relator = _normalize_text_filter(relator, "relator")
    orgao_julgador = _normalize_text_filter(orgao_julgador, "orgao_julgador")
    tipo_processo = _normalize_tipo_processo(tipo_processo)
    cfg = _get_api_config(request_fn)
    api_url = cfg["api_url"]
    token = cfg["token"]

    session.headers.update({
        "token": token,
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://jurisprudencia.tjmt.jus.br/",
    })

    def _fetch_page(pagina: int) -> tuple[dict, int]:
        params = _build_params(
            pesquisa=pesquisa,
            pagina=pagina,
            quantidade=quantidade_por_pagina,
            tipo_consulta=tipo_consulta,
            thesaurus=thesaurus,
            data_publicacao_inicio=data_publicacao_inicio,
            data_publicacao_fim=data_publicacao_fim,
            relator=relator,
            orgao_julgador=orgao_julgador,
            tipo_processo=tipo_processo,
        )
        resp = request_fn(
            "GET",
            f"{api_url}/consulta",
            params=params,
            timeout=60,
            expect_json=True,
        )
        try:
            data = resp.json()
        except ValueError as exc:
            raise TJMTResponseError("Resposta da API do TJMT não contém JSON válido.") from exc
        return _validate_response(data, tipo_consulta)

    if paginas_list is None:
        first, total = _fetch_page(0)
        resultados = [first]
        n_pags = math.ceil(total / quantidade_por_pagina) if total else 1
        if n_pags > 1:
            for pagina in tqdm(range(1, n_pags), desc="Baixando páginas TJMT"):
                page, _ = _fetch_page(pagina)
                resultados.append(page)
                time.sleep(1)
        return resultados

    resultados = []
    for pagina in tqdm(paginas_list, desc="Baixando páginas TJMT"):
        page, _ = _fetch_page(pagina - 1)
        resultados.append(page)
        if len(paginas_list) > 1:
            time.sleep(1)
    return resultados
