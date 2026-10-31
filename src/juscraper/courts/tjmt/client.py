"""
Scraper do Tribunal de Justiça do Estado de Mato Grosso (TJMT).
"""

import pandas as pd

from juscraper.core.http import HTTPScraper
from juscraper.utils.params import apply_input_pipeline_search, resolve_deprecated_alias

from .download import PRODUCTION_API_URL, cjsg_download
from .parse import CJSG_COLUMNS, cjsg_parse, coerce_tjmt_date_columns
from .schemas import InputCJSGTJMT


class TJMTScraper(HTTPScraper):
    """Scraper do Tribunal de Justiça do Estado de Mato Grosso (TJMT)."""

    BASE_URL = PRODUCTION_API_URL

    def __init__(self):
        super().__init__("TJMT")

    def cpopg(self, id_cnj: str | list[str]):
        """Consulta de processos de primeiro grau ainda não implementada no TJMT."""
        raise NotImplementedError("Consulta de processos de 1 grau nao implementada para TJMT.")

    def cposg(self, id_cnj: str | list[str]):
        """Consulta de processos de segundo grau ainda não implementada no TJMT."""
        raise NotImplementedError("Consulta de processos de 2 grau nao implementada para TJMT.")

    def cjsg_download(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        tipo_consulta: str = "Acordao",
        relator: str | None = None,
        orgao_julgador: str | None = None,
        classe: str | None = None,
        tipo_processo: str | None = None,
        thesaurus: bool = False,
        tamanho_pagina: int = 10,
        data_julgamento_inicio: str | None = None,
        data_julgamento_fim: str | None = None,
        data_publicacao_inicio: str | None = None,
        data_publicacao_fim: str | None = None,
        **kwargs,
    ) -> list:
        """Baixa resultados JSON brutos da API de jurisprudência do TJMT.

        Argumentos:
            pesquisa: Termo de pesquisa. Aceita ``query`` e ``termo`` como aliases deprecados.
            paginas: Páginas a baixar, baseadas em 1.
                inteiro: ``paginas=3`` baixa as páginas 1 a 3.
                ``range``: ``range(1, 4)`` baixa as páginas 1 a 3.
                ``None``: baixa todas as páginas disponíveis.
            tipo_consulta: ``"Acordao"`` ou ``"DecisaoMonocratica"``.
            relator: Filtro pelo nome do relator.
            orgao_julgador: Filtro pela câmara julgadora.
            classe: Filtro pela classe processual.
            tipo_processo: ``"Civel"`` ou ``"Criminal"``.
            thesaurus: Define se a pesquisa deve usar sinônimos.
            tamanho_pagina: Itens por página (padrão 10). Aceita
                ``quantidade_por_pagina`` como alias deprecado.
            data_julgamento_inicio: Data inicial do filtro (``yyyy-mm-dd``).
            data_julgamento_fim: Data final do filtro (``yyyy-mm-dd``).
            data_publicacao_inicio: Data inicial de publicação.
            data_publicacao_fim: Data final inclusiva de publicação.

        O backend atual aplica ``periodoDataDe/Ate`` à data de publicação.
        Filtros por data de julgamento continuam indisponíveis e geram
        ``NotImplementedError``.
        """
        tamanho_pagina = resolve_deprecated_alias(
            kwargs, "quantidade_por_pagina", "tamanho_pagina", tamanho_pagina, sentinel=10
        )
        inp = apply_input_pipeline_search(
            InputCJSGTJMT,
            "TJMTScraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            data_publicacao_inicio=data_publicacao_inicio,
            data_publicacao_fim=data_publicacao_fim,
            tipo_consulta=tipo_consulta,
            relator=relator,
            orgao_julgador=orgao_julgador,
            classe=classe,
            tipo_processo=tipo_processo,
            thesaurus=thesaurus,
            tamanho_pagina=tamanho_pagina,
        )
        return cjsg_download(
            pesquisa=inp.pesquisa,
            paginas=inp.paginas,
            tipo_consulta=inp.tipo_consulta,
            data_julgamento_inicio=inp.data_julgamento_inicio,
            data_julgamento_fim=inp.data_julgamento_fim,
            data_publicacao_inicio=inp.data_publicacao_inicio,
            data_publicacao_fim=inp.data_publicacao_fim,
            relator=inp.relator,
            orgao_julgador=inp.orgao_julgador,
            classe=inp.classe,
            tipo_processo=inp.tipo_processo,
            thesaurus=inp.thesaurus,
            quantidade_por_pagina=inp.tamanho_pagina,
            request_fn=self._request_with_retry,
            session=self.session,
        )

    def cjsg_parse(self, resultados_brutos: list, tipo_consulta: str = "Acordao") -> list[dict]:
        """Analisa resultados JSON brutos e produz registros estruturados.

        Argumentos:
            resultados_brutos: Lista de dicionários JSON brutos, um por página.
            tipo_consulta: ``"Acordao"`` ou ``"DecisaoMonocratica"``.

        Retorno:
            Lista de dicionários planos.
        """
        return cjsg_parse(resultados_brutos, tipo_consulta=tipo_consulta)

    def cjsg(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        tipo_consulta: str = "Acordao",
        relator: str | None = None,
        orgao_julgador: str | None = None,
        classe: str | None = None,
        tipo_processo: str | None = None,
        thesaurus: bool = False,
        tamanho_pagina: int = 10,
        data_julgamento_inicio: str | None = None,
        data_julgamento_fim: str | None = None,
        data_publicacao_inicio: str | None = None,
        data_publicacao_fim: str | None = None,
        **kwargs,
    ) -> pd.DataFrame:
        """Pesquisa jurisprudência do TJMT, baixando e analisando os resultados.

        Retorna um DataFrame pronto para análise.

        Aliases deprecados:
            * ``quantidade_por_pagina`` -> ``tamanho_pagina``
        """
        brutos = self.cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            tipo_consulta=tipo_consulta,
            relator=relator,
            orgao_julgador=orgao_julgador,
            classe=classe,
            tipo_processo=tipo_processo,
            thesaurus=thesaurus,
            tamanho_pagina=tamanho_pagina,
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            data_publicacao_inicio=data_publicacao_inicio,
            data_publicacao_fim=data_publicacao_fim,
            **kwargs,
        )
        dados = self.cjsg_parse(brutos, tipo_consulta=tipo_consulta)
        df = pd.DataFrame(dados, columns=CJSG_COLUMNS)
        coerce_tjmt_date_columns(df)
        return df
