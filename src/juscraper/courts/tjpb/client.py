"""Scraper for the Tribunal de Justica da Paraiba (TJPB)."""
from datetime import date, datetime

import pandas as pd
import requests

from juscraper.core.base import BaseScraper
from juscraper.utils.params import apply_input_pipeline_search, coerce_brazilian_date, resolve_deprecated_alias

from .download import cjsg_download_manager
from .parse import cjsg_parse_manager
from .schemas import InputCJSGTJPB


def _to_date(value, fallback: date) -> date:
    """Coerce a user-supplied date to ``datetime.date`` for the local post-filter.

    Reuses :func:`coerce_brazilian_date` so all four canonical string formats
    plus ``date``/``datetime`` are accepted. Returns ``fallback`` when the
    input is ``None``, empty, or unparseable — used to keep ``DataFrame.between``
    open on one side when the user only supplied ``inicio`` or ``fim``.
    """
    coerced = coerce_brazilian_date(value, "%d/%m/%Y")
    if not coerced or not isinstance(coerced, str):
        return fallback
    try:
        return datetime.strptime(coerced, "%d/%m/%Y").date()
    except ValueError:
        return fallback


def _first_present(kwargs: dict, *keys: str):
    """Retorna o primeiro valor cuja key esta em ``kwargs`` (mesmo que vazio).

    Distinto de ``or`` chain: trata ``""`` como valor explicito do usuario
    (canonico empty vence alias preenchido), nao como "passa adiante".
    """
    for key in keys:
        if key in kwargs:
            return kwargs[key]
    return None


class TJPBScraper(BaseScraper):
    """Scraper for the Tribunal de Justica da Paraiba (TJPB).

    Uses the PJe jurisprudence search at pje-jurisprudencia.tjpb.jus.br.
    Built on the same platform developed by TJRN (Laravel + Elasticsearch).
    """

    BASE_URL = "https://pje-jurisprudencia.tjpb.jus.br"

    def __init__(self):
        super().__init__("TJPB")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
        })

    def cpopg(self, id_cnj: str | list[str]):
        """Stub: first instance case consultation not implemented for TJPB."""
        raise NotImplementedError("Consulta de processos de 1o grau nao implementada para TJPB.")

    def cposg(self, id_cnj: str | list[str]):
        """Stub: second instance case consultation not implemented for TJPB."""
        raise NotImplementedError("Consulta de processos de 2o grau nao implementada para TJPB.")

    def cjsg(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        numero_processo: str = "",
        id_classe: str = "",
        id_orgao_julgador: str = "",
        id_relator: str = "",
        id_origem: str = "8,2",
        decisoes: bool = False,
        **kwargs,
    ) -> pd.DataFrame:
        """Busca jurisprudencia no TJPB.

        Args:
            pesquisa (str): Termo de busca livre (busca na ementa).
            paginas (int | list | range | None): Paginas 1-based; ``None`` baixa
                todas. Default ``None``.
            numero_processo (str): Numero CNJ do processo. Aceita o alias
                deprecado ``nr_processo``.
            id_classe (str): ID da classe judicial. Aceita o alias deprecado
                ``id_classe_judicial`` (refs #129).
            id_orgao_julgador (str): ID do orgao julgador.
            id_relator (str): ID do relator.
            id_origem (str): Filtro de origem. ``"8,2"`` para todos (default),
                ``"8"`` para Turmas Recursais, ``"2"`` para Tribunal Pleno/Camaras.
            decisoes (bool): Se ``True``, inclui decisoes monocraticas.
            **kwargs: Filtros aceitos pelo schema :class:`InputCJSGTJPB`.
                Listados abaixo (todos opcionais; ``None`` = sem filtro):

                * ``data_julgamento_inicio`` / ``data_julgamento_fim`` (str |
                  date | datetime): ``DD/MM/YYYY``, ``DD-MM-YYYY``,
                  ``YYYY-MM-DD`` ou ``YYYY/MM/DD``. Convertido para
                  ``YYYY-MM-DD`` antes do envio ao backend. O backend filtra
                  por uma data interna de disponibilizacao (nao por
                  ``dt_ementa``); o cliente aplica um post-filter local sobre
                  ``data_julgamento`` para garantir que a janela pedida bate
                  com o que e devolvido (refs #195).

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
            pd.DataFrame: DataFrame com as decisoes.

        See also:
            :class:`InputCJSGTJPB` — schema pydantic e a fonte da verdade dos
            filtros aceitos.
        """
        # Lookup passivo das datas para o post-filter local. Sem `pop` para
        # nao consumir aliases antes do pipeline em `cjsg_download`, que e
        # quem valida e emite DeprecationWarning. `_first_present` (em vez
        # de `or` chain) preserva canonico empty contra alias preenchido.
        raw_inicio = _first_present(
            kwargs, "data_julgamento_inicio", "data_julgamento_de", "data_inicio"
        )
        raw_fim = _first_present(
            kwargs, "data_julgamento_fim", "data_julgamento_ate", "data_fim"
        )

        brutos = self.cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            numero_processo=numero_processo,
            id_classe=id_classe,
            id_orgao_julgador=id_orgao_julgador,
            id_relator=id_relator,
            id_origem=id_origem,
            decisoes=decisoes,
            **kwargs,
        )
        df = self.cjsg_parse(brutos)

        # The TJPB backend filter on dt_inicio/dt_fim acts on an internal
        # disponibilização date, not on dt_ementa. Rows returned can have
        # dt_ementa far outside the requested window. Post-filter so the
        # returned data_julgamento (= dt_ementa) matches user intent.
        # Open bounds (date.min/date.max) keep the filter active even when
        # the user supplies only one side of the range (refs #195).
        if not df.empty and "data_julgamento" in df.columns:
            start = _to_date(raw_inicio, date.min)
            end = _to_date(raw_fim, date.max)
            mask = df["data_julgamento"].between(start, end)
            df = df[mask].reset_index(drop=True)
        return df

    def cjsg_download(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        numero_processo: str = "",
        id_classe: str = "",
        id_orgao_julgador: str = "",
        id_relator: str = "",
        id_origem: str = "8,2",
        decisoes: bool = False,
        **kwargs,
    ) -> list:
        """Download raw CJSG JSON responses from TJPB.

        Aceita os mesmos filtros de :meth:`cjsg`; veja la a lista completa.

        Returns:
            list: Lista de respostas JSON cruas (uma por pagina).
        """
        numero_processo = resolve_deprecated_alias(
            kwargs, "nr_processo", "numero_processo", numero_processo, sentinel=""
        )
        id_classe = resolve_deprecated_alias(
            kwargs, "id_classe_judicial", "id_classe", id_classe, sentinel=""
        )
        inp = apply_input_pipeline_search(
            InputCJSGTJPB,
            "TJPBScraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            numero_processo=numero_processo,
            id_classe=id_classe,
            id_orgao_julgador=id_orgao_julgador,
            id_relator=id_relator,
            id_origem=id_origem,
            decisoes=decisoes,
        )
        return cjsg_download_manager(
            pesquisa=inp.pesquisa,
            paginas=inp.paginas,
            session=self.session,
            nr_processo=inp.numero_processo,
            id_classe=inp.id_classe,
            id_orgao_julgador=inp.id_orgao_julgador,
            id_relator=inp.id_relator,
            id_origem=inp.id_origem,
            decisoes=inp.decisoes,
            dt_inicio=inp.data_julgamento_inicio or "",
            dt_fim=inp.data_julgamento_fim or "",
        )

    def cjsg_parse(self, resultados_brutos: list) -> pd.DataFrame:
        """Parse downloaded CJSG JSON responses.

        Returns:
            pd.DataFrame: DataFrame com as decisoes.
        """
        return cjsg_parse_manager(resultados_brutos)
