"""Scraper for the Tribunal de Justica do Amapa (TJAP)."""

from collections.abc import Mapping
from typing import Any, ClassVar, Literal

import pandas as pd

from juscraper.core.http import HTTPScraper, RequestPolicy
from juscraper.utils.deprecacao import resolve_deprecated_value
from juscraper.utils.params import apply_input_pipeline_search, resolve_deprecated_alias

from .download import cjsg_download_manager
from .parse import cjsg_parse_manager
from .schemas import InputCJSGTJAP, Orgao, Votacao

# Mais ``"Unanime"``, valor deprecado que ``cjsg_download`` troca por ``"Unânime"``.
VotacaoAceita = Votacao | Literal["Unanime"]


class TJAPScraper(HTTPScraper):
    """Scraper for the Tribunal de Justica do Amapa (TJAP).

    The TJAP uses the Tucujuris platform with a JSON REST API.
    Currently supports jurisprudence search (CJSG).
    """

    BASE_URL = "https://tucujuris.tjap.jus.br"

    perfis_http: ClassVar[Mapping[str, RequestPolicy]] = {
        "cjsg": RequestPolicy(timeout=30),
    }

    def __init__(self, *, sleep_time: float = 1.0, politica: Mapping[str, Mapping[str, Any]] | None = None):
        super().__init__("TJAP", sleep_time=sleep_time, politica=politica)

    def cpopg(self, id_cnj: str | list[str]):
        """Stub: first instance case consultation not implemented for TJAP."""
        raise NotImplementedError("Consulta de processos de 1o grau nao implementada para TJAP.")

    def cposg(self, id_cnj: str | list[str]):
        """Stub: second instance case consultation not implemented for TJAP."""
        raise NotImplementedError("Consulta de processos de 2o grau nao implementada para TJAP.")

    def cjsg(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        orgao: Orgao = "0",
        numero_processo: str | None = None,
        numero_acordao: str | None = None,
        numero_ano: str | None = None,
        palavras_exatas: bool = False,
        relator: str | None = None,
        secretaria: str | None = None,
        classe: str | None = None,
        votacao: VotacaoAceita = "0",
        origem: str | None = None,
        **kwargs,
    ) -> pd.DataFrame:
        """Pesquisa jurisprudência do TJAP.

        Args:
            pesquisa: Termo de busca livre.
            paginas: Páginas a baixar (1-based); ``None`` baixa todas.
            orgao: ``"0"`` para todos (default), ``"tj"`` para o Tribunal e
                ``"recursal"`` para a Turma Recursal.
            numero_processo: Número único CNJ do processo. Aceita o alias
                deprecado ``numero_cnj``.
            numero_acordao: Número do acórdão.
            numero_ano: Número/ano (por exemplo, ``"001858/1999"``).
            palavras_exatas: Se ``True``, busca as palavras exatas.
            relator: Nome do relator.
            secretaria: Secretaria do órgão julgador.
            classe: Classe processual.
            votacao: ``"0"`` para todas (default), ``"Unânime"`` ou ``"Maioria"``.
                ``"Unanime"`` (sem acento) é alias deprecado de ``"Unânime"``.
            origem: Origem (comarca).
            **kwargs: Aliases deprecados (ver abaixo).

        Aliases deprecados:
            * ``query`` / ``termo`` -> ``pesquisa``
            * ``numero_cnj`` -> ``numero_processo``

        Returns:
            Uma linha por decisão.

        Raises:
            TJAPSecurityCheckError: Quando o TJAP devolve "A verificação de segurança
                falhou" — desde ~2026 a busca exige um CAPTCHA Cloudflare Turnstile,
                validado server-side, que o raspador HTTP não consegue produzir
                (issue #279).
            TJAPApiError: Para qualquer outro envelope de erro (``status == "ERRO"``)
                do Tucujuris. Busca com zero resultados devolve DataFrame vazio.
        """
        brutos = self.cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            orgao=orgao,
            numero_processo=numero_processo,
            numero_acordao=numero_acordao,
            numero_ano=numero_ano,
            palavras_exatas=palavras_exatas,
            relator=relator,
            secretaria=secretaria,
            classe=classe,
            votacao=votacao,
            origem=origem,
            **kwargs,
        )
        return self.cjsg_parse(brutos)

    def cjsg_download(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        orgao: Orgao = "0",
        numero_processo: str | None = None,
        numero_acordao: str | None = None,
        numero_ano: str | None = None,
        palavras_exatas: bool = False,
        relator: str | None = None,
        secretaria: str | None = None,
        classe: str | None = None,
        votacao: VotacaoAceita = "0",
        origem: str | None = None,
        **kwargs,
    ) -> list:
        """Baixa as respostas JSON brutas da CJSG do TJAP.

        Aceita os mesmos parâmetros de :meth:`cjsg`. ``numero_cnj`` é aceito
        como alias deprecado de ``numero_processo``, e ``votacao="Unanime"``,
        como alias deprecado de ``votacao="Unânime"``.

        Returns:
            Lista das respostas JSON brutas, uma por página.

        Raises:
            TJAPSecurityCheckError: Quando o TJAP devolve "A verificação de segurança
                falhou" (CAPTCHA Cloudflare Turnstile exigido desde ~2026; issue #279).
            TJAPApiError: Para qualquer outro envelope de erro (``status == "ERRO"``)
                do Tucujuris. Busca com zero resultados devolve lista sem registros.
        """
        numero_processo = resolve_deprecated_alias(
            kwargs, "numero_cnj", "numero_processo", numero_processo
        )
        # Sem acento, o portal devolve os acordaos por maioria (15/11/2026).
        votacao = resolve_deprecated_value(
            votacao,
            {"Unanime": "Unânime"},
            'votacao="{antigo}" esta deprecado: o portal trata esse valor como '
            '"Maioria". O juscraper passa a enviar "{novo}"; use votacao="{novo}".',
        )
        inp = apply_input_pipeline_search(
            InputCJSGTJAP,
            "TJAPScraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            orgao=orgao,
            numero_processo=numero_processo,
            numero_acordao=numero_acordao,
            numero_ano=numero_ano,
            palavras_exatas=palavras_exatas,
            relator=relator,
            secretaria=secretaria,
            classe=classe,
            votacao=votacao,
            origem=origem,
        )
        return cjsg_download_manager(
            pesquisa=inp.pesquisa,
            paginas=inp.paginas_normalizadas,
            request_fn=self._request_with_retry,
            sleep_time=self.sleep_time,
            orgao=inp.orgao,
            numero_cnj=inp.numero_processo,
            numero_acordao=inp.numero_acordao,
            numero_ano=inp.numero_ano,
            palavras_exatas=inp.palavras_exatas,
            relator=inp.relator,
            secretaria=inp.secretaria,
            classe=inp.classe,
            votacao=inp.votacao,
            origem=inp.origem,
        )

    def cjsg_parse(self, resultados_brutos: list) -> pd.DataFrame:
        """Converte as respostas JSON baixadas da CJSG em DataFrame.

        Args:
            resultados_brutos: Lista das respostas JSON brutas da API do TJAP.

        Returns:
            Uma linha por decisão.
        """
        return cjsg_parse_manager(resultados_brutos)
