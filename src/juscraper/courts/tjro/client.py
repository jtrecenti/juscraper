"""Scraper for the Tribunal de Justica de Rondonia (TJRO)."""

from collections.abc import Mapping
from typing import Any, ClassVar

import pandas as pd

from juscraper.core.http import HTTPScraper, RequestPolicy
from juscraper.utils.params import apply_input_pipeline_search, resolve_deprecated_alias, to_iso_date

from .download import cjsg_download_manager
from .parse import cjsg_parse_manager
from .schemas import InputCJSGTJRO


class TJROScraper(HTTPScraper):
    """Scraper for the Tribunal de Justica de Rondonia (TJRO).

    Uses the JURIS Elasticsearch backend at juris-back.tjro.jus.br.
    """

    BASE_URL = "https://juris.tjro.jus.br"

    perfis_http: ClassVar[Mapping[str, RequestPolicy]] = {
        "cjsg": RequestPolicy(timeout=30),
    }

    def __init__(
        self,
        verbose: int = 0,
        download_path: str | None = None,
        sleep_time: float = 1.0,
        **kwargs: Any,
    ):
        super().__init__(
            "TJRO",
            verbose=verbose,
            download_path=download_path,
            sleep_time=sleep_time,
            **kwargs,
        )

    def cpopg(self, id_cnj: str | list[str]):
        """Stub: first instance case consultation not implemented for TJRO."""
        raise NotImplementedError("Consulta de processos de 1o grau nao implementada para TJRO.")

    def cposg(self, id_cnj: str | list[str]):
        """Stub: second instance case consultation not implemented for TJRO."""
        raise NotImplementedError("Consulta de processos de 2o grau nao implementada para TJRO.")

    def cjsg(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        tipo: list | None = None,
        numero_processo: str | None = None,
        relator: str | None = None,
        orgao_julgador: int | str | None = None,
        orgao_julgador_colegiado: int | str | None = None,
        classe: str | None = None,
        instancia: list | None = None,
        termo_exato: bool = False,
        auto_chunk: bool = True,
        **kwargs,
    ) -> pd.DataFrame:
        """Busca jurisprudencia no TJRO.

        Args:
            pesquisa: Termo de busca livre.
            paginas: Paginas 1-based; ``None`` baixa
                todas. Default ``None``. O portal so entrega os 10.000
                primeiros resultados de uma busca (1000 paginas): pagina
                pedida alem da 1000 levanta ``ValueError`` antes de qualquer
                requisicao, e ``None`` numa busca maior divide a busca por
                data de julgamento (ver ``auto_chunk``).
            tipo: Tipos de documento. Default backend
                ``["EMENTA"]``. O backend compara o valor exato, com acento
                e em maiusculas: ``"EMENTA"``, ``"ACÓRDÃO"``, ``"DECISÃO"``,
                ``"SENTENÇA"`` e ``"VOTO"``. ``"ACORDAO"`` ou ``"ementa"``
                devolvem zero resultados.
            numero_processo: Numero CNJ. Aceita o alias deprecado
                ``nr_processo``.
            relator: Nome do relator. Aceita o alias deprecado
                ``magistrado`` (refs #129).
            orgao_julgador: ID do orgao julgador.
            orgao_julgador_colegiado: ID do orgao colegiado.
            classe: Nome da classe judicial. Aceita o alias deprecado
                ``classe_judicial`` (refs #129).
            instancia: Instancias (ex.: ``[1]``, ``[2]``, ``[1, 2]``).
            termo_exato: Busca por termo exato.
            auto_chunk: Default ``True``. Com ``paginas=None``, a busca
                com mais de 10.000 resultados e dividida em janelas de data de
                julgamento que cabem no teto do portal, da mais recente para a
                mais antiga, e todas sao baixadas: a ordem por relevancia vale
                dentro de cada janela, nao entre elas, e a soma pode diferir
                do total inicial, porque o portal segue indexando. A
                primeira divisao emite ``UserWarning`` com o total e o numero
                aproximado de requisicoes (~1 s cada, 10 resultados por
                pagina). O dia que sozinho passa do teto vem ate o teto, com
                ``UserWarning``. Com ``False``,
                ``None`` baixa as 1000 primeiras paginas e emite
                ``UserWarning``. Sem efeito com ``paginas`` explicito.
            **kwargs: Filtros aceitos pelo schema :class:`InputCJSGTJRO`.
                Listados abaixo (todos opcionais; ``None`` = sem filtro):

                * ``data_julgamento_inicio`` / ``data_julgamento_fim``
                  (str | date | None): ``DD/MM/AAAA``, ``DD-MM-AAAA``,
                  ``AAAA-MM-DD``, ``AAAA/MM/DD``, ``date`` ou ``datetime``.

        Aliases deprecados:
            * ``query`` / ``termo`` -> ``pesquisa``
            * ``nr_processo`` -> ``numero_processo``
            * ``magistrado`` -> ``relator``
            * ``classe_judicial`` -> ``classe``
            * ``data_inicio`` / ``data_fim`` -> ``data_julgamento_inicio`` / ``data_julgamento_fim``
            * ``data_julgamento_de`` / ``data_julgamento_ate`` -> ``data_julgamento_inicio`` / ``data_julgamento_fim``

        Raises:
            TypeError: Quando um kwarg desconhecido e passado.
            ValueError: Quando um canonico e seu alias deprecado sao passados
                simultaneamente.
            ValidationError: Quando um filtro tem formato invalido.
            ColetaParcialError: Quando uma requisicao falha depois de a busca
                ter sido dividida por data. ``.resultado`` traz o DataFrame
                do que foi baixado, tambem em ``cjsg_download``, e a mensagem
                diz o intervalo que falta.

        Returns:
            DataFrame com as decisoes. ``id_documento`` traz a chave do
                documento no portal (o ``_id`` da resposta). O portal indexa
                algumas decisoes duas vezes, como dois documentos de conteudo
                igual: as linhas saem iguais em todas as outras colunas, e
                nenhuma e removida.

        See Also:
            :class:`InputCJSGTJRO` — schema pydantic e a fonte da verdade dos
            filtros aceitos.
        """
        return self.cjsg_parse(self.cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            tipo=tipo,
            numero_processo=numero_processo,
            relator=relator,
            orgao_julgador=orgao_julgador,
            orgao_julgador_colegiado=orgao_julgador_colegiado,
            classe=classe,
            instancia=instancia,
            termo_exato=termo_exato,
            auto_chunk=auto_chunk,
            **kwargs,
        ))

    def cjsg_download(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        tipo: list | None = None,
        numero_processo: str | None = None,
        relator: str | None = None,
        orgao_julgador: int | str | None = None,
        orgao_julgador_colegiado: int | str | None = None,
        classe: str | None = None,
        instancia: list | None = None,
        termo_exato: bool = False,
        auto_chunk: bool = True,
        **kwargs,
    ) -> list:
        """Baixa as respostas JSON brutas da CJSG do TJRO.

        Aceita os mesmos filtros de :meth:`cjsg`; veja lá a lista completa.

        Returns:
            Lista das respostas JSON brutas, uma por página.
        """
        numero_processo = resolve_deprecated_alias(
            kwargs, "nr_processo", "numero_processo", numero_processo
        )
        relator = resolve_deprecated_alias(
            kwargs, "magistrado", "relator", relator
        )
        classe = resolve_deprecated_alias(
            kwargs, "classe_judicial", "classe", classe
        )
        inp = apply_input_pipeline_search(
            InputCJSGTJRO,
            "TJROScraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            tipo=tipo,
            numero_processo=numero_processo,
            relator=relator,
            orgao_julgador=orgao_julgador,
            orgao_julgador_colegiado=orgao_julgador_colegiado,
            classe=classe,
            instancia=instancia,
            termo_exato=termo_exato,
            auto_chunk=auto_chunk,
        )
        return cjsg_download_manager(
            pesquisa=inp.pesquisa,
            paginas=inp.paginas_normalizadas,
            request_fn=self._request_with_retry,
            sleep_time=self.sleep_time,
            auto_chunk=inp.auto_chunk,
            tipo=inp.tipo,
            nr_processo=inp.numero_processo or "",
            relator=inp.relator or "",
            orgao_julgador=inp.orgao_julgador if inp.orgao_julgador is not None else "",
            orgao_julgador_colegiado=(
                inp.orgao_julgador_colegiado if inp.orgao_julgador_colegiado is not None else ""
            ),
            classe=inp.classe or "",
            data_julgamento_inicio=to_iso_date(inp.data_julgamento_inicio) or "",
            data_julgamento_fim=to_iso_date(inp.data_julgamento_fim) or "",
            instancia=inp.instancia,
            termo_exato=inp.termo_exato,
        )

    def cjsg_parse(self, resultados_brutos: list) -> pd.DataFrame:
        """Converte as respostas JSON baixadas da CJSG em DataFrame.

        Returns:
            Uma linha por decisão.
        """
        return cjsg_parse_manager(resultados_brutos)
