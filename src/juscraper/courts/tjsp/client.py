"""Main scraper for Tribunal de Justiça de São Paulo (TJSP)."""
from __future__ import annotations

import logging
import os
import shutil
import tempfile
import warnings
from typing import Any, Literal

from pydantic import BaseModel

from ...utils.params import (
    SEARCH_ALIASES,
    apply_input_pipeline_search,
    iter_date_windows,
    normalize_pesquisa,
    pop_deprecated_alias,
    validate_intervalo_datas,
)
from .._esaj.base import EsajSearchScraper
from .cjpg_download import cjpg_download as cjpg_download_mod
from .cjpg_download import fetch_cjpg_first_page
from .cjpg_parse import cjpg_n_pags, cjpg_n_results, cjpg_parse_manager
from .cpopg_download import cpopg_download_api, cpopg_download_html
from .cpopg_parse import cpopg_parse_manager, get_cpopg_download_links
from .cposg_download import cposg_download_api, cposg_download_html
from .cposg_parse import cposg_parse_manager
from .exceptions import QueryTooLongError, validate_pesquisa_length
from .forms import build_tjsp_cjsg_body
from .schemas import InputCJPGTJSP, InputCJSGTJSP

logger = logging.getLogger("juscraper.tjsp")


# Plurais legados de cjpg (refs #232). Singular canonico ja declarado em
# ``InputCJPGTJSP``; plurais aparecem so como alias deprecados.
_CJPG_PLURAL_ALIASES: tuple[tuple[str, str], ...] = (
    ("classes", "classe"),
    ("assuntos", "assunto"),
    ("varas", "vara"),
)


def _pop_cjpg_plural_aliases(kwargs: dict) -> None:
    """Popa aliases plurais cjpg (``classes``/``assuntos``/``varas`` -> singular).

    Chamado em duas posicoes do client TJSP:

    1. ``cjpg()`` antes de :func:`run_auto_chunk` — a validacao upfront do
       schema dentro do chunking nao tolera kwargs nao-canonicos
       (``extra_forbidden`` em :class:`InputCJPGTJSP`), entao precisa
       acontecer aqui, nao apenas em ``cjpg_download``.
    2. ``cjpg_download()`` para chamadas diretas que nao passaram por
       ``cjpg()``. Idempotente: se ``cjpg()`` ja popou, e no-op.

    Conflito plural+singular usa ``kwargs.get(_new) is not None`` (nao
    ``_new in kwargs``) para nao tratar ``classe=None`` explicito como
    conflito — alinha com a checagem de TJBA/DataJud. Refs #232.
    """
    for _old, _new in _CJPG_PLURAL_ALIASES:
        if _old not in kwargs:
            continue
        if kwargs.get(_new) is not None:
            kwargs.pop(_old)
            raise ValueError(
                f"Nao e possivel passar '{_new}' e '{_old}' simultaneamente."
            )
        kwargs[_new] = pop_deprecated_alias(kwargs, _old, _new)


class TJSPScraper(EsajSearchScraper):
    """Main scraper for TJSP — eSAJ web + api.tjsp.jus.br."""

    BASE_URL = "https://esaj.tjsp.jus.br/"
    TRIBUNAL_NAME = "TJSP"
    INPUT_CJSG = InputCJSGTJSP
    INPUT_CJPG = InputCJPGTJSP
    CJSG_CHROME_UA = True
    CJSG_EXTRACT_CONVERSATION_ID = True

    def __init__(
        self,
        verbose: int = 0,
        download_path: str | None = None,
        sleep_time: float = 0.5,
        **kwargs: Any,
    ):
        super().__init__(
            verbose=verbose,
            download_path=download_path,
            sleep_time=sleep_time,
            **kwargs,
        )
        self.u_base = self.BASE_URL
        self.api_base = "https://api.tjsp.jus.br/"
        self.method: Literal["html", "api"] | None = None

    def set_download_path(self, path: str | None = None):
        """Set download base dir; creates a tempdir when ``path`` is ``None``."""
        if path is None:
            path = tempfile.mkdtemp()
        self.download_path = path

    def set_method(self, method: Literal["html", "api"]):
        """Validate and store the access method (``'html'`` or ``'api'``) for cpopg/cposg."""
        if method not in ("html", "api"):
            raise ValueError(
                f"Método {method} nao suportado. Os métodos suportados são 'html' e 'api'."
            )
        self.method = method

    # --- cjsg -----------------------------------------------------------

    def cjsg(
        self,
        pesquisa: str = "",
        paginas: int | list | range | None = None,
        **kwargs: Any,
    ):
        """Pesquisa jurisprudencia de segundo grau do TJSP (CJSG).

        Override raso de :meth:`EsajSearchScraper.cjsg` so para ancorar a
        docstring TJSP-especifica: o schema validador e
        :class:`InputCJSGTJSP`, que difere do schema default da familia
        (sem ``numero_recurso``/``data_publicacao_*``/``origem``; com
        ``baixar_sg``). A logica de execucao continua na base.

        Diferente da familia eSAJ pura, ``pesquisa`` aceita string vazia
        — o usuario pode buscar so por filtros (ex.: ``classe``,
        ``assunto``, ``data_julgamento_*``) sem termo textual. Mesmo
        comportamento de :meth:`cjpg` (issue #229).

        Args:
            pesquisa (str): Termo livre buscado no acordao/ementa. Default
                ``""`` (sem termo, busca aberta por filtros). Limite de
                120 caracteres (raises ``QueryTooLongError``).
            paginas (int | list | range | None): Paginas 1-based;
                ``None`` baixa todas. Default ``None``.
            **kwargs: Filtros aceitos por :class:`InputCJSGTJSP` (todos
                opcionais; ``None`` = sem filtro):

                * ``ementa`` (str): Termo buscado especificamente na
                  ementa.
                * ``classe`` (str): ID interno da classe processual.
                * ``assunto`` (str): ID interno do assunto.
                * ``comarca`` (str): ID interno da comarca.
                * ``orgao_julgador`` (str): ID interno do orgao julgador.
                * ``baixar_sg`` (bool): ``True`` (default) busca em
                  segundo grau; ``False`` busca em colegio recursal.
                * ``tipo_decisao`` (Literal["acordao", "monocratica"]):
                  Default ``"acordao"``.
                * ``data_julgamento_inicio`` / ``data_julgamento_fim``
                  (str, ``DD/MM/AAAA``): Intervalo de julgamento.
                * ``auto_chunk`` (bool): Default ``True``. Quando o
                  intervalo ``data_julgamento_*`` excede 366 dias,
                  divide internamente em janelas, baixa cada uma e
                  concatena com dedup por ``cd_acordao``.
                * ``count_only`` (bool): Default ``False``. Se ``True``,
                  faz so a chamada inicial e retorna ``int`` com o total
                  de resultados em vez de ``pd.DataFrame``. Util pra
                  estimar wall-clock antes de coleta longa (issue #92).
                  Soma bruta cross-janela em ``auto_chunk=True``.

        Aliases deprecados (popados com ``DeprecationWarning`` antes do
        pydantic):

            * ``query`` / ``termo`` -> ``pesquisa``
            * ``data_inicio`` / ``data_fim`` -> ``data_julgamento_inicio`` / ``_fim``
            * ``data_julgamento_de`` / ``_ate`` -> ``data_julgamento_inicio`` / ``_fim``

        Raises:
            TypeError: Quando um kwarg desconhecido e passado.
            ValidationError: Quando um filtro tem formato invalido.
            QueryTooLongError: Quando ``pesquisa`` excede 120 chars.

        Returns:
            pd.DataFrame | int: Resultados parseados (colunas conforme
            :class:`OutputCJSGTJSP` — ``processo``, ``ementa``,
            ``data_julgamento``, ``cd_acordao``, ``relator``,
            ``orgao_julgador``); ``int`` com o total de resultados quando
            ``count_only=True``.

        Exemplo:
            >>> import juscraper as jus
            >>> tjsp = jus.scraper("tjsp")
            >>> df = tjsp.cjsg("dano moral", paginas=range(1, 3),
            ...                tipo_decisao="acordao",
            ...                data_julgamento_inicio="01/01/2024")
            >>> # Estimativa pre-scraping (issue #92):
            >>> n = tjsp.cjsg("dano moral", count_only=True)

        See also:
            :class:`~juscraper.courts.tjsp.schemas.InputCJSGTJSP` —
            schema pydantic e a fonte da verdade dos filtros aceitos.
            :meth:`EsajSearchScraper.cjsg` — descricao detalhada do
            auto-chunking (issue #130) para janelas
            ``data_julgamento_*`` > 366 dias.
        """
        return super().cjsg(pesquisa=pesquisa, paginas=paginas, **kwargs)

    def _cjsg_count_only(
        self,
        pesquisa: str,
        paginas: int | list | range | None,
        **kwargs: Any,
    ) -> int:
        """Override TJSP — valida limite de 120 chars antes do probe (#92).

        O caminho normal de cjsg em TJSP passa por :meth:`cjsg_download`
        (override), que roda :func:`validate_pesquisa_length` antes de
        delegar para a base. Com ``count_only=True``, o ramo na base desvia
        direto para :meth:`_cjsg_count_only` e pula esse check — entao
        replicamos a validacao aqui antes de delegar para
        :meth:`EsajSearchScraper._cjsg_count_only`. Espelha o padrao de
        :meth:`cjsg_download` (pop manual dos search aliases para evitar
        reprocessamento no helper de pipeline).
        """
        pesquisa = normalize_pesquisa(pesquisa, **kwargs)
        for alias in SEARCH_ALIASES:
            kwargs.pop(alias, None)
        validate_pesquisa_length(pesquisa, endpoint="CJSG")
        return super()._cjsg_count_only(
            pesquisa=pesquisa, paginas=paginas, **kwargs,
        )

    def cjsg_download(
        self,
        pesquisa: str = "",
        paginas: int | list | range | None = None,
        diretorio: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Baixa as paginas HTML brutas do CJSG TJSP (sem parsear).

        Roda :func:`validate_pesquisa_length` antes do pydantic para que
        ``QueryTooLongError`` propague limpo (em vez de virar
        ``ValidationError``). Aceita os mesmos filtros de :meth:`cjsg`;
        veja la a lista completa.

        Args:
            pesquisa (str): Termo livre. Default ``""`` (sem termo).
                Limite de 120 chars.
            paginas (int | list | range | None): Paginas 1-based;
                ``None`` baixa todas. Default ``None``.
            diretorio (str | None): Sobrescreve :attr:`download_path`
                para esta unica chamada. Default ``None``.
            **kwargs: Mesmos filtros aceitos por :meth:`cjsg` (validados
                por :class:`InputCJSGTJSP`).

        Raises:
            TypeError: Quando um kwarg desconhecido e passado.
            ValidationError: Quando um filtro tem formato invalido.
            QueryTooLongError: Quando ``pesquisa`` excede 120 chars.

        Returns:
            str: Caminho do diretorio onde os HTMLs foram salvos.
        """
        pesquisa = normalize_pesquisa(pesquisa, **kwargs)
        # Only the search aliases get popped here; the base class will run
        # normalize_datas on the date aliases before popping them, preserving
        # the DeprecationWarning they emit.
        for alias in SEARCH_ALIASES:
            kwargs.pop(alias, None)
        validate_pesquisa_length(pesquisa, endpoint="CJSG")
        return super().cjsg_download(
            pesquisa=pesquisa, paginas=paginas, diretorio=diretorio, **kwargs,
        )

    def _build_cjsg_body(self, inp: BaseModel) -> dict:
        data = inp.model_dump()
        body: dict = build_tjsp_cjsg_body(
            pesquisa=data["pesquisa"],
            ementa=data.get("ementa"),
            classe=data.get("classe"),
            assunto=data.get("assunto"),
            comarca=data.get("comarca"),
            orgao_julgador=data.get("orgao_julgador"),
            data_julgamento_inicio=data.get("data_julgamento_inicio"),
            data_julgamento_fim=data.get("data_julgamento_fim"),
            baixar_sg=data.get("baixar_sg", True),
            tipo_decisao=data.get("tipo_decisao", "acordao"),
        )
        return body

    # --- cjpg -----------------------------------------------------------
    # A orquestracao (probe count_only -> auto-chunk -> download -> parse)
    # e compartilhada com ``cjsg`` via ``EsajSearchScraper._run_search``
    # (Template Method, #205). Os internals de download/parse
    # (``cjpg_download.py`` + ``cjpg_parse.py``) sao unicos do TJSP e
    # entram em ``_run_search`` como hooks resolvidos por nome.

    def cjpg(
        self,
        pesquisa: str = "",
        paginas: int | list | range | None = None,
        **kwargs: Any,
    ):
        """Pesquisa jurisprudencia de primeiro grau do TJSP (CJPG).

        Delega para :meth:`cjpg_download` + :meth:`cjpg_parse` e remove
        o diretorio temporario antes de retornar. Diferente do CJSG, aqui
        ``pesquisa`` aceita string vazia — o usuario pode buscar so por
        filtros (ex.: todas as decisoes de uma vara especifica num
        intervalo de datas).

        Args:
            pesquisa (str): Termo livre buscado na decisao. Default
                ``""`` (sem termo). Limite de 120 caracteres (raises
                ``QueryTooLongError``).
            paginas (int | list | range | None): Paginas 1-based;
                ``None`` baixa todas. Default ``None``.
            **kwargs: Filtros aceitos por :class:`InputCJPGTJSP` (todos
                opcionais; ``None`` = sem filtro):

                * ``classe`` (int | str | list[int | str]): ID(s) internos
                  de classe processual. Backend:
                  ``classeTreeSelection.values`` (CSV).
                * ``assunto`` (int | str | list[int | str]): ID(s) internos
                  de assunto. Backend: ``assuntoTreeSelection.values``
                  (CSV).
                * ``vara`` (int | str | list[int | str]): ID(s) internos de
                  vara, no formato em arvore do TJSP (ex.: ``"1-1-1"``).
                  Backend: ``varasTreeSelection.values`` (CSV).
                * ``id_processo`` (str): Numero CNJ formatado para
                  filtrar uma instancia especifica. Normalizado via
                  :func:`clean_cnj` antes do envio.
                * ``data_julgamento_inicio`` / ``data_julgamento_fim``
                  (str, ``DD/MM/AAAA``): Intervalo de julgamento.
                * ``auto_chunk`` (bool): Default ``True``. Quando o
                  intervalo ``data_julgamento_*`` excede 366 dias,
                  divide internamente em janelas, baixa cada uma e
                  concatena com dedup por ``id_processo``. Veja a secao
                  "Auto-chunking" abaixo.
                * ``count_only`` (bool): Default ``False``. Se ``True``,
                  faz so o GET inicial, extrai o total de resultados via
                  ``cjpg_n_results`` e retorna ``int`` em vez de
                  ``pd.DataFrame``. Util pra estimar wall-clock antes de
                  coleta longa (issue #92). Com ``auto_chunk=True`` +
                  janela > 366 dias, itera janelas disjuntas e soma —
                  soma bruta (sem dedup por ``id_processo``). ``paginas``
                  e ignorado (emite ``UserWarning``).

        Aliases deprecados (popados com ``DeprecationWarning`` antes do
        pydantic):

            * ``query`` / ``termo`` -> ``pesquisa``
            * ``classes`` -> ``classe``
            * ``assuntos`` -> ``assunto``
            * ``varas`` -> ``vara``
            * ``data_inicio`` / ``data_fim`` -> ``data_julgamento_inicio`` / ``_fim``
            * ``data_julgamento_de`` / ``_ate`` -> ``data_julgamento_inicio`` / ``_fim``

        Raises:
            TypeError: Quando um kwarg desconhecido e passado (via
                :func:`raise_on_extra_kwargs`).
            ValidationError: Quando um filtro tem formato invalido.
            QueryTooLongError: Quando ``pesquisa`` excede 120 chars.
            ValueError: Quando ``classe`` e ``classes`` (ou par equivalente)
                sao passados simultaneamente.

        Returns:
            pd.DataFrame | int: Resultados parseados (colunas conforme
            :class:`OutputCJPGTJSP` — ``id_processo``, ``cd_processo`` e
            campos extras emitidos pelo parser via ``extra='allow'`` —
            ``classe``, ``assunto``, ``magistrado``, ``comarca``,
            ``foro``, ``vara``, ``data_disponibilizacao``, ``decisao``);
            ``int`` com o total de resultados quando ``count_only=True``.

        Exemplo:
            >>> import juscraper as jus
            >>> tjsp = jus.scraper("tjsp")
            >>> # Busca textual + filtro de vara:
            >>> df = tjsp.cjpg("dano moral", paginas=range(1, 3),
            ...                vara="1-1-1")
            >>> # So filtros (sem termo) — IDs como int ou list:
            >>> df = tjsp.cjpg(paginas=1, classe=12728, assunto=[3607, 5885],
            ...                data_julgamento_inicio="01/01/2024",
            ...                data_julgamento_fim="31/03/2024")
            >>> # Estimativa pre-scraping (issue #92):
            >>> n = tjsp.cjpg("dano moral", count_only=True)

        See also:
            :class:`~juscraper.courts.tjsp.schemas.InputCJPGTJSP` —
            schema pydantic e a fonte da verdade dos filtros aceitos.

        Auto-chunking (issue #130):
            Se ``auto_chunk=True`` (default herdado de
            :class:`~juscraper.schemas.AutoChunkMixin`) e o intervalo
            ``data_julgamento_*`` exceder 366 dias, a busca e dividida em
            janelas internas, baixadas e concatenadas com dedup por
            ``id_processo``. Falhas por janela viram :class:`UserWarning`
            (parcial + warning). ``auto_chunk=True`` + ``paginas != None``
            em janela > 366 dias e :class:`ValueError`.
        """
        # Orquestracao (probe count_only -> auto-chunk -> download -> parse
        # -> cleanup) compartilhada com ``cjsg`` via ``_run_search`` (#205).
        # ``pre_normalize`` popa os plurais antes do auto-chunk: a validacao
        # upfront do schema dentro do chunking rejeita ``classes``/``assuntos``/
        # ``varas`` via ``extra_forbidden``. Refs #232.
        return self._run_search(
            endpoint="cjpg",
            input_cls=self.INPUT_CJPG,
            dedup_key="id_processo",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            pre_normalize=_pop_cjpg_plural_aliases,
        )

    def _cjpg_count_only(
        self,
        pesquisa: str,
        paginas: int | list | range | None,
        **kwargs: Any,
    ) -> int:
        """Probe leve para ``cjpg(count_only=True)`` — refs #92.

        Faz o GET inicial por janela, extrai ``n_results`` via
        :func:`cjpg_n_results` e retorna a soma. ``paginas`` e ignorado.

        Multi-janela: se o intervalo ``data_julgamento_*`` excede 366 dias
        e ``auto_chunk=True``, itera janelas disjuntas via
        :func:`iter_date_windows`. ``auto_chunk=False`` + janela > 366d
        levanta :class:`ValueError` (consistencia com caminho normal).

        **Fail-fast no auto-chunk**: diferente do caminho normal
        (:func:`run_auto_chunk`), que tolera falha por janela como
        :class:`UserWarning` e devolve resultado parcial deduplicado, este
        probe usa ``sum()`` — qualquer :class:`ValueError` em uma janela
        aborta toda a iteracao. Decisao deliberada: estimativa parcial sem
        aviso seria pior que erro explicito.
        """
        if paginas is not None:
            warnings.warn(
                "paginas e ignorado quando count_only=True (probe sempre olha so a pagina 1).",
                UserWarning,
                stacklevel=3,
            )

        inp = apply_input_pipeline_search(
            InputCJPGTJSP,
            f"{type(self).__name__}.cjpg(count_only=True)",
            pesquisa=pesquisa,
            paginas=None,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            nullable_pesquisa=True,
            max_dias=None,
            origem_mensagem="O eSAJ",
        )
        validate_pesquisa_length(inp.pesquisa, endpoint="CJPG")

        auto_chunk = inp.auto_chunk
        di = inp.data_julgamento_inicio
        df_ = inp.data_julgamento_fim

        if not auto_chunk:
            validate_intervalo_datas(
                di, df_, max_dias=366, rotulo="data_julgamento", origem="O eSAJ",
            )

        def _probe(win_i: str | None, win_f: str | None) -> int:
            r0 = fetch_cjpg_first_page(
                pesquisa=inp.pesquisa,
                session=self.session,
                u_base=self.u_base,
                classe=inp.classe,
                assunto=inp.assunto,
                vara=inp.vara,
                id_processo=inp.id_processo,
                data_inicio=win_i,
                data_fim=win_f,
            )
            return cjpg_n_results(r0.content)

        if not auto_chunk or di is None or df_ is None:
            return _probe(di, df_)

        return sum(_probe(win_i, win_f) for win_i, win_f in iter_date_windows(di, df_, max_dias=366))

    def cjpg_download(
        self,
        pesquisa: str = "",
        paginas: int | list | range | None = None,
        **kwargs: Any,
    ) -> str:
        """Baixa as paginas HTML brutas do CJPG TJSP (sem parsear).

        Delega a normalizacao de ``pesquisa`` ao pipeline (via
        ``consume_pesquisa_aliases=True`` + ``nullable_pesquisa=True`` —
        CJPG admite busca aberta com ``pesquisa=""``). Roda
        :func:`validate_pesquisa_length` sobre o valor ja resolvido
        (apos consumir ``query``/``termo``) para que ``QueryTooLongError``
        propague mesmo quando o alias trouxe a string longa. Aceita os
        mesmos filtros de :meth:`cjpg`; veja la a lista completa.

        Args:
            pesquisa (str): Termo livre. Default ``""``. Limite de 120
                chars.
            paginas (int | list | range | None): Paginas 1-based;
                ``None`` baixa todas. Default ``None``.
            **kwargs: Mesmos filtros aceitos por :meth:`cjpg` (validados
                por :class:`InputCJPGTJSP`).

        Raises:
            TypeError: Quando um kwarg desconhecido e passado.
            ValidationError: Quando um filtro tem formato invalido.
            QueryTooLongError: Quando ``pesquisa`` (ou alias resolvido)
                excede 120 chars.
            ValueError: Quando o usuario passa um alias deprecado e o nome
                canonico simultaneamente (ex.: ``classe`` e ``classes``;
                refs #232).

        Returns:
            str: Caminho do diretorio onde os HTMLs foram salvos.
        """
        # Aliases plurais ja foram popados em ``cjpg()``; chamada direta a
        # ``cjpg_download()`` precisa fazer a pop tambem. ``_pop_cjpg_plural_aliases``
        # e idempotente (no-op quando ``cjpg()`` ja rodou). Refs #232.
        _pop_cjpg_plural_aliases(kwargs)

        inp = apply_input_pipeline_search(
            InputCJPGTJSP,
            f"{type(self).__name__}.cjpg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            nullable_pesquisa=True,
            max_dias=366,
            origem_mensagem="O eSAJ",
        )
        # Roda apos o pipeline para validar o valor ja resolvido (caso o
        # usuario passe `query=<string longa>`). InputCJPGTJSP nao tem
        # ``max_length`` em ``pesquisa``, entao ordem antes/depois do
        # pydantic e funcionalmente equivalente.
        validate_pesquisa_length(inp.pesquisa, endpoint="CJPG")

        def _get_n_pags(r0):
            html = r0.content if hasattr(r0, "content") else r0
            return cjpg_n_pags(html)

        path: str = cjpg_download_mod(
            pesquisa=inp.pesquisa,
            session=self.session,
            u_base=self.u_base,
            download_path=self.download_path,
            sleep_time=self.sleep_time,
            classe=inp.classe,
            assunto=inp.assunto,
            vara=inp.vara,
            id_processo=inp.id_processo,
            data_inicio=inp.data_julgamento_inicio,
            data_fim=inp.data_julgamento_fim,
            paginas=inp.paginas,
            get_n_pags_callback=_get_n_pags,
        )
        return path

    def cjpg_parse(self, path: str):
        """Parse downloaded CJPG HTML files into a DataFrame."""
        return cjpg_parse_manager(path)

    # --- cpopg ----------------------------------------------------------
    # Kept as-is — unique to TJSP, not eSAJ-search-shaped.

    def cpopg(self, id_cnj: str | list[str], method: Literal["html", "api"] = "html"):
        """Fetch a first-degree process by CNJ and return a DataFrame."""
        self.set_method(method)
        self.cpopg_download(id_cnj, method)
        result = self.cpopg_parse(self.download_path)
        shutil.rmtree(self.download_path)
        return result

    def cpopg_download(
        self,
        id_cnj: str | list[str],
        method: Literal["html", "api"] = "html",
    ):
        """Download raw CPOPG files for one or many CNJs via ``'html'`` or ``'api'``."""
        self.set_method(method)
        if isinstance(id_cnj, str):
            id_cnj = [id_cnj]
        if self.method == "html":
            def get_links_callback(response):
                return get_cpopg_download_links(response)
            cpopg_download_html(
                id_cnj_list=id_cnj,
                session=self.session,
                u_base=self.u_base,
                download_path=self.download_path,
                sleep_time=self.sleep_time,
                get_links_callback=get_links_callback,
            )
        elif self.method == "api":
            cpopg_download_api(
                id_cnj_list=id_cnj,
                session=self.session,
                api_base=self.api_base,
                download_path=self.download_path,
            )
        else:
            raise ValueError(f"Método '{method}' não é suportado.")

    def cpopg_parse(self, path: str):
        """Parse downloaded CPOPG files into a DataFrame."""
        return cpopg_parse_manager(path)

    # --- cposg ----------------------------------------------------------

    def cposg(self, id_cnj: str, method: Literal["html", "api"] = "html"):
        """Fetch a second-degree process by CNJ and return a DataFrame."""
        self.set_method(method)
        path = self.download_path
        self.cposg_download(id_cnj, method)
        result = self.cposg_parse(path)
        if os.path.exists(path):
            shutil.rmtree(path)
        else:
            logger.warning("[TJSP] Aviso: diretório %s não existe e não pôde ser removido.", path)
        return result

    def cposg_download(self, id_cnj: str | list, method: Literal["html", "api"] = "html"):
        """Download raw CPOSG files for one or many CNJs via ``'html'`` or ``'api'``."""
        self.set_method(method)
        if isinstance(id_cnj, str):
            id_cnj = [id_cnj]
        if self.method == "html":
            cposg_download_html(
                id_cnj_list=id_cnj,
                session=self.session,
                u_base=self.u_base,
                download_path=self.download_path,
                sleep_time=self.sleep_time,
            )
        elif self.method == "api":
            cposg_download_api(
                id_cnj_list=id_cnj,
                session=self.session,
                api_base=self.api_base,
                download_path=self.download_path,
                sleep_time=self.sleep_time,
            )
        else:
            raise ValueError(f"Método '{method}' não é suportado.")

    def cposg_parse(self, path: str):
        """Parse downloaded CPOSG files into a DataFrame."""
        return cposg_parse_manager(path)


__all__ = ["TJSPScraper", "QueryTooLongError"]
