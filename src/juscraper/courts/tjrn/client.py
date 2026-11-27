"""Scraper for the Tribunal de Justica do Rio Grande do Norte (TJRN)."""

from collections.abc import Mapping
from typing import Any, ClassVar

import pandas as pd

from juscraper.core.http import HTTPScraper, RequestPolicy
from juscraper.schemas import BuscarEm
from juscraper.utils.params import apply_input_pipeline_search, resolve_deprecated_alias, to_br_date

from .download import cjsg_download_manager
from .parse import cjsg_parse_manager
from .schemas import Decisoes, Grau, InputCJSGTJRN, Jurisdicoes, Sistema


def _to_tjrn_date(date_str):
    """Convert BR or ISO dates to TJRN's DD-MM-YYYY format.

    The UI at jurisprudencia.tjrn.jus.br sends ``dt_inicio``/``dt_fim`` as
    ``DD-MM-YYYY`` (dashes, not slashes); slashes are silently ignored and
    the backend returns unfiltered results.
    """
    if not date_str:
        return ""
    br = to_br_date(date_str)
    return br.replace("/", "-") if br else ""


class TJRNScraper(HTTPScraper):
    """Scraper for the Tribunal de Justica do Rio Grande do Norte (TJRN).

    Uses the TJRN Elasticsearch-based JSON API at jurisprudencia.tjrn.jus.br.
    """

    BASE_URL = "https://jurisprudencia.tjrn.jus.br"

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
            "TJRN",
            verbose=verbose,
            download_path=download_path,
            sleep_time=sleep_time,
            **kwargs,
        )

    def cpopg(self, id_cnj: str | list[str]):
        """Stub: first instance case consultation not implemented for TJRN."""
        raise NotImplementedError("Consulta de processos de 1o grau nao implementada para TJRN.")

    def cposg(self, id_cnj: str | list[str]):
        """Stub: second instance case consultation not implemented for TJRN."""
        raise NotImplementedError("Consulta de processos de 2o grau nao implementada para TJRN.")

    def cjsg(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        numero_processo: str | None = None,
        id_classe: str | None = None,
        id_orgao_julgador: str | None = None,
        id_relator: str | None = None,
        id_colegiado: str | None = None,
        sistema: Sistema | None = None,
        decisoes: Decisoes | None = None,
        jurisdicoes: Jurisdicoes | None = None,
        grau: Grau | None = None,
        buscar_em: BuscarEm = "ementa",
        **kwargs,
    ) -> pd.DataFrame:
        """Busca jurisprudencia no TJRN.

        Args:
            pesquisa (str): Termo de busca, procurado no campo indicado por
                ``buscar_em`` (por padrao, a ementa).
            paginas (int | list | range | None): Paginas 1-based; ``None`` baixa
                todas. Default ``None``.
            numero_processo (str): Numero CNJ do processo. Aceita o alias
                deprecado ``nr_processo``.
            id_classe (str): ID da classe judicial. Aceita o alias deprecado
                ``id_classe_judicial`` (refs #129).
            id_orgao_julgador (str): ID do orgao julgador.
            id_relator (str): ID do relator.
            id_colegiado (str): ID do colegiado.
            sistema (str): Sistema processual, com os valores do portal:
                ``"PJE"``, ``"SAJ"`` ou vazio para todos. Outro valor (inclusive
                ``"pje"``) levanta ``ValidationError``.
            decisoes (str): Tipo de decisao, com os valores do portal:
                ``"Decisão"`` (monocraticas), ``"Acórdão"`` (colegiadas),
                ``"Sentença"`` ou vazio para todas. Outro valor levanta
                ``ValidationError``. ``"Sentença"`` so existe no 1o grau e
                ``"Acórdão"`` so no 2o; ``"Decisão"`` existe nos dois. Como o
                portal nao devolve resultados para as combinacoes cruzadas,
                ``"Sentença"`` com ``grau="2"``, ``"TJ"`` ou ``"TR"`` e
                ``"Acórdão"`` com ``grau="1"`` levantam ``ValidationError``.
                Por padrao, ``pesquisa`` busca na ementa, e no portal so os
                acordaos tem ementa: com termo na ementa, ``"Sentença"`` e
                ``"Decisão"`` com ``jurisdicoes`` levantam ``ValidationError``.
                ``"Decisão"`` sem jurisdicao segue aceita, mas so algumas
                monocraticas do SAJ, de 2008, tem ementa. Para buscar termo
                nesses tipos, ver ``buscar_em``.
            jurisdicoes (str): Jurisdicao, com os valores do portal: ``"TJ"``
                (orgaos do Tribunal de Justica), ``"TR"`` (Turmas Recursais e
                Turma de Uniformizacao) ou vazio para todas. Outro valor
                levanta ``ValidationError``. ``"TJ"`` e ``"TR"`` so trazem
                decisoes de 2o grau: com ``grau="1"`` ou
                ``decisoes="Sentença"``, em que o portal nao devolve
                resultados, levantam ``ValidationError``.
            grau (str): ``"1"`` (primeiro), ``"2"`` (segundo) ou vazio para
                todos, sempre como texto. Outro valor (inclusive o inteiro
                ``2``) levanta ``ValidationError``. ``grau="1"`` com
                ``decisoes="Acórdão"`` e ``grau="2"`` com
                ``decisoes="Sentença"`` tambem levantam, porque o portal nao
                devolve resultados para elas. Decisoes de 1o grau nao tem
                ementa: ``grau="1"`` com termo na ementa levanta
                ``ValidationError``; buscar o termo com
                ``buscar_em="inteiro_teor"``.
            buscar_em (str): Onde procurar ``pesquisa``: ``"ementa"``
                (default) ou ``"inteiro_teor"`` (texto integral da decisao,
                campo "Inteiro teor" do portal). No portal so os acordaos tem
                ementa; o inteiro teor existe em acordaos, monocraticas e
                sentencas. Outro valor levanta ``ValidationError``. Com
                ``"ementa"`` e termo, ``decisoes="Sentença"``, ``grau="1"`` e
                ``decisoes="Decisão"`` com ``jurisdicoes`` levantam
                ``ValidationError``, porque o portal nao devolve resultados.
                O portal ignora as preposicoes e as conjuncoes ``"e"`` e
                ``"ou"`` em minusculas: termo so com elas (``"a"``, ``"de"``)
                conta como busca vazia e nao levanta.
            **kwargs: Filtros aceitos pelo schema :class:`InputCJSGTJRN`.
                Listados abaixo (todos opcionais; ``None`` = sem filtro):

                * ``data_julgamento_inicio`` / ``data_julgamento_fim``
                  (str | date | None): ``DD/MM/AAAA``, ``DD-MM-AAAA``,
                  ``AAAA-MM-DD``, ``AAAA/MM/DD``, ``date`` ou ``datetime``.
                  Convertido para ``DD-MM-YYYY`` antes do
                  envio ao backend.

        Aliases deprecados (popados com ``DeprecationWarning`` antes do pydantic):
            * ``query`` / ``termo`` -> ``pesquisa``
            * ``nr_processo`` -> ``numero_processo``
            * ``id_classe_judicial`` -> ``id_classe``
            * ``data_inicio`` / ``data_fim`` -> ``data_julgamento_inicio`` / ``_fim``
            * ``data_julgamento_de`` / ``_ate`` -> ``data_julgamento_inicio`` / ``_fim``

        Raises:
            TypeError: Quando um kwarg desconhecido e passado.
            ValueError: Quando um canonico e seu alias deprecado sao passados
                simultaneamente.
            ValidationError: Quando um filtro tem formato invalido.

        Returns:
            DataFrame com as decisoes.

        See also:
            :class:`InputCJSGTJRN` — schema pydantic e a fonte da verdade dos
            filtros aceitos.
        """
        return self.cjsg_parse(self.cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            numero_processo=numero_processo,
            id_classe=id_classe,
            id_orgao_julgador=id_orgao_julgador,
            id_relator=id_relator,
            id_colegiado=id_colegiado,
            sistema=sistema,
            decisoes=decisoes,
            jurisdicoes=jurisdicoes,
            grau=grau,
            buscar_em=buscar_em,
            **kwargs,
        ))

    def cjsg_download(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        numero_processo: str | None = None,
        id_classe: str | None = None,
        id_orgao_julgador: str | None = None,
        id_relator: str | None = None,
        id_colegiado: str | None = None,
        sistema: Sistema | None = None,
        decisoes: Decisoes | None = None,
        jurisdicoes: Jurisdicoes | None = None,
        grau: Grau | None = None,
        buscar_em: BuscarEm = "ementa",
        **kwargs,
    ) -> list:
        """Download raw CJSG JSON responses from TJRN.

        Aceita os mesmos filtros de :meth:`cjsg`; veja la a lista completa.

        Returns
        -------
        list
            List of raw JSON responses (one per page).
        """
        numero_processo = resolve_deprecated_alias(
            kwargs, "nr_processo", "numero_processo", numero_processo
        )
        id_classe = resolve_deprecated_alias(
            kwargs, "id_classe_judicial", "id_classe", id_classe
        )
        inp = apply_input_pipeline_search(
            InputCJSGTJRN,
            "TJRNScraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            numero_processo=numero_processo,
            id_classe=id_classe,
            id_orgao_julgador=id_orgao_julgador,
            id_relator=id_relator,
            id_colegiado=id_colegiado,
            sistema=sistema,
            decisoes=decisoes,
            jurisdicoes=jurisdicoes,
            grau=grau,
            buscar_em=buscar_em,
        )
        return cjsg_download_manager(
            pesquisa=inp.pesquisa,
            buscar_em=inp.buscar_em,
            paginas=inp.paginas_normalizadas,
            request_fn=self._request_with_retry,
            sleep_time=self.sleep_time,
            nr_processo=inp.numero_processo or "",
            id_classe=inp.id_classe or "",
            id_orgao_julgador=inp.id_orgao_julgador or "",
            id_relator=inp.id_relator or "",
            id_colegiado=inp.id_colegiado or "",
            dt_inicio=_to_tjrn_date(inp.data_julgamento_inicio),
            dt_fim=_to_tjrn_date(inp.data_julgamento_fim),
            sistema=inp.sistema or "",
            decisoes=inp.decisoes or "",
            jurisdicoes=inp.jurisdicoes or "",
            grau=inp.grau or "",
        )

    def cjsg_parse(self, resultados_brutos: list) -> pd.DataFrame:
        """Parse downloaded CJSG JSON responses.

        Parameters
        ----------
        resultados_brutos : list
            List of raw JSON responses from the TJRN API.

        Returns
        -------
        pd.DataFrame
        """
        return cjsg_parse_manager(resultados_brutos)
