"""Downloads raw results from the TJAP jurisprudence search (Tucujuris)."""
import logging
import time
from types import MappingProxyType

from tqdm import tqdm

from juscraper.core.http import RequestFn

from .exceptions import TJAPApiError, TJAPSecurityCheckError

logger = logging.getLogger(__name__)

BASE_URL = "https://tucujuris.tjap.jus.br/api/publico/consultar-jurisprudencia"
SITE_URL = "https://tucujuris.tjap.jus.br"
FRONT_URL = SITE_URL + "/pages/consultar-jurisprudencia/consultar-jurisprudencia.html"
RESULTS_PER_PAGE = 20

# Mensagem do envelope quando a busca não retorna nada — é um resultado legítimo
# (zero hits), não um erro: deve virar DataFrame vazio, não exceção.
NO_RESULTS_MESSAGE = "Nenhum resultado encontrado."


def _raise_for_error_envelope(data: dict) -> None:
    """Levanta exceção se a resposta do Tucujuris for um envelope de erro.

    O backend devolve HTTP-200 mesmo em falha, com
    ``{"status": "ERRO", "mensagem": ..., "detalhe": ...}`` e sem a chave
    ``dados``. Sem isso, ``cjsg_download_manager`` interpretaria o erro como "0
    resultados" (ver issue #279). ``"Nenhum resultado encontrado."`` é a única
    mensagem ``ERRO`` que representa sucesso (zero hits) e passa batido.
    """
    if data.get("status") != "ERRO":
        return
    mensagem = (data.get("mensagem") or "").strip()
    if mensagem == NO_RESULTS_MESSAGE:
        return
    detalhe = data.get("detalhe")
    if "verificação de segurança" in mensagem.lower():
        raise TJAPSecurityCheckError(mensagem, detalhe)
    raise TJAPApiError(mensagem, detalhe)


def _build_payload(
    pesquisa: str,
    offset: int = 0,
    orgao: str = "0",
    numero_cnj: str | None = None,
    numero_acordao: str | None = None,
    numero_ano: str | None = None,
    palavras_exatas: bool = False,
    relator: str | None = None,
    secretaria: str | None = None,
    classe: str | None = None,
    votacao: str = "0",
    origem: str | None = None,
    tipo_jurisprudencia: str | None = None,
) -> dict:
    """Build the JSON payload for the TJAP search API."""
    payload: dict = {
        "orgao": orgao,
        "ementa": pesquisa,
        "votacao": votacao,
        "tipo_jurisprudencia": tipo_jurisprudencia,
    }

    if offset > 0:
        payload["offset"] = offset
    if numero_cnj:
        payload["numeroCNJ"] = numero_cnj
    if numero_acordao:
        payload["numeroAcordao"] = numero_acordao
    if numero_ano:
        payload["numeroAno"] = numero_ano
    if palavras_exatas:
        payload["palavrasExatas"] = True
    if relator:
        payload["relator"] = relator
    if secretaria:
        payload["secretaria"] = secretaria
    if classe:
        payload["classe"] = classe
    if origem:
        payload["origem"] = origem

    return payload


_HEADERS = MappingProxyType({
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Referer": FRONT_URL,
    "tucujuris-front-url": FRONT_URL,
})


def cjsg_download_manager(
    pesquisa: str,
    paginas=None,
    *,
    request_fn: RequestFn,
    **kwargs,
) -> list:
    """Download raw results from the TJAP jurisprudence search (multiple pages).

    Returns a list of raw JSON responses (one per page).

    Args:
        pesquisa: Search term.
        paginas (list, range, or None): Pages to download (1-based).
            None: downloads all available pages.
        request_fn: HTTP callable that handles retry + raise_for_status — em
            uso normal e ``TJAPScraper._request_with_retry`` (via
            ``core.http.HTTPScraper``), centralizando backoff exponencial
            para 429/5xx.
        **kwargs: Additional parameters forwarded to ``_build_payload``.
    """
    def _get_page(pagina_1based):
        offset = (pagina_1based - 1) * RESULTS_PER_PAGE
        payload = _build_payload(pesquisa, offset=offset, **kwargs)
        resp = request_fn("POST", BASE_URL, json=payload, headers=_HEADERS, timeout=30)
        resp.encoding = "utf-8"
        data: dict = resp.json()
        _raise_for_error_envelope(data)
        time.sleep(1)
        return data

    if paginas is None:
        first = _get_page(1)
        resultados = [first]
        items = first.get("dados", [])
        if len(items) < RESULTS_PER_PAGE:
            return resultados

        page = 2
        while True:
            logger.info("TJAP: downloading page %d...", page)
            data = _get_page(page)
            resultados.append(data)
            items = data.get("dados", [])
            if len(items) < RESULTS_PER_PAGE:
                break
            page += 1
        return resultados

    paginas_iter = list(paginas)
    resultados = []
    for pagina_1based in tqdm(paginas_iter, desc="Baixando CJSG TJAP"):
        resultados.append(_get_page(pagina_1based))
    return resultados
