"""
Scraper do Tribunal de Justiça do Estado de Mato Grosso (TJMT).
"""

import pandas as pd

from juscraper.core.http import HTTPScraper
from juscraper.utils.method_context import preserve_public_method_error_name
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
        tipo_processo: str | None = None,
        thesaurus: bool = False,
        tamanho_pagina: int = 10,
        data_publicacao_inicio: str | None = None,
        data_publicacao_fim: str | None = None,
        **kwargs,
    ) -> list:
        """Baixa as respostas JSON brutas da API de jurisprudência do TJMT.

        Aceita os mesmos parâmetros, filtros, aliases e exceções de
        :meth:`cjsg`; veja lá a lista completa. Cada página baixada é uma
        resposta da API, sem parsear.

        Returns:
            list[dict]: Resposta JSON de cada página, na ordem pedida.
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
            data_publicacao_inicio=data_publicacao_inicio,
            data_publicacao_fim=data_publicacao_fim,
            tipo_consulta=tipo_consulta,
            relator=relator,
            orgao_julgador=orgao_julgador,
            tipo_processo=tipo_processo,
            thesaurus=thesaurus,
            tamanho_pagina=tamanho_pagina,
        )
        return cjsg_download(
            pesquisa=inp.pesquisa,
            paginas=inp.paginas,
            tipo_consulta=inp.tipo_consulta,
            data_publicacao_inicio=inp.data_publicacao_inicio,
            data_publicacao_fim=inp.data_publicacao_fim,
            relator=inp.relator,
            orgao_julgador=inp.orgao_julgador,
            tipo_processo=inp.tipo_processo,
            thesaurus=inp.thesaurus,
            quantidade_por_pagina=inp.tamanho_pagina,
            request_fn=self._request_with_retry,
            session=self.session,
        )

    def cjsg_parse(self, resultados_brutos: list, tipo_consulta: str = "Acordao") -> list[dict]:
        """Converte as respostas de :meth:`cjsg_download` em registros planos.

        Args:
            resultados_brutos (list[dict]): Respostas JSON brutas, uma por
                página.
            tipo_consulta (str): ``"Acordao"`` ou ``"DecisaoMonocratica"``.
                Mantido por compatibilidade; a resposta da API já traz o
                tipo de cada documento.

        Returns:
            list[dict]: Um dicionário por documento, com as colunas descritas
            em :meth:`cjsg`.
        """
        return cjsg_parse(resultados_brutos, tipo_consulta=tipo_consulta)

    @preserve_public_method_error_name
    def cjsg(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        tipo_consulta: str = "Acordao",
        relator: str | None = None,
        orgao_julgador: str | None = None,
        tipo_processo: str | None = None,
        thesaurus: bool = False,
        tamanho_pagina: int = 10,
        data_publicacao_inicio: str | None = None,
        data_publicacao_fim: str | None = None,
        **kwargs,
    ) -> pd.DataFrame:
        """Pesquisa jurisprudência do TJMT (acórdãos ou decisões monocráticas).

        Delega para :meth:`cjsg_download` e :meth:`cjsg_parse`. Antes da busca,
        lê a configuração pública do portal (URL da API e token) nos scripts
        de ``jurisprudencia.tjmt.jus.br``.

        A API devolve no máximo os 10.000 primeiros resultados de uma
        consulta; páginas além desse teto respondem HTTP 500.

        Args:
            pesquisa (str | None): Termo livre buscado no documento.
            paginas (int | list | range | None): Páginas 1-based; ``None``
                baixa todas, até o teto de 10.000 resultados. Página pedida
                além do teto levanta ``ValueError``.
            tipo_consulta (str): ``"Acordao"`` (default) ou
                ``"DecisaoMonocratica"``.
            relator (str | None): Nome do relator. A API casa só o nome
                exato; acentos, espaços repetidos e caixa são normalizados
                (``"João da Silva"`` vai como ``"JOAO DA SILVA"``). A API
                atual não aceita mais o identificador numérico, que é
                rejeitado antes da rede. ``None`` não filtra.
            orgao_julgador (str | None): Nome do órgão julgador, como
                aparece na coluna ``orgao_julgador`` (ex.:
                ``"PRIMEIRA CÂMARA DE DIREITO PRIVADO"``), com a mesma
                normalização de ``relator``. ``None`` não filtra.
            tipo_processo (str | None): ``"Civel"``, ``"Cível"`` ou
                ``"Criminal"``. ``None`` não filtra.
            thesaurus (bool): Se ``True``, a API amplia a busca com
                sinônimos. Default ``False``.
            tamanho_pagina (int): Documentos por página, de 1 a 10.000.
                Default 10.
            data_publicacao_inicio (str | None): Início do intervalo de
                publicação, em ``DD/MM/AAAA`` ou ``AAAA-MM-DD``. Com só
                ``data_publicacao_fim``, assume o piso
                ``OPEN_ENDED_DATE_FLOOR`` e emite ``UserWarning``.
            data_publicacao_fim (str | None): Fim do intervalo de
                publicação, inclusivo: o dia informado entra inteiro. Com só
                ``data_publicacao_inicio``, assume a data de hoje e emite
                ``UserWarning``.
            **kwargs: Só os aliases deprecados abaixo. Qualquer outro nome,
                inclusive ``data_julgamento_inicio``/``data_julgamento_fim``
                e ``classe``, que a API não filtra, levanta ``TypeError``.

        Aliases deprecados (popados com ``DeprecationWarning`` antes do pydantic):
            * ``query`` / ``termo`` -> ``pesquisa``
            * ``quantidade_por_pagina`` -> ``tamanho_pagina``
            * ``data_publicacao_de`` / ``_ate`` -> ``data_publicacao_inicio`` / ``_fim``
            * ``data_inicio`` / ``data_fim`` -> ``data_julgamento_inicio`` / ``_fim``,
              que o TJMT não aceita: depois do aviso, levanta ``TypeError``.

        Raises:
            TypeError: Kwarg desconhecido ou sem suporte na API
                (``data_julgamento_*``, ``classe``).
            ValidationError: Para os demais erros de validação do schema,
                como ``relator`` ou ``orgao_julgador`` passados como número e
                ``tamanho_pagina`` menor que 1.
            ValueError: Data inválida ou início depois do fim; ``relator``
                ou ``orgao_julgador`` só com dígitos; ``tipo_consulta`` ou
                ``tipo_processo`` desconhecido; ``tamanho_pagina`` acima de
                10.000; página além do teto de 10.000 resultados.
            TJMTConfigError: A configuração pública do portal não foi
                encontrada ou aponta para outra API.
            TJMTResponseError: A API respondeu com erro ou num formato
                inesperado.

        Avisos:
            ``UserWarning``: com ``paginas=None``, quando a consulta tem mais
            de 10.000 resultados; baixa só os que cabem no teto, e a
            mensagem traz o total e quantos vieram. Também quando só um dos
            lados do intervalo de publicação é informado.

        Returns:
            pd.DataFrame: Uma linha por documento, com as colunas de
            ``CJSG_COLUMNS`` em :mod:`juscraper.courts.tjmt.parse`
            (``processo``, ``ementa``, ``relator``, ``orgao_julgador``,
            ``data_julgamento``, ``data_publicacao`` e outras, descritas em
            :class:`OutputCJSGTJMT`). Datas vêm como ``datetime.date``. Busca
            sem resultados devolve DataFrame vazio com as mesmas colunas.

        Examples: Exemplo
            >>> import juscraper as jus
            >>> tjmt = jus.scraper("tjmt")
            >>> df = tjmt.cjsg(
            ...     "dano moral",
            ...     paginas=1,
            ...     data_publicacao_inicio="2025-03-10",
            ...     data_publicacao_fim="2025-03-10",
            ... )

        See Also:
            :class:`InputCJSGTJMT`: fonte dos filtros aceitos.
        """
        brutos = self.cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            tipo_consulta=tipo_consulta,
            relator=relator,
            orgao_julgador=orgao_julgador,
            tipo_processo=tipo_processo,
            thesaurus=thesaurus,
            tamanho_pagina=tamanho_pagina,
            data_publicacao_inicio=data_publicacao_inicio,
            data_publicacao_fim=data_publicacao_fim,
            **kwargs,
        )
        dados = self.cjsg_parse(brutos, tipo_consulta=tipo_consulta)
        df = pd.DataFrame(dados, columns=CJSG_COLUMNS)
        coerce_tjmt_date_columns(df)
        return df
