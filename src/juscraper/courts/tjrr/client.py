"""Scraper for the Tribunal de Justica de Roraima (TJRR)."""

from collections.abc import Mapping
from datetime import date
from typing import Any, ClassVar

import pandas as pd
from requests.cookies import remove_cookie_by_name

from juscraper.core.http import HTTPScraper, RequestPolicy
from juscraper.utils.params import apply_input_pipeline_search

from .download import cjsg_download_manager
from .parse import cjsg_parse_manager
from .schemas import InputCJSGTJRR


class TJRRScraper(HTTPScraper):
    """Scraper for the Tribunal de Justica de Roraima (TJRR).

    Uses the JSF/PrimeFaces-based jurisprudence search at jurisprudencia.tjrr.jus.br.
    """

    BASE_URL = "https://jurisprudencia.tjrr.jus.br"

    perfis_http: ClassVar[Mapping[str, RequestPolicy]] = {
        "formulario": RequestPolicy(timeout=30),
        "cjsg": RequestPolicy(timeout=60),
    }

    def __init__(
        self,
        verbose: int = 0,
        download_path: str | None = None,
        sleep_time: float = 1.0,
        **kwargs: Any,
    ):
        super().__init__(
            "TJRR",
            verbose=verbose,
            download_path=download_path,
            sleep_time=sleep_time,
            **kwargs,
        )

    def cpopg(self, id_cnj: str | list[str]):
        """Stub: first instance case consultation not implemented for TJRR."""
        raise NotImplementedError("Consulta de processos de 1o grau nao implementada para TJRR.")

    def cposg(self, id_cnj: str | list[str]):
        """Stub: second instance case consultation not implemented for TJRR."""
        raise NotImplementedError("Consulta de processos de 2o grau nao implementada para TJRR.")

    def cjsg(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        relator: list | None = None,
        orgao_julgador: list | None = None,
        especie: list | None = None,
        **kwargs,
    ) -> pd.DataFrame:
        """Busca jurisprudencia no TJRR.

        Args:
            pesquisa: Termo de busca livre (busca na ementa).
            paginas: Paginas 1-based; ``None`` baixa
                todas. Default ``None``. O portal mostra duas tabelas, cada uma
                com paginador proprio: acordaos e decisoes monocraticas. A
                pagina ``n`` traz a pagina ``n`` de cada uma (ate 10 + 10
                linhas); com ``None``, o download vai ate o fim da mais longa.
            relator: Lista de nomes regimentais de
                magistrados (ex.: ``["ALMIRO PADILHA", "ERICK LINHARES"]``).
                O backend usa um ``SelectManyCheckbox``
                (``menuinicial:relatorList``) cujos values sao beans Java
                serializados; o scraper baixa o form GET inicial e resolve
                cada nome regimental para o bean correspondente. Match
                insensivel a caixa e diacritico — ``"cristovao suter"``,
                ``"Cristóvão Suter"`` e ``"CRISTÓVÃO SUTER"`` resolvem
                para o mesmo magistrado. ``ValueError`` se algum nome nao
                bater (a mensagem lista os nomes na forma canonica:
                UPPERCASE com acento). Refs #158.
            orgao_julgador: Codigos do orgao julgador
                (ex.: ``["PRIMEIRA_TURMA_CIVEL"]``). Backend:
                ``menuinicial:tipoOrgaoList``.
            especie: Codigos do tipo de decisao
                (ex.: ``["ACORDAO"]``). Backend: ``menuinicial:tipoEspecieList``.
            **kwargs: Filtros aceitos pelo schema :class:`InputCJSGTJRR`.
                Listados abaixo (todos opcionais; ``None`` = sem filtro):

                * ``data_julgamento_inicio`` / ``data_julgamento_fim``
                  (str | date | None): ``DD/MM/AAAA``, ``DD-MM-AAAA``,
                  ``AAAA-MM-DD``, ``AAAA/MM/DD``, ``date`` ou ``datetime``.
                  Backend: ``menuinicial:datainicial_input``
                  / ``menuinicial:datafinal_input``.

        Aliases deprecados (popados com ``DeprecationWarning`` antes do pydantic):
            * ``query`` / ``termo`` -> ``pesquisa``
            * ``data_inicio`` / ``data_fim`` -> ``data_julgamento_inicio`` / ``_fim``
            * ``data_julgamento_de`` / ``_ate`` -> ``data_julgamento_inicio`` / ``_fim``

        Raises:
            TypeError: Quando um kwarg desconhecido e passado.
            ValueError: Quando ``relator`` contem nome nao encontrado no form.
            ValidationError: Quando um filtro tem formato invalido.

        Returns:
            DataFrame com as decisoes: acordaos e decisoes monocraticas
                juntos. A coluna ``tipo_decisao`` diz a origem de cada linha
                (``"acordao"`` ou ``"monocratica"``).

        See also:
            :class:`InputCJSGTJRR` — schema pydantic e a fonte da verdade dos
            filtros aceitos.
        """
        return self.cjsg_parse(self.cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            relator=relator,
            orgao_julgador=orgao_julgador,
            especie=especie,
            **kwargs,
        ))

    def cjsg_download(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        relator: list | None = None,
        orgao_julgador: list | None = None,
        especie: list | None = None,
        data_julgamento_inicio: str | date | None = None,
        data_julgamento_fim: str | date | None = None,
        **kwargs,
    ) -> list:
        """Baixa as páginas HTML brutas do TJRR.

        Aceita os mesmos filtros de :meth:`cjsg`; veja lá a lista completa.

        Returns:
            Lista do HTML bruto, uma string por página.
        """
        inp = apply_input_pipeline_search(
            InputCJSGTJRR,
            "TJRRScraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            relator=relator,
            orgao_julgador=orgao_julgador,
            especie=especie,
        )
        self._descartar_sessao_jsf()
        return cjsg_download_manager(
            pesquisa=inp.pesquisa,
            paginas=inp.paginas_normalizadas,
            request_fn=self._request_with_retry,
            sleep_time=self.sleep_time,
            relator=inp.relator,
            data_inicio=inp.data_julgamento_inicio or "",
            data_fim=inp.data_julgamento_fim or "",
            orgao_julgador=inp.orgao_julgador,
            especie=inp.especie,
        )

    def _descartar_sessao_jsf(self) -> None:
        """Descarta o ``JSESSIONID`` para que a busca comece numa sessão JSF nova.

        O portal guarda a última busca na sessão: com o ``JSESSIONID`` de uma
        busca anterior, o GET inicial devolve a página de resultados, sem o
        form ``menuinicial``, e o POST da busca nova é ignorado em silêncio,
        trazendo os resultados da busca anterior (conferido ao vivo).
        """
        remove_cookie_by_name(self.session.cookies, "JSESSIONID")

    def cjsg_parse(self, resultados_brutos: list) -> pd.DataFrame:
        """Converte as páginas HTML baixadas em DataFrame.

        Returns:
            Uma linha por decisão.
        """
        return cjsg_parse_manager(resultados_brutos)
