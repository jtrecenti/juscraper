"""
Module for the scraper of the Court of Justice of the Federal District and Territories (TJDFT).
"""

from collections.abc import Mapping
from typing import Any, ClassVar

import pandas as pd

from juscraper.core.http import HTTPScraper, RequestPolicy
from juscraper.core.parse_utils import coerce_date_columns
from juscraper.utils.params import apply_input_pipeline_search, resolve_deprecated_alias

from .download import cjsg_download
from .parse import cjsg_parse
from .schemas import InputCJSGTJDFT


class TJDFTScraper(HTTPScraper):
    """Scraper for the Court of Justice of the Federal District and Territories (TJDFT)."""

    BASE_URL = "https://jurisdf.tjdft.jus.br/api/v1/pesquisa"

    perfis_http: ClassVar[Mapping[str, RequestPolicy]] = {
        "cjsg": RequestPolicy(timeout=10),
    }

    def __init__(self, *, politica: Mapping[str, Mapping[str, Any]] | None = None):
        super().__init__("TJDFT", politica=politica)

    def cpopg(self, id_cnj: str | list[str]):
        """Stub for compatibility with BaseScraper."""
        raise NotImplementedError("TJDFT does not implement cpopg.")

    def cposg(self, id_cnj: str | list[str]):
        """Stub for compatibility with BaseScraper."""
        raise NotImplementedError("TJDFT does not implement cposg.")

    def cjsg_download(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        sinonimos: bool = True,
        espelho: bool = True,
        inteiro_teor: bool = False,
        tamanho_pagina: int | None = None,
        **kwargs,
    ) -> list:
        """Baixa as respostas cruas da pesquisa de jurisprudência do TJDFT.

        Aceita os mesmos filtros e aliases deprecados de :meth:`cjsg`; veja lá
        a lista completa.

        Args:
            pesquisa (str): Termo de busca livre.
            paginas (int | list | range | None): Páginas 1-based; ``None``
                busca todas.
            sinonimos (bool): Inclui sinônimos do termo na busca.
            espelho (bool): Pesquisa no espelho do acórdão.
            inteiro_teor (bool): Pesquisa também no inteiro teor.
            tamanho_pagina (int | None): Resultados por página, de 1 a 40
                (acima disso a API responde HTTP 400). ``None`` usa 10.

        Returns:
            Os registros do JSON da API, um por acórdão.
        """
        # Sentinela ``None``: ``tamanho_pagina=10`` com o alias tambem e conflito.
        tamanho_pagina = resolve_deprecated_alias(
            kwargs, "quantidade_por_pagina", "tamanho_pagina", tamanho_pagina
        )
        if tamanho_pagina is not None:
            kwargs["tamanho_pagina"] = tamanho_pagina
        inp = apply_input_pipeline_search(
            InputCJSGTJDFT,
            "TJDFTScraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            sinonimos=sinonimos,
            espelho=espelho,
            inteiro_teor=inteiro_teor,
        )
        brutos: list = cjsg_download(
            query=inp.pesquisa,
            paginas=inp.paginas,
            request_fn=self._request_with_retry,
            sinonimos=inp.sinonimos,
            espelho=inp.espelho,
            inteiro_teor=inp.inteiro_teor,
            quantidade_por_pagina=inp.tamanho_pagina,
            base_url=self.BASE_URL,
            data_julgamento_inicio=inp.data_julgamento_inicio,
            data_julgamento_fim=inp.data_julgamento_fim,
            data_publicacao_inicio=inp.data_publicacao_inicio,
            data_publicacao_fim=inp.data_publicacao_fim,
        )
        return brutos

    def cjsg_parse(self, resultados_brutos: list) -> list:
        """Converte os registros brutos da API em linhas, uma por registro.

        As colunas saem como em :meth:`cjsg`, mas as datas ficam no texto ISO
        da API: quem as converte é :meth:`cjsg`.

        Args:
            resultados_brutos (list): Registros devolvidos por
                :meth:`cjsg_download`.

        Returns:
            Uma linha por registro, como dicionário.
        """
        parsed: list = cjsg_parse(resultados_brutos)
        return parsed

    def cjsg(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        **kwargs,
    ) -> pd.DataFrame:
        """Pesquisa jurisprudência do TJDFT (download + parse).

        Consulta a API REST do portal ``jurisdf.tjdft.jus.br``. Os filtros de
        data viram entradas de ``termosAcessorios`` no JSON enviado à API.

        Args:
            pesquisa (str): Termo de busca livre.
            paginas (int | list | range | None): Páginas 1-based; ``None``
                busca todas. ``paginas=3`` baixa as páginas 1 a 3.
            **kwargs: Filtros aceitos por :class:`InputCJSGTJDFT`:

                * ``sinonimos`` (bool): Inclui sinônimos do termo na busca.
                  Default ``True``. Backend: ``sinonimos``.
                * ``espelho`` (bool): Pesquisa no espelho do acórdão.
                  Default ``True``. Backend: ``espelho``.
                * ``inteiro_teor`` (bool): Pesquisa também no inteiro teor,
                  o que amplia o resultado. Default ``False``. Backend:
                  ``inteiroTeor``.
                * ``tamanho_pagina`` (int): Resultados por página, de 1 a 40;
                  acima de 40 a API responde HTTP 400, e o schema recusa
                  antes da requisição. Default ``10``.
                * ``data_julgamento_inicio`` / ``data_julgamento_fim``
                  (str | date | None): Intervalo de julgamento. Aceita
                  ``DD/MM/AAAA``, ``DD-MM-AAAA``, ``AAAA-MM-DD``,
                  ``AAAA/MM/DD``, ``date`` ou ``datetime``. ``None`` não
                  filtra. Backend: ``dataJulgamento``.
                * ``data_publicacao_inicio`` / ``data_publicacao_fim``
                  (str | date | None): Intervalo de publicação, nos mesmos
                  formatos. ``None`` não filtra. Backend: ``dataPublicacao``.

        Aliases deprecados:
            * ``query`` / ``termo`` -> ``pesquisa``
            * ``data_inicio`` / ``data_fim`` -> ``data_julgamento_inicio`` / ``_fim``
            * ``data_julgamento_de`` / ``_ate`` -> ``data_julgamento_inicio`` / ``_fim``
            * ``data_publicacao_de`` / ``_ate`` -> ``data_publicacao_inicio`` / ``_fim``
            * ``quantidade_por_pagina`` -> ``tamanho_pagina``

        Raises:
            TypeError: Quando ``pesquisa`` falta ou quando todos os erros são
                kwargs desconhecidos.
            ValueError: Quando uma data é inválida, o início é posterior ao
                fim, ou um parâmetro e seu alias deprecado são passados
                juntos (uma data, ou ``tamanho_pagina`` com
                ``quantidade_por_pagina``).
            ValidationError: Para os demais erros de validação do schema,
                como ``tamanho_pagina`` acima de 40.

        Avisos:
            ``UserWarning``: Quando um intervalo de datas vem só com o início
                ou só com o fim. O fim que falta vira a data atual; o início
                que falta vira 01/01/1990.
            ``DeprecationWarning``: Quando um alias deprecado é usado.

        Returns:
            Uma linha por acórdão ou decisão monocrática, com ``processo``,
                ``ementa``, ``relator``, ``orgao_julgador``,
                ``data_julgamento`` e ``data_publicacao``; as demais chaves do
                JSON da API (``decisao``, ``codigoClasseCnj``,
                ``turmaRecursal``...) saem com o nome da API. As duas datas
                saem como ``datetime.date``, a data em UTC do instante que a
                API devolve (``2026-10-28T03:00:00.000Z`` vira 28/10/2026), a
                mesma que os filtros ``data_*`` usam. Decisões monocráticas
                (``base == "decisoes"``) não têm data de julgamento:
                ``data_julgamento`` fica vazia nelas.

        Examples: Exemplo
            >>> import juscraper as jus
            >>> tjdft = jus.scraper("tjdft")
            >>> df = tjdft.cjsg(
            ...     "lucros cessantes",
            ...     paginas=1,
            ...     data_julgamento_inicio="01/01/2024",
            ...     data_julgamento_fim="31/03/2024",
            ... )

        See Also:
            :class:`InputCJSGTJDFT`: fonte dos filtros aceitos.
        """
        brutos = self.cjsg_download(pesquisa=pesquisa, paginas=paginas, **kwargs)
        dados = self.cjsg_parse(brutos)
        df = pd.DataFrame(dados)
        # Data em UTC de proposito: e a que o filtro ``data_*`` da API usa.
        coerce_date_columns(df, ["data_julgamento", "data_publicacao"], date_format="ISO8601")
        return df
