"""Scraper for the Brazilian Supreme Court (STF) jurisprudence search."""
from __future__ import annotations

import math
import time
import warnings

import pandas as pd
import requests

from juscraper.core.http import HTTPScraper
from juscraper.core.parse_utils import coerce_date_columns
from juscraper.utils.params import apply_input_pipeline_search

from ._tls import _STFTLSAdapter
from ._waf import PAGINA_BUSCA, USER_AGENT, WAF_COOKIE, obter_waf_token
from .download import BASE_URL, MAX_REGISTROS, build_payload
from .parse import parse_contagem, parse_decisoes
from .schemas import InputContarDecisoesSTF, InputListarDecisoesSTF

_FILTROS = {
    "base",
    "classe",
    "inteiro_teor",
    "data_julgamento_inicio",
    "data_julgamento_fim",
    "data_publicacao_inicio",
    "data_publicacao_fim",
}


def _pesquisa_ou_tudo(pesquisa: str | None, kwargs: dict) -> str | None:
    """Sem termo, a busca vai com ``"*"``, salvo quando o termo chega por ``query``/``termo``."""
    if pesquisa is None and not {"query", "termo"} & kwargs.keys():
        return "*"
    return pesquisa


def _eh_desafio(resp: requests.Response) -> bool:
    return resp.headers.get("x-amzn-waf-action") == "challenge"


def _levantar_limite_da_api(resp: requests.Response) -> None:
    """Converte o 403 de limite da API em ``ValueError``, sem retry.

    ``HTTPScraper`` repete todo 403 porque, em outros tribunais, ele e bloqueio
    transitorio de WAF. Aqui o 403 com ``detail`` e regra fixa da API (250 por
    pagina, 10.000 por busca), e repetir nao muda a resposta.
    """
    if resp.status_code != 403:
        return
    try:
        detalhe = resp.json().get("detail")
    except (ValueError, AttributeError):
        return
    if detalhe:
        raise ValueError(f"A API do STF recusou a busca: {detalhe}")


class STFScraper(HTTPScraper):
    """Scraper for the STF jurisprudence search (acordaos e decisoes monocraticas)."""

    BASE_URL = BASE_URL

    def __init__(
        self,
        waf_token: str | None = None,
        *,
        verbose: int = 0,
        sleep_time: float = 1.0,
        **kwargs,
    ):
        """Cria o scraper.

        Args:
            waf_token (str | None): Cookie ``aws-waf-token`` ja obtido. Sem ele, o
                scraper obtem um com o Playwright (extra ``juscraper[stf]``) na
                primeira busca, e renova sempre que o WAF voltar a desafiar.
            verbose (int): Nivel de log.
            sleep_time (float): Pausa em segundos entre paginas. Default ``1.0``.
        """
        self._waf_token = waf_token
        super().__init__("STF", verbose=verbose, sleep_time=sleep_time, **kwargs)

    def _configure_session(self, session: requests.Session) -> None:
        session.mount("https://jurisprudencia.stf.jus.br", _STFTLSAdapter())
        session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://jurisprudencia.stf.jus.br",
            "Referer": PAGINA_BUSCA,
        })
        if self._waf_token:
            session.cookies.set(WAF_COOKIE, self._waf_token)

    def _renovar_token(self) -> None:
        self.session.cookies.set(WAF_COOKIE, obter_waf_token())

    def _post(self, payload: dict) -> requests.Response:
        return self._request_with_retry(
            "POST", BASE_URL, json=payload, timeout=60, on_response=_levantar_limite_da_api
        )

    def _buscar(self, payload: dict) -> dict:
        if WAF_COOKIE not in self.session.cookies:
            self._renovar_token()
        resp = self._post(payload)
        if _eh_desafio(resp):
            self._renovar_token()
            resp = self._post(payload)
            if _eh_desafio(resp):
                raise RuntimeError(
                    "O WAF do STF desafiou de novo logo apos a renovacao do cookie aws-waf-token. "
                    "Aguarde alguns minutos antes de tentar outra vez."
                )
        dados: dict = resp.json()
        return dados

    def listar_decisoes(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        **kwargs,
    ) -> pd.DataFrame:
        """Lista acordaos ou decisoes monocraticas da busca de jurisprudencia do STF.

        Faz um POST por pagina na API do portal ``jurisprudencia.stf.jus.br``, com o
        mesmo corpo que o site envia. A API so entrega os 10.000 primeiros registros
        de uma busca; com ``paginas=None`` e mais resultados que isso, emite
        ``UserWarning`` e devolve os 10.000.

        Args:
            pesquisa (str | None): Termos na sintaxe do portal: ``$`` como curinga
                (``terceiriz$``), ``ou`` como disjuncao, ``AND``/``NOT`` e aspas do
                Elasticsearch. ``None`` busca tudo o que os filtros selecionam.
            paginas (int | list | range | None): Paginas 1-based; ``None`` baixa
                todas. Default ``None``.
            **kwargs: Filtros aceitos pelo schema :class:`InputListarDecisoesSTF`.
                Listados abaixo (todos opcionais; ``None`` = sem filtro):

                * ``base`` (str): ``"decisoes"`` (monocraticas, default) ou
                  ``"acordaos"``. Backend: ``post_filter`` em ``base``.
                * ``classe`` (str | list[str]): Sigla da classe processual (ex.:
                  ``"Rcl"``). Backend:
                  ``processo_classe_processual_unificada_classe_sigla.keyword``.
                * ``inteiro_teor`` (bool): Pesquisa tambem no inteiro teor, como a
                  opcao do portal. Default ``False``.
                * ``data_julgamento_inicio`` / ``data_julgamento_fim`` (str):
                  ``DD/MM/AAAA``.
                * ``data_publicacao_inicio`` / ``data_publicacao_fim`` (str):
                  ``DD/MM/AAAA``.
                * ``tamanho_pagina`` (int): Documentos por pagina, de 1 a 250.
                  Default ``250``.

        Aliases deprecados (popados com ``DeprecationWarning`` antes do pydantic):
            * ``query`` / ``termo`` -> ``pesquisa``
            * ``data_inicio`` / ``data_fim`` -> ``data_julgamento_inicio`` / ``_fim``
            * ``data_julgamento_de`` / ``_ate`` -> ``data_julgamento_inicio`` / ``_fim``
            * ``data_publicacao_de`` / ``_ate`` -> ``data_publicacao_inicio`` / ``_fim``

        Raises:
            TypeError: Quando um kwarg desconhecido e passado.
            ValidationError: Quando um filtro tem formato invalido.
            ValueError: Quando a pagina pedida passa do registro 10.000.
            ImportError: Quando nao ha ``waf_token`` e o Playwright nao esta instalado.

        Returns:
            pd.DataFrame: Uma linha por documento, com ``processo``, ``classe``,
            ``relator``, ``data_julgamento``, ``data_publicacao``, ``ementa``
            (acordaos), ``decisao_texto`` (monocraticas), ``inteiro_teor_url`` e o
            restante do ``_source`` da API.

        Exemplo:
            >>> import juscraper as jus
            >>> stf = jus.scraper("stf")
            >>> df = stf.listar_decisoes("pejotização", classe="Rcl", paginas=1,
            ...                          data_publicacao_fim="20/08/2023")

        See also:
            :class:`InputListarDecisoesSTF` — schema pydantic e a fonte da verdade
            dos filtros aceitos.
        """
        inp = apply_input_pipeline_search(
            InputListarDecisoesSTF,
            "STFScraper.listar_decisoes()",
            pesquisa=_pesquisa_ou_tudo(pesquisa, kwargs),
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
        )
        filtros = inp.model_dump(include=_FILTROS)
        tamanho = inp.tamanho_pagina

        respostas: list[dict] = []
        if inp.paginas is None:
            respostas.append(self._buscar(build_payload(inp.pesquisa, pagina=1, tamanho_pagina=tamanho, **filtros)))
            total = respostas[0]["result"]["hits"]["total"]["value"]
            if total > MAX_REGISTROS:
                warnings.warn(
                    f"A busca tem {total} resultados, mas a API do STF so entrega os {MAX_REGISTROS} "
                    "primeiros. Divida a busca por intervalo de datas para obter o restante.",
                    UserWarning,
                    stacklevel=2,
                )
            paginas_alvo: list[int] | range = range(2, math.ceil(min(total, MAX_REGISTROS) / tamanho) + 1)
        else:
            paginas_alvo = inp.paginas

        # Montar tudo antes da primeira requisicao faz uma pagina alem do teto falhar
        # sem gastar nenhuma chamada.
        payloads = [build_payload(inp.pesquisa, pagina=p, tamanho_pagina=tamanho, **filtros) for p in paginas_alvo]
        for payload in payloads:
            if respostas:
                time.sleep(self.sleep_time)
            respostas.append(self._buscar(payload))

        df = pd.DataFrame(parse_decisoes(respostas))
        coerce_date_columns(df, ["data_julgamento", "data_publicacao"])
        return df

    def contar_decisoes(self, pesquisa: str | None = None, **kwargs) -> pd.DataFrame:
        """Conta os resultados de uma busca e devolve as facetas do portal, sem baixar documentos.

        Uma requisicao com ``size=0``. Aceita os mesmos filtros de
        :meth:`listar_decisoes`, exceto ``tamanho_pagina``.

        Args:
            pesquisa (str | None): Termos na sintaxe do portal. ``None`` conta tudo o
                que os filtros selecionam.
            **kwargs: Filtros aceitos pelo schema :class:`InputContarDecisoesSTF`.

        Raises:
            TypeError: Quando um kwarg desconhecido e passado.
            ValidationError: Quando um filtro tem formato invalido.

        Returns:
            pd.DataFrame: Colunas ``faceta``, ``valor`` e ``n``. A primeira linha e
            ``faceta="total"``; as demais vem das agregacoes do portal (``base``,
            ``ministro_facet``, ``processo_classe_processual_unificada_classe_sigla``,
            ``procedencia_geografica_uf_sigla``, ``orgao_julgador`` e indicadores).
            Com ``classe``, a faceta de classe ignora o proprio filtro e as outras
            facetas o respeitam, como no portal. Uma decisao pode ter mais de um
            ministro, entao a soma de ``ministro_facet`` pode passar do total.
        """
        inp = apply_input_pipeline_search(
            InputContarDecisoesSTF,
            "STFScraper.contar_decisoes()",
            pesquisa=_pesquisa_ou_tudo(pesquisa, kwargs),
            paginas=None,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
        )
        filtros = inp.model_dump(include=_FILTROS)
        resposta = self._buscar(build_payload(inp.pesquisa, tamanho_pagina=0, **filtros))
        return pd.DataFrame(parse_contagem(resposta), columns=["faceta", "valor", "n"])
