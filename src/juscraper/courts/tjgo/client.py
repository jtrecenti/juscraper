"""Scraper for the Court of Justice of Goiás (TJGO)."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import date
from typing import Any, ClassVar, Literal

import pandas as pd
import requests

from juscraper.core.avisos import avisar
from juscraper.core.http import HTTPScraper, RequestPolicy
from juscraper.utils.deprecacao import resolve_deprecated_value
from juscraper.utils.params import apply_input_pipeline_search, resolve_deprecated_alias

from .download import cjsg_download as _cjsg_download
from .parse import cjsg_parse as _cjsg_parse
from .schemas import IdServentiaSubtipo, InputCJSGTJGO

logger = logging.getLogger("juscraper.tjgo")

# Opcoes do seletor "Instancia" e, ate a 0.7.0, os valores deprecados 1, 2 e 3.
IdInstancia = Literal[0, 15, 151, 1, 2, 3, "0", "15", "151", "1", "2", "3"]
# Codigos do seletor "Orgao", tambem em ``int``, que o schema converte para ``str``.
IdServentiaSubtipoAceito = IdServentiaSubtipo | Literal[
    0, 1, 2, 3, 6, 7, 8, 9, 10, 11, 12, 14, 20, 21, 22,
    26, 27, 34, 35, 36, 37, 39, 41, 42, 43, 44, 45, 46,
    47, 49, 58, 60, 61, 63, 64, 66, 67, 68, 69, 70, 71,
    72, 81, 82, 83,
]


class TJGOScraper(HTTPScraper):
    """Scraper for the Court of Justice of Goiás.

    A busca de jurisprudencia do TJGO (Projudi) tem um widget Cloudflare
    Turnstile. Desde 12/11/2026 (Projudi 3.194.1) o servidor valida o token, que
    o raspador nao envia: toda busca volta vazia, e ``cjsg``/``cjsg_download``
    emitem ``UserWarning`` explicando o bloqueio.
    """

    BASE_URL = "https://projudi.tjgo.jus.br/ConsultaJurisprudencia"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
    )

    perfis_http: ClassVar[Mapping[str, RequestPolicy]] = {
        "cjsg": RequestPolicy(timeout=90),
        "formulario": RequestPolicy(timeout=60),
    }

    def __init__(self, sleep_time: float = 1.0, *, politica: Mapping[str, Mapping[str, Any]] | None = None):
        super().__init__("TJGO", sleep_time=sleep_time, politica=politica)

    def _configure_session(self, session: requests.Session) -> None:
        session.headers["User-Agent"] = self.USER_AGENT

    def cjsg_download(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        id_instancia: IdInstancia = 0,
        id_area: Literal[0, 1, 2, "0", "1", "2"] = 0,
        id_serventia_subtipo: IdServentiaSubtipoAceito = 0,
        numero_processo: str | None = None,
        tamanho_pagina: int = 10,
        data_publicacao_inicio: str | date | None = None,
        data_publicacao_fim: str | date | None = None,
        **kwargs,
    ) -> list:
        """Executa a busca no TJGO e devolve o HTML bruto de cada página.

        Aceita os mesmos parâmetros e aliases deprecados de :meth:`cjsg`; veja lá
        a lista completa.

        Returns:
            HTML bruto de cada página baixada.
        """
        tamanho_pagina = resolve_deprecated_alias(
            kwargs, "qtde_itens_pagina", "tamanho_pagina", tamanho_pagina, sentinel=10
        )
        inp = apply_input_pipeline_search(
            InputCJSGTJGO,
            "TJGOScraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            data_publicacao_inicio=data_publicacao_inicio,
            data_publicacao_fim=data_publicacao_fim,
            id_instancia=_resolver_id_instancia(id_instancia),
            id_area=id_area,
            id_serventia_subtipo=id_serventia_subtipo,
            numero_processo=numero_processo,
            tamanho_pagina=tamanho_pagina,
        )

        return _cjsg_download(
            request_fn=self._request_with_retry,
            pesquisa=inp.pesquisa or "",
            paginas=inp.paginas_normalizadas,
            id_instancia=str(inp.id_instancia),
            id_area=str(inp.id_area),
            id_serventia_subtipo=str(inp.id_serventia_subtipo),
            data_publicacao_inicio=_br_date(inp.data_publicacao_inicio),
            data_publicacao_fim=_br_date(inp.data_publicacao_fim),
            numero_processo=inp.numero_processo or "",
            qtde_itens_pagina=inp.tamanho_pagina,
            sleep_time=self.sleep_time,
        )

    def cjsg_parse(self, raw_pages: list) -> pd.DataFrame:
        """Transform raw TJGO HTML pages into a DataFrame."""
        return _cjsg_parse(raw_pages)

    def cjsg(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        id_instancia: IdInstancia = 0,
        id_area: Literal[0, 1, 2, "0", "1", "2"] = 0,
        id_serventia_subtipo: IdServentiaSubtipoAceito = 0,
        numero_processo: str | None = None,
        tamanho_pagina: int = 10,
        **kwargs,
    ) -> pd.DataFrame:
        """Busca jurisprudencia no TJGO (Projudi).

        Args:
            pesquisa: Termo de busca livre.
            paginas: Paginas 1-based; ``None`` baixa
                todas. Default ``None``.
            id_instancia: ``0`` todas / ``15`` Tribunal / ``151``
                Turma de Uniformizacao e Turmas Recursais, as opcoes do
                seletor "Instancia" do site. ``1``, ``2`` e ``3`` sao
                deprecados (ver abaixo); o 1o grau nao esta no seletor, e
                ``1`` vai ao portal como esta.
            id_area: ``0`` todas / ``1`` civel / ``2`` criminal.
                Com ``id_instancia=151``, so ``0``, como no formulario do site.
            id_serventia_subtipo: Codigo do seletor "Orgao" do
                site (por exemplo, ``14`` Camaras Civeis, ``20`` Camaras
                Criminais, ``6`` Turma Recursal Civel e Criminal). ``0`` =
                todos. Codigo fora da lista, ou que o formulario nao oferece
                para a instancia e a area escolhidas, levanta ``ValidationError``.
            numero_processo: Filtrar por numero CNJ especifico.
            tamanho_pagina: Itens por pagina (default 10).
            **kwargs: Filtros aceitos pelo schema :class:`InputCJSGTJGO`.
                Listados abaixo (todos opcionais; ``None`` = sem filtro):

                * ``data_publicacao_inicio`` / ``data_publicacao_fim``
                  (str | date | None): ``DD/MM/AAAA``, ``DD-MM-AAAA``,
                  ``AAAA-MM-DD``, ``AAAA/MM/DD``, ``date`` ou ``datetime``.
                  Backend Projudi mapeia
                  para ``DataInicial`` / ``DataFinal`` no form body.

        Aliases deprecados (popados com ``DeprecationWarning`` antes do pydantic):
            * ``query`` / ``termo`` -> ``pesquisa``
            * ``data_publicacao_de`` / ``data_publicacao_ate`` -> ``data_publicacao_inicio`` / ``data_publicacao_fim``
            * ``qtde_itens_pagina`` -> ``tamanho_pagina``
            * ``id_instancia=2`` -> ``id_instancia=151``; ``id_instancia=3`` ->
              ``id_instancia=15``; ``id_instancia=1`` sem substituto

        Raises:
            TypeError: Quando um kwarg desconhecido e passado, **incluindo**
                ``data_julgamento_inicio`` / ``data_julgamento_fim`` — o backend
                Projudi nao expoe filtro de data de julgamento; use
                ``data_publicacao_*`` (canonico para o TJGO).
            ValidationError: Quando um filtro tem formato invalido ou a
                combinacao de ``id_instancia``, ``id_area`` e
                ``id_serventia_subtipo`` nao existe no formulario do Projudi.
            ValueError: Quando a pagina 1 traz resultados sem o total ("N
                resultados encontrados"), por exemplo depois de uma mudanca de
                markup do portal, tambem com ``paginas=1``.

        Returns:
            DataFrame com as decisoes (coluna ``texto`` carrega
                o conteudo do documento; ``ementa`` nao e preenchido).

        See also:
            :class:`InputCJSGTJGO` — schema pydantic e a fonte da verdade dos
            filtros aceitos.
        """
        return self.cjsg_parse(self.cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            id_instancia=id_instancia,
            id_area=id_area,
            id_serventia_subtipo=id_serventia_subtipo,
            numero_processo=numero_processo,
            tamanho_pagina=tamanho_pagina,
            **kwargs,
        ))

    def cpopg(self, id_cnj: str | list[str]):
        """Stub: first degree case search not implemented for TJGO."""
        raise NotImplementedError("TJGO does not implement cpopg.")

    def cposg(self, id_cnj: str | list[str]):
        """Stub: second degree case search not implemented for TJGO."""
        raise NotImplementedError("TJGO does not implement cposg.")


# Valores que a docstring indicava ate a 0.5.0 ("1 1o grau", "2 recursal",
# "3 tribunal"), fora das opcoes do seletor "Instancia" do Projudi, e a opcao
# equivalente. O formulario atual nao tem o 1o grau: ``1`` vai como esta.
_ID_INSTANCIA_DEPRECADO: dict[str, int | str] = {"2": 151, "3": 15}
_SO_OPCOES_DO_FORM = (
    "o formulario do Projudi so oferece 0 (todas), 15 (Tribunal) e 151 (Turmas Recursais)."
)


def _resolver_id_instancia(id_instancia: int | str) -> int | str:
    """Troca ``2``/``3`` pela opcao do formulario e avisa de ``1``, com ``DeprecationWarning``."""
    if str(id_instancia) == "1":
        avisar(
            f"id_instancia={id_instancia!r} esta deprecado: {_SO_OPCOES_DO_FORM} "
            "O valor (1o grau) vai ao portal como esta, sem garantia de filtro.",
            DeprecationWarning,
        )
        return id_instancia
    return resolve_deprecated_value(
        id_instancia,
        _ID_INSTANCIA_DEPRECADO,
        "id_instancia={antigo!r} esta deprecado: " + _SO_OPCOES_DO_FORM
        + " O juscraper passa a enviar {novo}; use id_instancia={novo}.",
    )


def _br_date(value) -> str:
    """Normalize a date-like value to TJGO's ``dd/mm/yyyy`` format."""
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        formatted: str = value.strftime("%d/%m/%Y")
        return formatted
    text = str(value).strip()
    if not text:
        return ""
    # yyyy-mm-dd → dd/mm/yyyy
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return f"{text[8:10]}/{text[5:7]}/{text[0:4]}"
    return text
