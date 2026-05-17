"""
Scraper for the Tribunal de Justica de Pernambuco (TJPE).
"""


import pandas as pd

from juscraper.core.http import HTTPScraper
from juscraper.utils.params import apply_input_pipeline_search, resolve_deprecated_alias

from .download import cjsg_download
from .parse import cjsg_parse
from .schemas import InputCJSGTJPE


class TJPEScraper(HTTPScraper):
    """Scraper for the Tribunal de Justica de Pernambuco."""

    BASE_URL = "https://www.tjpe.jus.br/consultajurisprudenciaweb"

    def __init__(self):
        super().__init__("TJPE")

    def cpopg(self, id_cnj: str | list[str]):
        """Stub: first instance case consultation not implemented for TJPE."""
        raise NotImplementedError("Consulta de processos de 1 grau não implementada para TJPE.")

    def cposg(self, id_cnj: str | list[str]):
        """Stub: second instance case consultation not implemented for TJPE."""
        raise NotImplementedError("Consulta de processos de 2 grau não implementada para TJPE.")

    def cjsg_download(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        data_julgamento_inicio: str | None = None,
        data_julgamento_fim: str | None = None,
        relator: str | None = None,
        classe: str | None = None,
        assunto: str | None = None,
        meio_tramitacao: str | None = None,
        tipo_decisao: str = "acordaos",
        **kwargs,
    ) -> list:
        """Baixa as paginas brutas do cjsg do TJPE.

        Aceita os mesmos filtros de :meth:`cjsg`; veja la a lista completa.

        Returns:
            list: Lista de strings HTML brutas, uma por pagina.
        """
        classe = resolve_deprecated_alias(kwargs, "classe_cnj", "classe", classe)
        assunto = resolve_deprecated_alias(kwargs, "assunto_cnj", "assunto", assunto)
        inp = apply_input_pipeline_search(
            InputCJSGTJPE,
            "TJPEScraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            relator=relator,
            classe=classe,
            assunto=assunto,
            meio_tramitacao=meio_tramitacao,
            tipo_decisao=tipo_decisao,
        )
        return cjsg_download(
            pesquisa=inp.pesquisa,
            paginas=inp.paginas,
            request_fn=self._request_with_retry,
            data_julgamento_inicio=inp.data_julgamento_inicio,
            data_julgamento_fim=inp.data_julgamento_fim,
            relator=inp.relator,
            classe_cnj=inp.classe,
            assunto_cnj=inp.assunto,
            meio_tramitacao=inp.meio_tramitacao,
            tipo_decisao=inp.tipo_decisao,
        )

    def cjsg_parse(self, raw_pages: list) -> pd.DataFrame:
        """Parseia as paginas brutas de :meth:`cjsg_download` em DataFrame."""
        return cjsg_parse(raw_pages)

    def cjsg(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        data_julgamento_inicio: str | None = None,
        data_julgamento_fim: str | None = None,
        relator: str | None = None,
        classe: str | None = None,
        assunto: str | None = None,
        meio_tramitacao: str | None = None,
        tipo_decisao: str = "acordaos",
        **kwargs,
    ) -> pd.DataFrame:
        """Busca jurisprudencia no TJPE.

        Wrapper trivial (``download → parse``) sobre :meth:`cjsg_download`.
        O backend e JSF/RichFaces: o fluxo carrega o ``ViewState`` da
        ``consulta.xhtml`` e propaga entre requests; a paginacao usa
        AJAX RichFaces em ``resultado.xhtml`` retornando XML envolto em
        ``<![CDATA[HTML]]>``.

        Args:
            pesquisa (str): Termo de busca livre (ementa). Aceita os aliases
                deprecados ``query`` / ``termo``.
            paginas (int | list | range | None): Paginas 1-based; ``None`` baixa
                todas. Default ``None``.
            data_julgamento_inicio (str): Data inicial de julgamento
                (``DD/MM/AAAA``, ``DD-MM-AAAA``, ``AAAA-MM-DD``, ``AAAA/MM/DD``,
                :class:`datetime.date` ou :class:`datetime.datetime`).
            data_julgamento_fim (str): Data final de julgamento (mesmos
                formatos de ``data_julgamento_inicio``).
            relator (str): Nome do relator (deve bater exatamente com o valor
                do dropdown do formulario).
            classe (str): Codigo CNJ da classe. Aceita o alias deprecado
                ``classe_cnj``.
            assunto (str): Codigo CNJ do assunto. Aceita o alias deprecado
                ``assunto_cnj``.
            meio_tramitacao (str): Filtro de meio de tramitacao
                (ex.: ``"ELETRONICO"``).
            tipo_decisao (str): ``"acordaos"`` (default), ``"monocraticas"`` ou
                ``"todos"``. Quando ``"todos"``, o backend marca os dois
                checkboxes e o fluxo passa pela pagina de escolha
                (``escolhaResultado.xhtml``).

        Todos os filtros do schema :class:`InputCJSGTJPE` estao listados
        acima como parametros nomeados. O ``**kwargs`` so e exposto para
        absorver aliases deprecados (listados abaixo) e qualquer kwarg
        desconhecido vira ``TypeError`` via ``raise_on_extra_kwargs``.

        Aliases deprecados (popados com ``DeprecationWarning`` antes do pydantic):
            * ``query`` / ``termo`` -> ``pesquisa``
            * ``classe_cnj`` -> ``classe``
            * ``assunto_cnj`` -> ``assunto``
            * ``data_inicio`` / ``data_fim`` -> ``data_julgamento_inicio`` / ``_fim``
            * ``data_julgamento_de`` / ``_ate`` -> ``data_julgamento_inicio`` / ``_fim``

        Raises:
            TypeError: Quando um kwarg desconhecido e passado.
            ValueError: Quando um canonico e seu alias deprecado sao passados
                simultaneamente.
            ValidationError: Quando um filtro tem formato invalido (ex.: data
                fora dos formatos aceitos, ``tipo_decisao`` fora do enum).

        Returns:
            pd.DataFrame: Uma linha por decisao. Colunas canonicas:
                ``processo``, ``classe``, ``assunto``, ``relator``,
                ``orgao_julgador``, ``data_julgamento``, ``data_publicacao``,
                ``ementa``, ``acordao``, ``meio_tramitacao``,
                ``url_inteiro_teor``.

        Exemplo:
            >>> import juscraper as jus
            >>> tjpe = jus.scraper("tjpe")
            >>> df = tjpe.cjsg("dano moral", paginas=range(1, 3),
            ...                tipo_decisao="acordaos")

        See also:
            :class:`InputCJSGTJPE` — schema pydantic e a fonte da verdade dos
            filtros aceitos.
        """
        raw = self.cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            relator=relator,
            classe=classe,
            assunto=assunto,
            meio_tramitacao=meio_tramitacao,
            tipo_decisao=tipo_decisao,
            **kwargs,
        )
        return self.cjsg_parse(raw)
