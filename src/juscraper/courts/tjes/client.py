"""Scraper for the Tribunal de Justica do Espirito Santo (TJES)."""

from collections.abc import Mapping
from datetime import date
from typing import Any, ClassVar

import pandas as pd

from juscraper.core.http import HTTPScraper, RequestPolicy
from juscraper.utils.params import apply_input_pipeline_search, resolve_deprecated_alias

from .download import CJPG_CORE, CJSG_CORES, DEFAULT_CORE, DEFAULT_PER_PAGE, cjsg_download
from .parse import cjsg_parse
from .schemas import CoreCJSG, InputCJPGTJES, InputCJSGTJES, OrdenacaoCJSG


class TJESScraper(HTTPScraper):
    """Scraper for the Tribunal de Justica do Espirito Santo."""

    BASE_URL = "https://sistemas.tjes.jus.br/consulta-jurisprudencia/api"

    perfis_http: ClassVar[Mapping[str, RequestPolicy]] = {
        "cjsg": RequestPolicy(timeout=30, expect_json=True),
    }

    def __init__(self, *, politica: Mapping[str, Mapping[str, Any]] | None = None):
        super().__init__("TJES", politica=politica)

    def cpopg(self, id_cnj: str | list[str]):
        """Stub: first-instance case lookup not implemented for TJES."""
        raise NotImplementedError("Consulta de processos de 1 grau nao implementada para TJES.")

    def cposg(self, id_cnj: str | list[str]):
        """Stub: second-instance case lookup not implemented for TJES."""
        raise NotImplementedError("Consulta de processos de 2 grau nao implementada para TJES.")

    def cjsg_download(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        core: CoreCJSG = DEFAULT_CORE,
        busca_exata: bool = False,
        relator: str | None = None,
        orgao_julgador: str | None = None,
        classe: str | None = None,
        jurisdicao: str | None = None,
        assunto: str | None = None,
        ordenacao: OrdenacaoCJSG | None = None,
        tamanho_pagina: int = DEFAULT_PER_PAGE,
        data_julgamento_inicio: str | date | None = None,
        data_julgamento_fim: str | date | None = None,
        **kwargs,
    ) -> list:
        """Baixa os resultados JSON brutos da pesquisa de jurisprudência do TJES.

        Aceita os mesmos parâmetros e aliases deprecados de :meth:`cjsg`; veja lá
        a lista completa.

        Returns:
            Respostas JSON brutas, uma por página.
        """
        if core not in CJSG_CORES:
            raise ValueError(
                f"cjsg nao suporta core='{core}'. Use um de: {', '.join(sorted(CJSG_CORES))}. "
                "Para primeiro grau (pje1g), use cjpg()."
            )
        relator = resolve_deprecated_alias(kwargs, "magistrado", "relator", relator)
        classe = resolve_deprecated_alias(kwargs, "classe_judicial", "classe", classe)
        tamanho_pagina = resolve_deprecated_alias(
            kwargs, "per_page", "tamanho_pagina", tamanho_pagina, sentinel=DEFAULT_PER_PAGE
        )
        inp = apply_input_pipeline_search(
            InputCJSGTJES,
            "TJESScraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            core=core,
            busca_exata=busca_exata,
            relator=relator,
            orgao_julgador=orgao_julgador,
            classe=classe,
            jurisdicao=jurisdicao,
            assunto=assunto,
            ordenacao=ordenacao,
            tamanho_pagina=tamanho_pagina,
        )
        return cjsg_download(
            pesquisa=inp.pesquisa,
            paginas=inp.paginas_normalizadas,
            core=inp.core,
            busca_exata=inp.busca_exata,
            # TJES only supports a single date range (dataIni/dataFim mapped to dt_juntada)
            data_inicio=inp.data_julgamento_inicio,
            data_fim=inp.data_julgamento_fim,
            magistrado=inp.relator,
            orgao_julgador=inp.orgao_julgador,
            classe_judicial=inp.classe,
            jurisdicao=inp.jurisdicao,
            assunto=inp.assunto,
            ordenacao=inp.ordenacao,
            per_page=inp.tamanho_pagina,
            request_fn=self._request_with_retry,
        )

    def cjsg_parse(self, resultados_brutos: list) -> pd.DataFrame:
        """Converte os resultados brutos da pesquisa do TJES em DataFrame.

        Args:
            resultados_brutos: Respostas JSON brutas devolvidas por
                :meth:`cjsg_download`.

        Returns:
            Uma linha por decisão.
        """
        return cjsg_parse(resultados_brutos)

    def cjsg(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        core: CoreCJSG = DEFAULT_CORE,
        busca_exata: bool = False,
        relator: str | None = None,
        orgao_julgador: str | None = None,
        classe: str | None = None,
        jurisdicao: str | None = None,
        assunto: str | None = None,
        ordenacao: OrdenacaoCJSG | None = None,
        tamanho_pagina: int = DEFAULT_PER_PAGE,
        data_julgamento_inicio: str | date | None = None,
        data_julgamento_fim: str | date | None = None,
        **kwargs,
    ) -> pd.DataFrame:
        """Pesquisa jurisprudência do TJES (download + parse).

        Devolve um DataFrame pronto para análise.

        Args:
            pesquisa: Termo de busca. ``query`` e ``termo`` são aceitos como
                aliases deprecados.
            paginas: Páginas a baixar (1-based). ``int`` n significa as páginas
                1..n. ``None`` baixa todas as páginas disponíveis.
            core: Core do Solr a consultar: ``pje2g`` (default), ``pje2g_mono``,
                ``legado``, ``turma_recursal_legado``. Para o primeiro grau
                (``pje1g``), usar :meth:`cjpg`.
            busca_exata: Se ``True``, faz busca exata.
            relator: Nome do magistrado (exato, em maiúsculas). Aceita o alias
                deprecado ``magistrado``.
            orgao_julgador: Órgão julgador.
            classe: Classe judicial. Aceita o alias deprecado ``classe_judicial``.
            jurisdicao: Jurisdição.
            assunto: Assunto.
            ordenacao: Ordem dos resultados; ``None`` (default) ordena por
                relevância. As opções dependem do ``core``: ``"dt_juntada desc"``,
                ``"dt_juntada asc"``, ``"nr_processo asc"``, ``"nr_processo desc"``
                para ``pje2g``, ``pje2g_mono`` e :meth:`cjpg` (``pje1g``);
                ``"data_julgamento desc|asc"``, ``"data_publicacao desc|asc"``,
                ``"numero_processo_legado asc|desc"`` para ``legado``;
                ``"data_julgamento desc|asc"``, ``"num_processo asc|desc"`` para
                ``turma_recursal_legado``.
            tamanho_pagina: Resultados por página (default 20 — particularidade do
                backend Elasticsearch do TJES; demais tribunais usam 10). Aceita
                ``per_page`` como alias deprecado.
            data_julgamento_inicio: Início do intervalo de datas: ``DD/MM/AAAA``,
                ``DD-MM-AAAA``, ``AAAA-MM-DD``, ``AAAA/MM/DD``, ``date`` ou
                ``datetime``, enviado ao backend como ``AAAA-MM-DD``. O TJES usa
                ``dataIni``/``dataFim``, que filtram por ``dt_juntada``. O backend
                não expõe um filtro separado de data de publicação; passar
                ``data_publicacao_*`` levanta ``TypeError``.
            data_julgamento_fim: Fim do intervalo de datas (mesmos formatos e mesmo
                campo do backend).
            **kwargs: Aliases deprecados (ver abaixo).

        Aliases deprecados:
            * ``query`` / ``termo`` -> ``pesquisa``
            * ``magistrado`` -> ``relator``
            * ``classe_judicial`` -> ``classe``
            * ``per_page`` -> ``tamanho_pagina``
            * ``data_inicio`` / ``data_fim`` -> ``data_julgamento_inicio`` / ``data_julgamento_fim``
            * ``data_julgamento_de`` / ``data_julgamento_ate`` -> ``data_julgamento_inicio`` / ``data_julgamento_fim``

        Returns:
            Uma linha por decisão.
        """
        brutos = self.cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            core=core,
            busca_exata=busca_exata,
            relator=relator,
            orgao_julgador=orgao_julgador,
            classe=classe,
            jurisdicao=jurisdicao,
            assunto=assunto,
            ordenacao=ordenacao,
            tamanho_pagina=tamanho_pagina,
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            **kwargs,
        )
        return self.cjsg_parse(brutos)

    # --- cjpg (first instance / 1o grau) ---

    def _cjpg_download_internal(self, pesquisa, paginas, kwargs, *, tamanho_pagina):
        """Shared logic for cjpg_download — delegates to cjsg_download with core=pje1g."""
        relator = resolve_deprecated_alias(
            kwargs, "magistrado", "relator", kwargs.pop("relator", None)
        )
        classe = resolve_deprecated_alias(
            kwargs, "classe_judicial", "classe", kwargs.pop("classe", None)
        )
        tamanho_pagina = resolve_deprecated_alias(
            kwargs, "per_page", "tamanho_pagina", tamanho_pagina, sentinel=DEFAULT_PER_PAGE
        )
        busca_exata = kwargs.pop("busca_exata", False)
        orgao_julgador = kwargs.pop("orgao_julgador", None)
        jurisdicao = kwargs.pop("jurisdicao", None)
        assunto = kwargs.pop("assunto", None)
        ordenacao = kwargs.pop("ordenacao", None)
        inp = apply_input_pipeline_search(
            InputCJPGTJES,
            "TJESScraper.cjpg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            busca_exata=busca_exata,
            relator=relator,
            orgao_julgador=orgao_julgador,
            classe=classe,
            jurisdicao=jurisdicao,
            assunto=assunto,
            ordenacao=ordenacao,
            tamanho_pagina=tamanho_pagina,
        )

        return cjsg_download(
            pesquisa=inp.pesquisa,
            paginas=inp.paginas_normalizadas,
            core=CJPG_CORE,
            busca_exata=inp.busca_exata,
            # TJES only supports a single date range (dataIni/dataFim mapped to dt_juntada)
            data_inicio=inp.data_julgamento_inicio,
            data_fim=inp.data_julgamento_fim,
            magistrado=inp.relator,
            orgao_julgador=inp.orgao_julgador,
            classe_judicial=inp.classe,
            jurisdicao=inp.jurisdicao,
            assunto=inp.assunto,
            ordenacao=inp.ordenacao,
            per_page=inp.tamanho_pagina,
            request_fn=self._request_with_retry,
        )

    def cjpg_download(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        tamanho_pagina: int = DEFAULT_PER_PAGE,
        **kwargs,
    ) -> list:
        """Baixa os resultados JSON brutos da pesquisa de primeiro grau do TJES (core ``pje1g``).

        Aceita os mesmos parâmetros de :meth:`cjpg`, cujos filtros são os de
        :meth:`cjsg`, exceto ``core``.
        ``per_page`` é aceito como alias deprecado de ``tamanho_pagina``.

        Returns:
            Respostas JSON brutas, uma por página.
        """
        resultados: list = self._cjpg_download_internal(
            pesquisa, paginas, kwargs, tamanho_pagina=tamanho_pagina
        )
        return resultados

    def cjpg_parse(self, resultados_brutos: list) -> pd.DataFrame:
        """Converte os resultados brutos de primeiro grau do TJES em DataFrame.

        Args:
            resultados_brutos: Respostas JSON brutas devolvidas por
                :meth:`cjpg_download`.

        Returns:
            Uma linha por decisão.
        """
        return cjsg_parse(resultados_brutos)

    def cjpg(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        tamanho_pagina: int = DEFAULT_PER_PAGE,
        **kwargs,
    ) -> pd.DataFrame:
        """Pesquisa jurisprudência de primeiro grau do TJES (download + parse).

        Atalho para :meth:`cjpg_download` + :meth:`cjpg_parse`. Consulta o core
        ``pje1g``.

        Args:
            pesquisa: Termo de busca. ``query`` e ``termo`` são aceitos como
                aliases deprecados.
            paginas: Páginas a baixar (1-based); ``None`` baixa todas.
            tamanho_pagina: Resultados por página (default 20). Aceita ``per_page``
                como alias deprecado.
            **kwargs: Filtros aceitos por :class:`InputCJPGTJES`, os mesmos de
                :meth:`cjsg` exceto ``core``; a semântica de cada um está lá:

                * ``busca_exata`` (bool): Se ``True``, faz busca exata.
                * ``relator`` (str | None): Nome do magistrado (exato, em
                  maiúsculas).
                * ``orgao_julgador`` (str | None): Órgão julgador.
                * ``classe`` (str | None): Classe judicial.
                * ``jurisdicao`` (str | None): Jurisdição.
                * ``assunto`` (str | None): Assunto.
                * ``ordenacao`` (OrdenacaoCJPG | None): Ordem dos resultados:
                  ``"dt_juntada desc"``, ``"dt_juntada asc"``,
                  ``"nr_processo asc"`` ou ``"nr_processo desc"``; ``None``
                  (default) ordena por relevância.
                * ``data_julgamento_inicio`` / ``data_julgamento_fim``
                  (str | date | None): Intervalo de datas, que o TJES aplica a
                  ``dt_juntada``.

        Aliases deprecados:
            * ``query`` / ``termo`` -> ``pesquisa``
            * ``magistrado`` -> ``relator``
            * ``classe_judicial`` -> ``classe``
            * ``per_page`` -> ``tamanho_pagina``
            * ``data_inicio`` / ``data_fim`` -> ``data_julgamento_inicio`` / ``data_julgamento_fim``
            * ``data_julgamento_de`` / ``data_julgamento_ate`` -> ``data_julgamento_inicio`` / ``data_julgamento_fim``

        Returns:
            Uma linha por decisão.
        """
        brutos = self._cjpg_download_internal(pesquisa, paginas, kwargs, tamanho_pagina=tamanho_pagina)
        return cjsg_parse(brutos)
