"""Scraper for the Tribunal de Justiça do Rio Grande do Sul (TJRS)."""
from collections.abc import Mapping
from datetime import date
from typing import Any, ClassVar

import pandas as pd

from juscraper.core.http import HTTPScraper, RequestPolicy
from juscraper.utils.params import apply_input_pipeline_search

from .download import PERFIL_CJSG, cjsg_download_manager
from .parse import cjsg_parse_manager
from .schemas import InputCJSGTJRS


class TJRSScraper(HTTPScraper):
    """Scraper for the Tribunal de Justiça do Rio Grande do Sul."""

    BASE_URL = "https://www.tjrs.jus.br/buscas/jurisprudencia/ajax.php"
    DEFAULT_PARAMS: ClassVar[dict[str, str]] = {
        "tipo-busca": "jurisprudencia-mob",
        "client": "tjrs_index",
        "proxystylesheet": "tjrs_index",
        "lr": "lang_pt",
        "oe": "UTF-8",
        "ie": "UTF-8",
        "getfields": "*",
        "filter": "0",
        "entqr": "3",
        "content": "body",
        "accesskey": "p",
        "ulang": "",
        "entqrm": "0",
        "ud": "1",
        "start": "0",
        "aba": "jurisprudencia",
        "sort": "date:D:L:d1"
    }

    #: Perfil HTTP da busca de jurisprudência: nova tentativa em timeout e erro
    #: de conexão, e prazo de conexão curto para o portal fora do ar falhar logo.
    perfis_http: ClassVar[Mapping[str, RequestPolicy]] = {
        PERFIL_CJSG: RequestPolicy(
            timeout=(10, 30),
            retry_on_timeout=True,
            retry_on_connection_error=True,
            expect_json=True,
        ),
    }

    def __init__(self, *, politica: Mapping[str, Mapping[str, Any]] | None = None):
        """Cria o raspador.

        Args:
            politica: Ajustes por campo do perfil HTTP ``"cjsg"`` (ver
                :class:`~juscraper.core.http.RequestPolicy`), por exemplo
                ``{"cjsg": {"timeout": 60, "max_retries": 5}}``.
        """
        super().__init__("TJRS", politica=politica)

    def cpopg(self, id_cnj: str | list[str]):
        """Stub: Primeiro grau case consultation not implemented for TJRS."""
        raise NotImplementedError("Consulta de processos de 1º grau não implementada para TJRS.")

    def cposg(self, id_cnj: str | list[str]):
        """Stub: Segundo grau case consultation not implemented for TJRS."""
        raise NotImplementedError("Consulta de processos de 2º grau não implementada para TJRS.")

    def cjsg_download(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        classe: int | str | None = None,
        assunto: int | str | None = None,
        orgao_julgador: int | str | None = None,
        relator: int | str | None = None,
        data_julgamento_inicio: str | date | None = None,
        data_julgamento_fim: str | date | None = None,
        data_publicacao_inicio: str | date | None = None,
        data_publicacao_fim: str | date | None = None,
        tipo_processo: str | None = None,
        secao: str | None = None,
        **kwargs,
    ) -> list:
        """Baixa as páginas brutas da pesquisa de jurisprudência do TJRS.

        Aceita os mesmos parâmetros e aliases deprecados de :meth:`cjsg`;
        veja lá a lista completa.

        Returns:
            Lista com o JSON cru de cada página.
        """
        inp = apply_input_pipeline_search(
            InputCJSGTJRS,
            "TJRSScraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            data_publicacao_inicio=data_publicacao_inicio,
            data_publicacao_fim=data_publicacao_fim,
            classe=classe,
            assunto=assunto,
            orgao_julgador=orgao_julgador,
            relator=relator,
            tipo_processo=tipo_processo,
            secao=secao,
        )
        return cjsg_download_manager(
            termo=inp.pesquisa,
            paginas=inp.paginas_normalizadas,
            request_fn=self._request_with_retry,
            classe=inp.classe,
            assunto=inp.assunto,
            orgao_julgador=inp.orgao_julgador,
            relator=inp.relator,
            data_julgamento_inicio=inp.data_julgamento_inicio,
            data_julgamento_fim=inp.data_julgamento_fim,
            data_publicacao_inicio=inp.data_publicacao_inicio,
            data_publicacao_fim=inp.data_publicacao_fim,
            tipo_processo=inp.tipo_processo,
            secao=inp.secao,
        )

    def cjsg_parse(self, resultados_brutos: list) -> 'pd.DataFrame':
        """
        Extracts relevant data from the raw results returned by TJRS.
        Returns a DataFrame with the decisions.
        """
        return cjsg_parse_manager(resultados_brutos)

    def cjsg(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        classe: int | str | None = None,
        assunto: int | str | None = None,
        orgao_julgador: int | str | None = None,
        relator: int | str | None = None,
        data_julgamento_inicio: str | date | None = None,
        data_julgamento_fim: str | date | None = None,
        data_publicacao_inicio: str | date | None = None,
        data_publicacao_fim: str | date | None = None,
        tipo_processo: str | None = None,
        secao: str | None = None,
        **kwargs,
    ) -> 'pd.DataFrame':
        """Pesquisa jurisprudência do TJRS (download + parse).

        Args:
            pesquisa: Termo de busca livre; obrigatório.
            paginas: Páginas 1-based; ``None``
                busca todas. ``paginas=3`` baixa as páginas 1 a 3.
            classe: Código da classe processual (coluna
                ``cod_classe_cnj`` do resultado; ``460`` é Recurso Inominado).
            assunto: Código do assunto (coluna
                ``cod_assunto_cnj``).
            orgao_julgador: Código do órgão julgador
                (coluna ``cod_org_julg``).
            relator: Código do relator (coluna
                ``cod_relator``); casa com o relator ou com o redator do
                acórdão. Nestes quatro filtros, o portal aceita só o código:
                um nome levanta ``ValidationError``.
            data_julgamento_inicio: Início do intervalo
                de julgamento. Aceita ``DD/MM/AAAA``, ``DD-MM-AAAA``,
                ``AAAA-MM-DD``, ``AAAA/MM/DD``, ``date`` ou ``datetime``.
            data_julgamento_fim: Fim do intervalo de
                julgamento, nos mesmos formatos.
            data_publicacao_inicio: Início do intervalo
                de publicação, nos mesmos formatos.
            data_publicacao_fim: Fim do intervalo de
                publicação, nos mesmos formatos.
            tipo_processo: Tipo de processo.
            secao: ``"civel"``, ``"crime"`` ou ``None`` (as
                duas), sem distinção de caixa nem de acento (``"Cível"``
                vale). Outro valor levanta ``ValidationError``.
            **kwargs: Só os aliases deprecados abaixo; os filtros aceitos são
                os parâmetros explícitos, campos de :class:`InputCJSGTJRS`.

        Aliases deprecados:
            * ``query`` / ``termo`` -> ``pesquisa``
            * ``data_inicio`` / ``data_fim`` -> ``data_julgamento_inicio`` / ``data_julgamento_fim``
            * ``data_julgamento_de`` / ``data_julgamento_ate`` -> ``data_julgamento_inicio`` / ``data_julgamento_fim``
            * ``data_publicacao_de`` / ``data_publicacao_ate`` -> ``data_publicacao_inicio`` / ``data_publicacao_fim``

        Raises:
            TypeError: Quando ``pesquisa`` falta ou quando todos os erros são
                kwargs desconhecidos.
            ValueError: Quando uma data é inválida, o início é posterior ao
                fim, ou um parâmetro e seu alias deprecado são passados juntos.
            ValidationError: Para os demais erros de validação do schema.
            TJRSBuscaError: Quando o portal responde com erro do Solr no lugar
                dos resultados, como em ``pesquisa`` com aspas sem fechar
                (:class:`juscraper.courts.tjrs.download.TJRSBuscaError`).

        Avisos:
            ``UserWarning``: Quando um intervalo de datas vem só com o início
                ou só com o fim. O fim que falta vira a data atual; o início
                que falta vira 01/01/1990.
            ``DeprecationWarning``: Quando um alias deprecado é usado.

        Returns:
            Uma linha por decisão, com ``processo``, ``relator``,
                ``orgao_julgador``, ``data_julgamento``, ``data_publicacao``,
                ``classe``, ``assunto`` e ``ementa``, entre outras colunas.
                ``relator`` é o relator do processo; quando o redator do
                acórdão é outra pessoa, o nome dela vem em ``nome_redator``.

        Examples: Exemplo
            >>> from datetime import date
            >>> import juscraper as jus
            >>> tjrs = jus.scraper("tjrs")
            >>> df = tjrs.cjsg(
            ...     "dano moral",
            ...     paginas=1,
            ...     data_julgamento_inicio=date(2024, 1, 1),
            ...     data_julgamento_fim="31/03/2024",
            ... )

        See Also:
            :class:`InputCJSGTJRS`: fonte dos filtros aceitos.
        """
        brutos = self.cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            classe=classe,
            assunto=assunto,
            orgao_julgador=orgao_julgador,
            relator=relator,
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            data_publicacao_inicio=data_publicacao_inicio,
            data_publicacao_fim=data_publicacao_fim,
            tipo_processo=tipo_processo,
            secao=secao,
            **kwargs,
        )
        return self.cjsg_parse(brutos)
