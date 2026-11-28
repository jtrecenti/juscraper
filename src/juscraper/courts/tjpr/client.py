"""Scraper for the Court of Justice of Paraná (TJPR)."""

from collections.abc import Mapping
from datetime import date
from typing import Any, ClassVar

import pandas as pd
import requests

from juscraper.core.http import HTTPScraper, RequestPolicy
from juscraper.utils.params import SEARCH_ALIASES, apply_input_pipeline_search, normalize_pesquisa

from .download import BASE_URL, cjsg_download
from .parse import cjsg_parse
from .schemas import InputCJSGTJPR


def _validar_incluir_corte_idh(valor: object) -> None:
    # A opção só vale no parse, e o parser usa a verdade do Python: ``"false"``
    # a ligaria. Daí a checagem aqui, com o contrato do ``StrictBool`` de
    # ``InputCJSGTJPR``, e a recusa em ``cjsg_download``, cujo schema a
    # aceitaria e a ignoraria.
    if not isinstance(valor, bool):
        raise TypeError(f"incluir_corte_idh deve ser bool, recebeu {type(valor).__name__}.")


class TJPRScraper(HTTPScraper):
    """Scraper for the Court of Justice of Paraná."""

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0"
    )

    perfis_http: ClassVar[Mapping[str, RequestPolicy]] = {
        "cjsg": RequestPolicy(timeout=60),
        "ementa": RequestPolicy(timeout=30),
    }

    def __init__(self, *, politica: Mapping[str, Mapping[str, Any]] | None = None) -> None:
        """Cria o raspador do TJPR.

        Args:
            politica: Ajuste dos perfis HTTP ``"cjsg"`` (home e busca) e
                ``"ementa"`` (ementa completa), por exemplo
                ``{"cjsg": {"timeout": 120}}``.
        """
        super().__init__("TJPR", politica=politica)

    def _configure_session(self, session: requests.Session) -> None:
        """TJPR's portal applies User-Agent gating — keep the Chrome UA."""
        session.headers.update({"User-Agent": self.USER_AGENT})

    def cjsg_download(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        data_julgamento_inicio: str | date | None = None,
        data_julgamento_fim: str | date | None = None,
        data_publicacao_inicio: str | date | None = None,
        data_publicacao_fim: str | date | None = None,
        **kwargs,
    ) -> list:
        """Downloads raw results from the TJPR jurisprudence search (multiple pages).

        Returns a list of HTMLs (one per page).

        Args:
            pesquisa: Search term. ``termo`` is accepted as deprecated alias.
            paginas: Pages to download (1-based).
                int: paginas=3 downloads pages 1-3.
                range: range(1, 4) downloads pages 1-3.
                None: downloads all available pages.
            data_julgamento_inicio: Início do intervalo
                de julgamento, nos formatos aceitos por :meth:`cjsg`.
            data_julgamento_fim: Fim do intervalo de
                julgamento.
            data_publicacao_inicio: Início do intervalo
                de publicação.
            data_publicacao_fim: Fim do intervalo de
                publicação.
            **kwargs: Aliases deprecados de :meth:`cjsg`.

        Raises:
            TypeError: Com ``incluir_corte_idh``, que não muda o download: as
                páginas brutas sempre trazem as linhas da Corte IDH. Para
                mantê-las, passe ``incluir_corte_idh=True`` a :meth:`cjsg_parse`.
            ValueError: Quando a primeira página baixada (a menor pedida) não
                permite fixar o total de páginas; os casos estão em
                :func:`juscraper.courts.tjpr.download.extract_total_pages`. O
                scraper levanta depois da primeira página, em vez de estimar.
            ColetaParcialError: Uma página falhou depois de outras já
                baixadas, como em :meth:`cjsg`; ``resultado`` traz as
                baixadas já lidas, em DataFrame, sem as linhas da Corte IDH
                e com as ementas longas truncadas.
        """
        if "incluir_corte_idh" in kwargs:
            raise TypeError(
                "TJPRScraper.cjsg_download() não usa incluir_corte_idh: as páginas "
                "brutas sempre trazem as linhas da Corte IDH. Passe "
                "incluir_corte_idh a cjsg_parse()."
            )
        return self._baixar(
            pesquisa, paginas, data_julgamento_inicio, data_julgamento_fim,
            data_publicacao_inicio, data_publicacao_fim, kwargs,
        )

    def _baixar(
        self,
        pesquisa: str | None,
        paginas: int | list | range | None,
        data_julgamento_inicio: str | date | None,
        data_julgamento_fim: str | date | None,
        data_publicacao_inicio: str | date | None,
        data_publicacao_fim: str | date | None,
        kwargs: dict[str, Any],
        *,
        incluir_corte_idh: bool = False,
    ) -> list:
        """Páginas brutas da busca.

        Raises:
            ColetaParcialError: Uma página falhou depois de outras baixadas;
                ``resultado`` traz as baixadas, lidas com ``incluir_corte_idh``.
        """
        inp = apply_input_pipeline_search(
            InputCJSGTJPR,
            "TJPRScraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            data_publicacao_inicio=data_publicacao_inicio,
            data_publicacao_fim=data_publicacao_fim,
        )
        brutos: list = cjsg_download(
            home_url=BASE_URL,
            pesquisa=inp.pesquisa,
            paginas=inp.paginas_normalizadas,
            data_julgamento_inicio=inp.data_julgamento_inicio,
            data_julgamento_fim=inp.data_julgamento_fim,
            data_publicacao_inicio=inp.data_publicacao_inicio,
            data_publicacao_fim=inp.data_publicacao_fim,
            request_fn=self._request_with_retry,
            # Sem ``request_fn``: a leitura do parcial não faz requisição.
            ler_parcial=lambda paginas: cjsg_parse(paginas, inp.pesquisa, incluir_corte_idh=incluir_corte_idh),
        )
        return brutos

    def cjsg_parse(
        self,
        resultados_brutos: list,
        criterio: str | None = None,
        *,
        incluir_corte_idh: bool = False,
    ) -> pd.DataFrame:
        """Extracts relevant data from the HTMLs returned by TJPR.

        Returns a DataFrame with the decisions.

        Args:
            resultados_brutos: HTMLs devolvidos por :meth:`cjsg_download`.
            criterio: Termo da busca, repassado ao portal ao
                buscar a ementa completa das linhas truncadas em "Leia mais..".
                Só muda o destaque do termo, que o texto descarta: sem ele as
                ementas também vêm completas.
            incluir_corte_idh: Mantém os precedentes da Corte IDH que o
                portal mistura à tabela, como em :meth:`cjsg`. Default ``False``.

        Raises:
            TypeError: Quando ``incluir_corte_idh`` não é ``bool``.
        """
        _validar_incluir_corte_idh(incluir_corte_idh)
        return cjsg_parse(
            resultados_brutos,
            criterio,
            request_fn=self._request_with_retry,
            incluir_corte_idh=incluir_corte_idh,
        )

    def cjsg(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        data_julgamento_inicio: str | date | None = None,
        data_julgamento_fim: str | date | None = None,
        data_publicacao_inicio: str | date | None = None,
        data_publicacao_fim: str | date | None = None,
        *,
        incluir_corte_idh: bool = False,
        **kwargs,
    ) -> pd.DataFrame:
        """Searches for TJPR jurisprudence in a simplified way (download + parse).

        Returns a ready-to-analyze DataFrame.

        O portal mistura à tabela até 10 precedentes da Corte Interamericana de
        Direitos Humanos (Corte IDH) por página. Por padrão eles ficam de fora:
        uma página rende menos de 50 linhas e o total fica abaixo da contagem
        "registro(s) encontrado(s)" do portal, que soma as duas fontes.

        Args:
            pesquisa: Termo de busca livre.
            paginas: Páginas 1-based; None busca
                todas.
            data_julgamento_inicio: Início do intervalo
                de julgamento. Aceita ``DD/MM/AAAA``, ``DD-MM-AAAA``,
                ``AAAA-MM-DD``, ``AAAA/MM/DD``, ``date`` ou ``datetime``.
            data_julgamento_fim: Fim do intervalo de
                julgamento, nos mesmos formatos.
            data_publicacao_inicio: Início do intervalo
                de publicação, nos mesmos formatos.
            data_publicacao_fim: Fim do intervalo de
                publicação, nos mesmos formatos.
            incluir_corte_idh: Mantém os precedentes da Corte IDH no
                resultado. Default ``False``. Ligado, o DataFrame ganha as
                colunas ``fonte`` ("TJPR" ou "Corte IDH") e ``caso`` (nome do
                caso, só nas linhas da Corte IDH); nessas linhas ``processo``,
                ``orgao_julgador`` e ``relator`` ficam vazios, porque o portal
                não os tem. O portal não aplica a esses casos os filtros de
                data: eles vêm com a própria ``data_julgamento``, fora do
                intervalo pedido.
            **kwargs: Só os aliases deprecados abaixo; os filtros aceitos são
                os parâmetros explícitos, campos de :class:`InputCJSGTJPR`.

        Aliases deprecados (popados com ``DeprecationWarning`` antes do
        pydantic):

            * ``query`` / ``termo`` -> ``pesquisa``
            * ``data_inicio`` / ``data_fim`` -> ``data_julgamento_inicio`` / ``data_julgamento_fim``
            * ``data_julgamento_de`` / ``data_julgamento_ate`` -> ``data_julgamento_inicio`` / ``data_julgamento_fim``
            * ``data_publicacao_de`` / ``data_publicacao_ate`` -> ``data_publicacao_inicio`` / ``data_publicacao_fim``

        Raises:
            TypeError: Quando todos os erros são kwargs desconhecidos, ou
                quando ``incluir_corte_idh`` não é ``bool``.
            ValidationError: Para os demais erros de validação do schema.
            ValueError: Quando a primeira página baixada (a menor pedida) não
                permite fixar o total de páginas; ver :meth:`cjsg_download`.
            ColetaParcialError: Uma página falhou (prazo estourado, erro HTTP
                depois das tentativas) quando outras já tinham sido baixadas.
                A busca para ali: ``resultado`` traz as páginas anteriores, já
                lidas, e a mensagem diz as que faltam, para pedir de novo com
                ``paginas=``. Nesse parcial as ementas longas ficam truncadas
                em "Leia mais..", porque completá-las custaria uma requisição
                por linha a um portal que acabou de falhar. Se a falha é na
                primeira requisição, sobe a exceção original.

        Returns:
            Uma linha por decisão, com ``processo``,
                ``orgao_julgador``, ``relator``, ``data_julgamento`` e ``ementa``,
                mais ``fonte`` e ``caso`` quando ``incluir_corte_idh=True``.
                ``ementa`` é ``None`` na decisão monocrática que o portal manda
                sem ementa.

        Examples: Exemplo
            >>> import juscraper as jus
            >>> tjpr = jus.scraper("tjpr")
            >>> df = tjpr.cjsg("dano moral", paginas=1, incluir_corte_idh=True)
            >>> corte_idh = df[df["fonte"] == "Corte IDH"]

        See Also:
            :class:`InputCJSGTJPR`: fonte dos filtros aceitos.
        """
        # Resolve search alias here so cjsg_parse receives the actual term
        # for inteiro-teor lookups. Strip apenas SEARCH_ALIASES (query/termo)
        # para evitar re-pass duplicado; date aliases (data_inicio/data_fim,
        # *_de/*_ate) seguem em kwargs e sao normalizados pelo pipeline em
        # cjsg_download via normalize_datas.
        _validar_incluir_corte_idh(incluir_corte_idh)
        pesquisa_resolved = normalize_pesquisa(pesquisa, **kwargs)
        for alias in SEARCH_ALIASES:
            kwargs.pop(alias, None)
        brutos = self._baixar(
            pesquisa_resolved, paginas, data_julgamento_inicio, data_julgamento_fim,
            data_publicacao_inicio, data_publicacao_fim, kwargs,
            incluir_corte_idh=incluir_corte_idh,
        )
        return self.cjsg_parse(brutos, pesquisa_resolved, incluir_corte_idh=incluir_corte_idh)

    def cpopg(self, id_cnj: str | list[str]):
        """Stub: Primeiro grau case consultation not implemented for TJPR."""
        raise NotImplementedError("Consulta de processos de 1º grau não implementada para TJPR.")

    def cposg(self, id_cnj: str | list[str]):
        """Stub: Segundo grau case consultation not implemented for TJPR."""
        raise NotImplementedError("Consulta de processos de 2º grau não implementada para TJPR.")
