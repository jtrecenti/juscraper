"""
Scraper for the Tribunal de Justica do Estado da Bahia (TJBA).
"""

from collections.abc import Mapping
from datetime import date
from typing import Any, ClassVar

import pandas as pd

from juscraper.core.http import HTTPScraper, RequestPolicy
from juscraper.utils.params import apply_input_pipeline_search, pop_deprecated_alias, resolve_deprecated_alias

from .download import cjsg_download
from .parse import cjsg_parse
from .schemas import InputCJSGTJBA, OrdenadoPor


class TJBAScraper(HTTPScraper):
    """Scraper for the Tribunal de Justica do Estado da Bahia."""

    BASE_URL = "https://jurisprudenciaws.tjba.jus.br/graphql"

    perfis_http: ClassVar[Mapping[str, RequestPolicy]] = {
        "cjsg": RequestPolicy(timeout=60),
    }

    def __init__(self, *, sleep_time: float = 1.0, politica: Mapping[str, Mapping[str, Any]] | None = None):
        super().__init__("TJBA", sleep_time=sleep_time, politica=politica)

    def cpopg(self, id_cnj: str | list[str]):
        """Stub: first-instance case consultation not implemented for TJBA."""
        raise NotImplementedError("Consulta de processos de 1 grau nao implementada para TJBA.")

    def cposg(self, id_cnj: str | list[str]):
        """Stub: second-instance case consultation not implemented for TJBA."""
        raise NotImplementedError("Consulta de processos de 2 grau nao implementada para TJBA.")

    def cjsg_download(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        numero_recurso: str | None = None,
        orgaos: list | None = None,
        relatores: list | None = None,
        classe: list | None = None,
        data_publicacao_inicio: str | date | None = None,
        data_publicacao_fim: str | date | None = None,
        segundo_grau: bool = True,
        turmas_recursais: bool = True,
        tipo_acordaos: bool = True,
        tipo_decisoes_monocraticas: bool = True,
        ordenado_por: OrdenadoPor = "dataPublicacao",
        tamanho_pagina: int = 10,
        auto_chunk: bool = True,
        **kwargs,
    ) -> list:
        """Baixa os resultados brutos da pesquisa de jurisprudência do TJBA.

        Aceita os mesmos parâmetros e aliases deprecados de :meth:`cjsg`; veja lá
        a lista completa.

        Returns:
            Lista dos dicionários brutos da resposta GraphQL, um por página.
        """
        tamanho_pagina = resolve_deprecated_alias(
            kwargs, "items_per_page", "tamanho_pagina", tamanho_pagina, sentinel=10
        )
        # Popa alias plural antes do pydantic — sem isso o schema canonico
        # (que so declara o singular ``classe``) trataria ``classes`` como
        # ``extra_forbidden``. Usa ``classe is not None`` (nao ``in kwargs``)
        # para nao tratar ``classe=None`` explicito como conflito. Refs #232.
        if "classes" in kwargs:
            if classe is not None:
                kwargs.pop("classes")
                raise ValueError(
                    "Nao e possivel passar 'classe' e 'classes' simultaneamente."
                )
            classe = pop_deprecated_alias(kwargs, "classes", "classe")
        inp = apply_input_pipeline_search(
            InputCJSGTJBA,
            "TJBAScraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            data_publicacao_inicio=data_publicacao_inicio,
            data_publicacao_fim=data_publicacao_fim,
            numero_recurso=numero_recurso,
            orgaos=orgaos,
            relatores=relatores,
            classe=classe,
            segundo_grau=segundo_grau,
            turmas_recursais=turmas_recursais,
            tipo_acordaos=tipo_acordaos,
            tipo_decisoes_monocraticas=tipo_decisoes_monocraticas,
            ordenado_por=ordenado_por,
            tamanho_pagina=tamanho_pagina,
            auto_chunk=auto_chunk,
        )
        return cjsg_download(
            pesquisa=inp.pesquisa,
            paginas=inp.paginas_normalizadas,
            numero_recurso=inp.numero_recurso,
            orgaos=inp.orgaos,
            relatores=inp.relatores,
            classes=inp.classe,
            data_publicacao_inicio=inp.data_publicacao_inicio,
            data_publicacao_fim=inp.data_publicacao_fim,
            segundo_grau=inp.segundo_grau,
            turmas_recursais=inp.turmas_recursais,
            tipo_acordaos=inp.tipo_acordaos,
            tipo_decisoes_monocraticas=inp.tipo_decisoes_monocraticas,
            ordenado_por=inp.ordenado_por,
            items_per_page=inp.tamanho_pagina,
            auto_chunk=inp.auto_chunk,
            request_fn=self._request_with_retry,
            sleep_time=self.sleep_time,
        )

    def cjsg_parse(self, resultados_brutos: list) -> pd.DataFrame:
        """Converte os resultados brutos do TJBA em DataFrame.

        Args:
            resultados_brutos: Dicionários da resposta, como devolvidos por
                :meth:`cjsg_download`.

        Returns:
            Uma linha por decisão.
        """
        return cjsg_parse(resultados_brutos)

    def cjsg(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        numero_recurso: str | None = None,
        orgaos: list | None = None,
        relatores: list | None = None,
        classe: list | None = None,
        data_publicacao_inicio: str | date | None = None,
        data_publicacao_fim: str | date | None = None,
        segundo_grau: bool = True,
        turmas_recursais: bool = True,
        tipo_acordaos: bool = True,
        tipo_decisoes_monocraticas: bool = True,
        ordenado_por: OrdenadoPor = "dataPublicacao",
        tamanho_pagina: int = 10,
        auto_chunk: bool = True,
        **kwargs,
    ) -> pd.DataFrame:
        """Pesquisa jurisprudência do TJBA (download + parse).

        Devolve um DataFrame pronto para análise.

        Args:
            pesquisa: Termo de busca. ``query`` e ``termo`` são aceitos como
                aliases deprecados.
            paginas: Páginas a baixar (1-based). ``int``: ``paginas=3`` baixa as
                páginas 1 a 3. ``range``: ``range(1, 4)`` baixa as páginas 1 a 3.
                ``None``: baixa todas.
                O portal só entrega os 10.000 primeiros resultados de uma busca
                (1000 páginas de 10): página pedida além desse teto levanta
                ``ValueError`` antes de qualquer requisição, e ``None`` numa busca
                maior divide a busca por data de publicação (ver ``auto_chunk``).
            numero_recurso: Número do processo/recurso.
            orgaos: Lista de IDs de órgão julgador.
            relatores: Lista de IDs de relator.
            classe: Lista de IDs de classe. ``classes`` (plural) é aceito como
                alias deprecado (emite :class:`DeprecationWarning`). Refs #232.
            data_publicacao_inicio: Data inicial de publicação: ``DD/MM/AAAA``,
                ``DD-MM-AAAA``, ``AAAA-MM-DD``, ``AAAA/MM/DD``, ``date`` ou
                ``datetime``.
            data_publicacao_fim: Data final de publicação (mesmos formatos).
            segundo_grau: Inclui resultados do segundo grau (default ``True``).
            turmas_recursais: Inclui resultados das turmas recursais (default
                ``True``).
            tipo_acordaos: Inclui acórdãos (default ``True``).
            tipo_decisoes_monocraticas: Inclui decisões monocráticas (default
                ``True``).
            ordenado_por: ``"dataPublicacao"`` (default) ou ``"relevancia"``.
            tamanho_pagina: Resultados por página (default 10). Aceita
                ``items_per_page`` como alias deprecado (emite
                ``DeprecationWarning``).
            auto_chunk: Default ``True``. Com ``paginas=None``, a busca com mais de
                10.000 resultados é dividida em janelas de data de publicação que
                cabem no teto do portal, da mais recente para a mais antiga, e todas
                são baixadas; a soma pode diferir do total inicial, porque o portal
                segue indexando. A primeira divisão emite ``UserWarning`` com o
                total e o número aproximado de requisições (~1 s cada). O dia que
                sozinho passa do teto vem até o teto, com ``UserWarning``. Se uma
                requisição falha depois da divisão, levanta
                ``ColetaParcialError``: ``.resultado`` traz o DataFrame do que foi
                baixado (também em ``cjsg_download``), e a mensagem diz o
                intervalo que falta. Com ``False``, ``None`` baixa as páginas até
                o teto e emite ``UserWarning``. Sem efeito com ``paginas``
                explícito.
            **kwargs: Aliases deprecados (ver abaixo).

        Aliases deprecados:
            * ``query`` / ``termo`` -> ``pesquisa``
            * ``items_per_page`` -> ``tamanho_pagina``
            * ``classes`` -> ``classe`` (refs #232)
            * ``data_publicacao_de`` / ``data_publicacao_ate`` -> ``data_publicacao_inicio`` / ``data_publicacao_fim``

        Returns:
            Resultados de jurisprudência, uma linha por decisão.
        """
        brutos = self.cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            numero_recurso=numero_recurso,
            orgaos=orgaos,
            relatores=relatores,
            classe=classe,
            data_publicacao_inicio=data_publicacao_inicio,
            data_publicacao_fim=data_publicacao_fim,
            segundo_grau=segundo_grau,
            turmas_recursais=turmas_recursais,
            tipo_acordaos=tipo_acordaos,
            tipo_decisoes_monocraticas=tipo_decisoes_monocraticas,
            ordenado_por=ordenado_por,
            tamanho_pagina=tamanho_pagina,
            auto_chunk=auto_chunk,
            **kwargs,
        )
        return self.cjsg_parse(brutos)
