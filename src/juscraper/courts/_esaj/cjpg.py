"""cjpg do eSAJ (consulta de julgados de primeiro grau), comum a TJSP e TJMS.

Os dois portais usam as mesmas rotas e parâmetros de busca e paginação. O
download fica em :mod:`.cjpg_download`, o parse em :mod:`.cjpg_parse` e os
schemas em :mod:`.schemas` (``InputCJPGEsaj``/``OutputCJPGEsaj``). O limite de
tamanho de ``pesquisa`` fica no hook :meth:`EsajSearchScraper._validate_pesquisa`
de cada tribunal: o de 120 caracteres é do TJSP.
"""
from __future__ import annotations

from typing import Any, ClassVar

import pandas as pd
from pydantic import BaseModel

from ...core.avisos import avisar
from ...utils.params import apply_input_pipeline_search, pop_deprecated_alias, validate_intervalo_datas
from .base import ESAJ_JANELA_ANOS, EsajSearchScraper, somar_contagens_por_janela
from .cjpg_download import cjpg_download as cjpg_download_mod
from .cjpg_download import fetch_cjpg_first_page
from .cjpg_parse import cjpg_n_results, cjpg_parse_manager
from .schemas import InputCJPGEsaj
from .sentenca import EsajSentencaScraper

# Plurais legados de cjpg (refs #232). Singular canonico ja declarado em
# ``InputCJPGEsaj``; plurais aparecem so como alias deprecados.
_CJPG_PLURAL_ALIASES: tuple[tuple[str, str], ...] = (
    ("classes", "classe"),
    ("assuntos", "assunto"),
    ("varas", "vara"),
)


def _pop_cjpg_plural_aliases(kwargs: dict) -> None:
    """Popa aliases plurais cjpg (``classes``/``assuntos``/``varas`` -> singular).

    Chamado em duas posicoes de :class:`EsajCjpgScraper`:

    1. ``cjpg()`` antes de :func:`run_auto_chunk` — a validacao upfront do
       schema dentro do chunking nao tolera kwargs nao-canonicos
       (``extra_forbidden`` em :class:`InputCJPGEsaj`), entao precisa
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


class EsajCjpgScraper(EsajSentencaScraper):
    """Base eSAJ com ``cjpg`` e o PDF da sentença de cada linha dele (``baixar_sentenca``)."""

    INPUT_CJPG: type[BaseModel] = InputCJPGEsaj

    # Alem das arvores de cjsg herdadas de EsajSearchScraper, as de 1o grau
    # (cjpg). Os stems do cjpg sao no SINGULAR (``classeTreeSelect`` etc.),
    # diferente do plural do cjsg. O formulario do cjpg tem as mesmas tres
    # arvores, nas mesmas rotas, no TJSP e no TJMS (samples
    # ``cjpg/results_normal_page_01.html`` dos dois). Refs #228, #487.
    TREE_ENDPOINTS: ClassVar[dict[str, str]] = {
        **EsajSearchScraper.TREE_ENDPOINTS,
        "classes_1": "cjpg/classeTreeSelect.do?campoId=classes",
        "assuntos_1": "cjpg/assuntoTreeSelect.do?campoId=assuntos",
        "varas_1": "cjpg/varasTreeSelect.do?campoId=varas",
    }

    def listar_varas(self, *, grau: str = "1") -> pd.DataFrame:
        """Lista as varas de primeiro grau disponiveis para filtrar (cjpg).

        Baixa a arvore de varas do eSAJ para descobrir os IDs aceitos pelo
        filtro ``vara`` de :meth:`cjpg`. A arvore agrupa as varas por
        comarca/foro, entao ``id_pai``/``caminho`` carregam essa hierarquia.

        Args:
            grau: ``"1"`` (primeiro grau / cjpg). Unico valor aceito.

        Raises:
            ValueError: Quando ``grau`` nao esta disponivel.

        Returns:
            Arvore de varas (colunas ``id``, ``nome``,
                ``id_pai``, ``nivel``, ``selecionavel``, ``caminho``).
        """
        return self._listar_arvore(f"varas_{grau}")

    # --- cjpg -----------------------------------------------------------
    # A orquestracao (probe count_only -> auto-chunk -> download -> parse)
    # e compartilhada com ``cjsg`` via ``EsajSearchScraper._run_search``
    # (Template Method, #205). Os internals de download/parse
    # (``cjpg_download.py`` + ``cjpg_parse.py``) entram em
    # ``_run_search`` como hooks resolvidos por nome.

    def cjpg(
        self,
        pesquisa: str = "",
        paginas: int | list | range | None = None,
        **kwargs: Any,
    ) -> pd.DataFrame | int:
        """Pesquisa jurisprudencia de primeiro grau do tribunal (CJPG).

        Delega para :meth:`cjpg_download` + :meth:`cjpg_parse` e remove
        o diretorio temporario antes de retornar. Diferente do CJSG, aqui
        ``pesquisa`` aceita string vazia — o usuario pode buscar so por
        filtros (ex.: todas as decisoes de uma vara especifica num
        intervalo de datas).

        Args:
            pesquisa (str): Termo livre buscado na decisao. Default
                ``""`` (sem termo). No TJSP, limite de 120 caracteres
                (raises ``QueryTooLongError``).
            paginas (int | list | range | None): Paginas 1-based;
                ``None`` baixa todas. Default ``None``.
            **kwargs: Filtros aceitos por :class:`InputCJPGEsaj` (todos
                opcionais; ``None`` = sem filtro):

                * ``classe`` (int | str | list[int | str]): ID(s) internos
                  de classe processual. Backend:
                  ``classeTreeSelection.values`` (CSV).
                * ``assunto`` (int | str | list[int | str]): ID(s) internos
                  de assunto. Backend: ``assuntoTreeSelection.values``
                  (CSV).
                * ``vara`` (int | str | list[int | str]): ID(s) internos de
                  vara, no formato em arvore do eSAJ (ex.: ``"1-1-1"``).
                  Backend: ``varasTreeSelection.values`` (CSV).
                * ``id_processo`` (str): Numero CNJ formatado para
                  filtrar uma instancia especifica. Normalizado via
                  :func:`clean_cnj` antes do envio.
                * ``data_julgamento_inicio`` / ``data_julgamento_fim``
                  (str, ``DD/MM/AAAA``): Intervalo de julgamento.
                * ``auto_chunk`` (bool): Default ``True``. Quando o
                  intervalo ``data_julgamento_*`` excede 1 ano,
                  divide internamente em janelas, baixa cada uma e
                  concatena com dedup por ``id_processo``. Veja a secao
                  "Auto-chunking" abaixo.
                * ``count_only`` (bool): Default ``False``. Se ``True``,
                  faz so o GET inicial, extrai o total de resultados via
                  ``cjpg_n_results`` e retorna ``int`` em vez de
                  ``pd.DataFrame``. Util pra estimar wall-clock antes de
                  coleta longa (issue #92). Com ``auto_chunk=True`` +
                  janela > 1 ano, itera janelas disjuntas e soma —
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
            QueryTooLongError: No TJSP, quando ``pesquisa`` excede 120 chars.
            ValueError: Quando ``classe`` e ``classes`` (ou par equivalente)
                sao passados simultaneamente.
            ColetaParcialError: Quando parte das paginas baixadas nao pode
                ser lida; ``.resultado`` traz as paginas lidas. Ver
                :func:`~juscraper.courts._esaj.cjpg_parse.cjpg_parse_manager`.

        Returns:
            Resultados parseados (colunas conforme
                :class:`OutputCJPGEsaj` — ``id_processo``, ``cd_processo`` e
                campos extras emitidos pelo parser via ``extra='allow'`` —
                ``classe``, ``assunto``, ``magistrado``, ``comarca``,
                ``foro``, ``vara``, ``data_disponibilizacao``, ``decisao``);
                ``int`` com o total de resultados quando ``count_only=True``.

        Examples: Exemplo
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

        See Also:
            :class:`~juscraper.courts._esaj.schemas.InputCJPGEsaj` —
            schema pydantic e a fonte da verdade dos filtros aceitos.

        Auto-chunking (issue #130):
            Se ``auto_chunk=True`` (default herdado de
            :class:`~juscraper.schemas.AutoChunkMixin`) e o intervalo
            ``data_julgamento_*`` exceder 1 ano, a busca e dividida em
            janelas internas, baixadas e concatenadas com dedup por
            ``id_processo``. Janela que falha levanta
            :class:`~juscraper.core.exceptions.ColetaParcialError`, com as
            janelas que passaram em ``.resultado``. ``auto_chunk=True`` + ``paginas != None``
            em janela > 1 ano e :class:`ValueError`.
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

        Multi-janela: se o intervalo ``data_julgamento_*`` excede 1 ano
        e ``auto_chunk=True``, itera janelas disjuntas via
        :func:`iter_date_windows`. ``auto_chunk=False`` + janela > 1 ano
        levanta :class:`ValueError` (consistencia com caminho normal).

        **Fail-fast no auto-chunk**: o caminho normal (:func:`run_auto_chunk`)
        tenta todas as janelas e levanta
        :class:`~juscraper.core.exceptions.ColetaParcialError` com o parcial;
        este probe usa ``sum()``, e a primeira janela que falha aborta a
        iteracao. Contagem parcial nao tem uso, entao nao vale carrega-la.
        """
        if paginas is not None:
            avisar(
                "paginas e ignorado quando count_only=True (probe sempre olha so a pagina 1).",
                UserWarning,
            )

        inp = apply_input_pipeline_search(
            self.INPUT_CJPG,
            f"{type(self).__name__}.cjpg(count_only=True)",
            pesquisa=pesquisa,
            paginas=None,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            nullable_pesquisa=True,
            max_dias=None,
            origem_mensagem="O eSAJ",
        )
        self._validate_pesquisa(inp.pesquisa, endpoint="cjpg")

        auto_chunk = inp.auto_chunk
        di = inp.data_julgamento_inicio
        df_ = inp.data_julgamento_fim

        if not auto_chunk:
            validate_intervalo_datas(
                di, df_, max_anos=ESAJ_JANELA_ANOS, rotulo="data_julgamento", origem="O eSAJ",
            )

        def _probe(win_i: str | None, win_f: str | None) -> int:
            r0 = fetch_cjpg_first_page(
                pesquisa=inp.pesquisa,
                session=self.session,
                u_base=self.BASE_URL,
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

        return somar_contagens_por_janela(_probe, di, df_)

    def cjpg_download(
        self,
        pesquisa: str = "",
        paginas: int | list | range | None = None,
        diretorio: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Baixa as paginas HTML brutas do CJPG (sem parsear).

        Delega a normalizacao de ``pesquisa`` ao pipeline (via
        ``consume_pesquisa_aliases=True`` + ``nullable_pesquisa=True`` —
        CJPG admite busca aberta com ``pesquisa=""``). Roda o hook
        ``_validate_pesquisa`` sobre o valor ja resolvido (apos
        consumir ``query``/``termo``), para que o ``QueryTooLongError`` do
        TJSP propague mesmo quando o alias trouxe a string longa. Aceita os
        mesmos filtros de :meth:`cjpg`; veja la a lista completa.

        Args:
            pesquisa (str): Termo livre. Default ``""``. No TJSP, limite
                de 120 chars.
            paginas (int | list | range | None): Paginas 1-based;
                ``None`` baixa todas. Default ``None``.
            diretorio (str | None): Sobrescreve :attr:`download_path`
                para esta unica chamada. Default ``None``.
            **kwargs: Mesmos filtros aceitos por :meth:`cjpg` (validados
                por :class:`InputCJPGEsaj`).

        Raises:
            TypeError: Quando um kwarg desconhecido e passado.
            ValidationError: Quando um filtro tem formato invalido.
            QueryTooLongError: No TJSP, quando ``pesquisa`` (ou alias
                resolvido) excede 120 chars.
            ValueError: Quando o usuario passa um alias deprecado e o nome
                canonico simultaneamente (ex.: ``classe`` e ``classes``;
                refs #232).

        Returns:
            Caminho do diretorio onde os HTMLs foram salvos.
        """
        # Aliases plurais ja foram popados em ``cjpg()``; chamada direta a
        # ``cjpg_download()`` precisa fazer a pop tambem. ``_pop_cjpg_plural_aliases``
        # e idempotente (no-op quando ``cjpg()`` ja rodou). Refs #232.
        _pop_cjpg_plural_aliases(kwargs)

        inp = apply_input_pipeline_search(
            self.INPUT_CJPG,
            f"{type(self).__name__}.cjpg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            nullable_pesquisa=True,
            max_anos=ESAJ_JANELA_ANOS,
            origem_mensagem="O eSAJ",
        )
        # Roda apos o pipeline para validar o valor ja resolvido (caso o
        # usuario passe `query=<string longa>`). InputCJPGEsaj nao tem
        # ``max_length`` em ``pesquisa``, entao ordem antes/depois do
        # pydantic e funcionalmente equivalente.
        self._validate_pesquisa(inp.pesquisa, endpoint="cjpg")

        path: str = cjpg_download_mod(
            pesquisa=inp.pesquisa,
            session=self.session,
            u_base=self.BASE_URL,
            download_path=diretorio or self.download_path,
            sleep_time=self.sleep_time,
            classe=inp.classe,
            assunto=inp.assunto,
            vara=inp.vara,
            id_processo=inp.id_processo,
            data_inicio=inp.data_julgamento_inicio,
            data_fim=inp.data_julgamento_fim,
            paginas=inp.paginas,
        )
        return path

    def cjpg_parse(self, path: str) -> pd.DataFrame:
        """Parse downloaded CJPG HTML files into a DataFrame.

        Pagina que falha num diretorio levanta ``ColetaParcialError``, com as
        demais em ``.resultado``. Ver :func:`cjpg_parse_manager`.
        """
        return cjpg_parse_manager(path)
