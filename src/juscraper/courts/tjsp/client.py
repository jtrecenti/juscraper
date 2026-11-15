"""Main scraper for Tribunal de Justiça de São Paulo (TJSP)."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, ClassVar, Literal

import pandas as pd
from pydantic import BaseModel

from ...core.avisos import avisar
from ...utils.params import (
    SEARCH_ALIASES,
    apply_input_pipeline_search,
    normalize_pesquisa,
    pop_deprecated_alias,
    validate_intervalo_datas,
)
from .._esaj.acordao import EsajAcordaoScraper
from .._esaj.base import ESAJ_JANELA_ANOS, EsajSearchScraper, somar_contagens_por_janela
from .._esaj.sentenca import EsajSentencaScraper
from ._falhas import avisar_falhas_de_processo
from .cjpg_download import cjpg_download as cjpg_download_mod
from .cjpg_download import fetch_cjpg_first_page
from .cjpg_parse import cjpg_n_results, cjpg_parse_manager
from .cpopg_download import cpopg_download_html, validar_download_pecas
from .cpopg_parse import cpopg_parse_manager, get_cpopg_download_links, tabelas_vazias
from .cposg_download import cposg_download_html
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


def _resolve_cjsg_pesquisa(pesquisa: str | None, kwargs: dict) -> str:
    """Resolve ``pesquisa`` contra ``query``/``termo`` e popa os aliases de ``kwargs``.

    O ``cjsg`` do TJSP tem ``pesquisa=""`` como default (busca aberta,
    issue #229). Passado direto a :func:`normalize_pesquisa`, esse ``""``
    conta como valor informado, e ``cjsg(query="x")`` cairia no erro de
    conflito entre ``pesquisa`` e ``query``. Com alias presente, ``""`` vale
    como ausente, a mesma regra que :func:`run_auto_chunk` aplica no
    caminho multi-janela. ``pesquisa`` nao vazia junto de alias continua
    sendo conflito.

    Os aliases saem de ``kwargs`` aqui porque :func:`normalize_pesquisa`
    so popa da propria copia; os aliases de data ficam para a base, que
    emite o ``DeprecationWarning`` deles.
    """
    if any(alias in kwargs for alias in SEARCH_ALIASES):
        pesquisa = pesquisa or None
    resolvida = normalize_pesquisa(pesquisa, **kwargs)
    for alias in SEARCH_ALIASES:
        kwargs.pop(alias, None)
    return resolvida


def _mover_documentos(movimentacoes: pd.DataFrame, origem: str, destino: str) -> pd.DataFrame:
    """Leva os PDFs de ``download_pecas`` da pasta de download, que ``cpopg`` apaga, para ``destino``.

    Mantém o caminho relativo (``cpopg/<cnj>/documentos/<cdDocumento>.pdf``),
    o mesmo de ``cpopg_download(..., diretorio=destino)``. Um documento ligado
    a duas movimentações aparece em duas linhas e se move uma vez.
    """
    novos: dict[str, str] = {}
    for caminho in movimentacoes["caminho_documento"].dropna().unique():
        novo = Path(destino) / Path(caminho).relative_to(origem)
        novo.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(caminho, novo)
        novos[caminho] = str(novo)
    # ``dict.get`` e não ``Series.map``: a linha sem PDF continua ``None``, e não ``NaN``.
    return movimentacoes.assign(caminho_documento=[novos.get(c) for c in movimentacoes["caminho_documento"]])


class TJSPScraper(EsajSentencaScraper, EsajAcordaoScraper):
    """Raspador principal do TJSP, pelas páginas do eSAJ."""

    BASE_URL = "https://esaj.tjsp.jus.br/"
    TRIBUNAL_NAME = "TJSP"
    CPOSG_PATH = "cposg/"
    MOVIMENTACOES_AJAX = True
    INPUT_CJSG = InputCJSGTJSP
    INPUT_CJPG = InputCJPGTJSP
    CJSG_CHROME_UA = True
    CJSG_EXTRACT_CONVERSATION_ID = True

    # Alem das arvores de cjsg herdadas de EsajSearchScraper, o TJSP expoe as
    # arvores de 1o grau (cjpg). Os stems do cjpg sao no SINGULAR
    # (``classeTreeSelect`` etc.), diferente do plural do cjsg. Refs #228.
    TREE_ENDPOINTS: ClassVar[dict[str, str]] = {
        **EsajSearchScraper.TREE_ENDPOINTS,
        "classes_1": "cjpg/classeTreeSelect.do?campoId=classes",
        "assuntos_1": "cjpg/assuntoTreeSelect.do?campoId=assuntos",
        "varas_1": "cjpg/varasTreeSelect.do?campoId=varas",
    }

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
        self.method: Literal["html"] | None = None

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

    def set_download_path(self, path: str | None = None):
        """Set download base dir; with ``None``, a tempdir is created on first use."""
        self._download_path = path

    def set_method(self, method: str):
        """Valida e guarda o método de acesso do cpopg/cposg; só ``'html'`` é aceito."""
        if method == "api":
            raise ValueError(
                "method='api' foi removido: a API do TJSP (api.tjsp.jus.br) deixou de devolver "
                "processos, inclusive os que existem. Use method='html', o default."
            )
        if method != "html":
            raise ValueError(f"Método {method} nao suportado. O único método suportado é 'html'.")
        self.method = "html"

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
                  intervalo ``data_julgamento_*`` excede 1 ano,
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
            (pd.DataFrame | int): Resultados parseados (colunas conforme
                :class:`OutputCJSGTJSP` — ``processo``, ``ementa``,
                ``data_julgamento``, ``cd_acordao``, ``relator``,
                ``orgao_julgador``); ``int`` com o total de resultados quando
                ``count_only=True``.

        Examples: Exemplo
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
            ``data_julgamento_*`` > 1 ano.
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
        :meth:`EsajSearchScraper._cjsg_count_only`. Resolve ``query``/``termo``
        com :func:`_resolve_cjsg_pesquisa`, como :meth:`cjsg_download`, para
        validar o termo que de fato vai ao backend.
        """
        pesquisa = _resolve_cjsg_pesquisa(pesquisa, kwargs)
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
            Caminho do diretorio onde os HTMLs foram salvos.
        """
        pesquisa = _resolve_cjsg_pesquisa(pesquisa, kwargs)
        validate_pesquisa_length(pesquisa, endpoint="CJSG")
        return super().cjsg_download(
            pesquisa=pesquisa, paginas=paginas, diretorio=diretorio, **kwargs,
        )

    def _validate_pesquisa(self, pesquisa: str | None, *, endpoint: Literal["cjsg", "cjpg"]) -> None:
        """Aplica o limite de 120 chars antes de o auto-chunk dividir a busca em janelas."""
        validate_pesquisa_length(pesquisa, endpoint=endpoint.upper())

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
            QueryTooLongError: Quando ``pesquisa`` excede 120 chars.
            ValueError: Quando ``classe`` e ``classes`` (ou par equivalente)
                sao passados simultaneamente.
            ColetaParcialError: Quando parte das paginas baixadas nao pode
                ser lida; ``.resultado`` traz as paginas lidas. Ver
                :func:`~juscraper.courts.tjsp.cjpg_parse.cjpg_parse_manager`.

        Returns:
            (pd.DataFrame | int): Resultados parseados (colunas conforme
                :class:`OutputCJPGTJSP` — ``id_processo``, ``cd_processo`` e
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

        See also:
            :class:`~juscraper.courts.tjsp.schemas.InputCJPGTJSP` —
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
                di, df_, max_anos=ESAJ_JANELA_ANOS, rotulo="data_julgamento", origem="O eSAJ",
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

        return somar_contagens_por_janela(_probe, di, df_)

    def cjpg_download(
        self,
        pesquisa: str = "",
        paginas: int | list | range | None = None,
        diretorio: str | None = None,
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
            diretorio (str | None): Sobrescreve :attr:`download_path`
                para esta unica chamada. Default ``None``.
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
            Caminho do diretorio onde os HTMLs foram salvos.
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
            max_anos=ESAJ_JANELA_ANOS,
            origem_mensagem="O eSAJ",
        )
        # Roda apos o pipeline para validar o valor ja resolvido (caso o
        # usuario passe `query=<string longa>`). InputCJPGTJSP nao tem
        # ``max_length`` em ``pesquisa``, entao ordem antes/depois do
        # pydantic e funcionalmente equivalente.
        validate_pesquisa_length(inp.pesquisa, endpoint="CJPG")

        path: str = cjpg_download_mod(
            pesquisa=inp.pesquisa,
            session=self.session,
            u_base=self.u_base,
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

    def cjpg_parse(self, path: str):
        """Parse downloaded CJPG HTML files into a DataFrame.

        Pagina que falha num diretorio levanta ``ColetaParcialError``, com as
        demais em ``.resultado``. Ver :func:`cjpg_parse_manager`.
        """
        return cjpg_parse_manager(path)

    # --- cpopg ----------------------------------------------------------
    # Kept as-is — unique to TJSP, not eSAJ-search-shaped.

    def cpopg(
        self,
        id_cnj: str | list[str],
        method: Literal["html"] = "html",
        *,
        baixar_movimentacoes: bool = True,
        download_pecas: bool = False,
        diretorio: str | None = None,
    ):
        """Baixa processos de primeiro grau pelo CNJ e devolve as tabelas extraidas.

        Args:
            id_cnj (str | list[str]): Numero CNJ ou lista de numeros CNJ.
            method (str): So ``"html"`` (paginas do eSAJ), o default. O
                ``"api"`` foi removido e levanta ``ValueError``.
            baixar_movimentacoes (bool): Com ``False``, nao baixa as
                movimentacoes, e a tabela delas sai vazia (a pagina no formato
                antigo ja traz a lista e sai completa). Cada processo custa uma
                requisicao a mais por cinco movimentacoes, mais uma; desligar
                poupa essas requisicoes. Default ``True``.
            download_pecas (bool): Com ``True``, baixa tambem o PDF de cada
                documento publico das movimentacoes, sem login: dois pedidos
                por documento, feitos na sessao que acabou de listar as
                movimentacoes, porque o eSAJ so libera documento ja listado.
                Documento com senha do processo fica de fora. So com
                ``baixar_movimentacoes=True``. Default ``False``.
            diretorio (str | None): Onde ficam os PDFs de ``download_pecas``,
                que o exige: ``cpopg`` apaga a pasta de download ao terminar.
                Os PDFs vao para
                ``<diretorio>/cpopg/<cnj>/documentos/<cdDocumento>.pdf``. Nao
                pode ficar dentro de :attr:`download_path`. Default ``None``.

        Raises:
            ValueError: Quando ``method`` nao e suportado, quando ha
                arquivos baixados e nenhum pode ser lido (nesse caso o
                diretorio de download nao e apagado), ou quando
                ``download_pecas`` e ``diretorio`` nao combinam com os demais
                argumentos.

        Returns:
            (dict[str, pd.DataFrame]): Tabelas ``basicos``, ``partes``,
                ``movimentacoes`` e ``peticoes_diversas``. ``basicos`` traz a
                ``situacao`` do cabecalho ("Extinto", "Suspenso" etc.) e
                ``movimentacoes`` traz a lista completa, que o download busca
                pagina a pagina. Em ``movimentacoes``, ``cd_documento`` e
                ``documento_publico`` dizem se a linha tem documento e se ele
                abre sem senha; ``caminho_documento`` traz o PDF baixado, ou
                ``None`` sem ``download_pecas``, para documento com senha e para
                o que falhou (as falhas saem num ``UserWarning``).

                Todo CNJ pedido aparece em ``basicos``. A coluna ``motivo_falha``
                e ``None`` no processo lido; o CNJ que nao foi baixado ganha uma
                linha so com ``id_processo`` e o motivo (``nao_encontrado`` quando
                a consulta diz nao ter o numero, ``entrada_invalida``,
                ``http_<status>``, ``conexao``, ``timeout`` ou
                ``resposta_inesperada``), e o arquivo baixado que nao pode ser
                lido sai ``resposta_inesperada``. As falhas de download e as de
                leitura saem juntas num unico ``UserWarning``.
        """
        self.set_method(method)
        validar_download_pecas(baixar_movimentacoes, download_pecas)
        if download_pecas != (diretorio is not None):
            raise ValueError(
                "download_pecas=True exige diretorio, e diretorio so vale com download_pecas=True: "
                "cpopg apaga a pasta de download ao terminar."
            )
        if diretorio is not None and Path(diretorio).resolve().is_relative_to(Path(self.download_path).resolve()):
            raise ValueError(f"diretorio {diretorio!r} fica dentro de download_path, que cpopg apaga ao terminar.")
        ids = [id_cnj] if isinstance(id_cnj, str) else id_cnj
        # Sem o aviso do download: o parse lê as falhas que ele gravou na
        # pasta e avisa uma vez só, junto com as de leitura.
        self._baixar_cpopg(
            ids, self.download_path, baixar_movimentacoes=baixar_movimentacoes, download_pecas=download_pecas,
        )
        # Lote vazio: nada foi pedido, e o parse da pasta vazia levantaria.
        result = cpopg_parse_manager(self.download_path, metodo="TJSPScraper.cpopg") if ids else tabelas_vazias()
        if diretorio is not None:
            result["movimentacoes"] = _mover_documentos(result["movimentacoes"], self.download_path, diretorio)
        # O lote vazio não cria a pasta de download.
        if Path(self.download_path).exists():
            shutil.rmtree(self.download_path)
        return result

    def cpopg_download(
        self,
        id_cnj: str | list[str],
        method: Literal["html"] = "html",
        diretorio: str | None = None,
        *,
        baixar_movimentacoes: bool = True,
        download_pecas: bool = False,
    ):
        """Baixa as paginas HTML do CPOPG.

        Args:
            id_cnj: Numero CNJ ou lista de numeros CNJ.
            method: So ``"html"``, o default. Ver :meth:`cpopg`.
            diretorio: Sobrescreve :attr:`download_path` para esta chamada.
                Default ``None``.
            baixar_movimentacoes: Com ``False``, nao baixa as movimentacoes.
                Ver :meth:`cpopg`. Um download com ``True`` no mesmo diretorio
                baixa de novo o processo salvo sem elas.
                Default ``True``.
            download_pecas: Com ``True``, grava tambem o PDF de cada documento
                publico das movimentacoes em
                ``<diretorio>/cpopg/<cnj>/documentos/<cdDocumento>.pdf``. Ver
                :meth:`cpopg`. Um download com ``True`` no mesmo diretorio
                baixa de novo o processo salvo com documento publico sem PDF,
                e pede so os PDFs que faltam. Default ``False``.

        Returns:
            (dict[str, str]): ``{CNJ formatado: motivo_falha}`` dos processos
                que ficaram sem arquivo; vazio quando todos foram baixados. Os
                motivos sao os de :meth:`cpopg`, e as falhas tambem saem num
                ``UserWarning``. Elas ficam gravadas na pasta do download, e
                :meth:`cpopg_parse` as devolve em ``basicos``, como o :meth:`cpopg`.
        """
        self.set_method(method)
        validar_download_pecas(baixar_movimentacoes, download_pecas)
        if isinstance(id_cnj, str):
            id_cnj = [id_cnj]
        falhas = self._baixar_cpopg(
            id_cnj, diretorio or self.download_path,
            baixar_movimentacoes=baixar_movimentacoes, download_pecas=download_pecas,
        )
        avisar_falhas_de_processo(
            falhas, [], "TJSPScraper.cpopg_download",
            "Esses processos ficam sem arquivo; cpopg_parse os devolve na tabela basicos",
        )
        return falhas

    def _baixar_cpopg(
        self, ids: list, pasta: str, *, baixar_movimentacoes: bool, download_pecas: bool,
    ) -> dict[str, str]:
        """Download do cpopg sem o aviso, que fica com quem chama: ``cpopg_download`` ou o parse do ``cpopg``."""
        falhas: dict[str, str] = cpopg_download_html(
            id_cnj_list=ids,
            session=self.session,
            u_base=self.u_base,
            download_path=pasta,
            sleep_time=self.sleep_time,
            get_links_callback=get_cpopg_download_links,
            baixar_movimentacoes=baixar_movimentacoes,
            download_pecas=download_pecas,
        )
        return falhas

    def cpopg_parse(self, path: str):
        """Le os arquivos baixados do CPOPG e devolve um dict de DataFrames.

        ``basicos`` traz a coluna ``motivo_falha``, como no :meth:`cpopg`:
        o arquivo que nao pode ser lido e o processo que
        :meth:`cpopg_download` nao baixou nessa pasta saem numa linha com o
        motivo, e as falhas, num ``UserWarning``.

        Raises:
            ValueError: Quando ``path`` e um diretorio e nenhum arquivo dele
                pode ser lido, ou quando ``path`` e um arquivo com extensao
                diferente de ``.html``. Ver :func:`cpopg_parse_manager`.
        """
        return cpopg_parse_manager(path)

    # --- cposg ----------------------------------------------------------

    def cposg(self, id_cnj: str, method: Literal["html"] = "html"):
        """Fetch a second-degree process by CNJ and return a DataFrame.

        ``method`` aceita só ``"html"``, o default; o ``"api"`` foi removido e
        levanta ``ValueError``.

        Todo CNJ pedido aparece no DataFrame. A coluna ``motivo_falha`` é
        ``None`` no processo lido; o CNJ que não foi baixado ganha uma linha
        só com ``processo`` e o motivo (``nao_encontrado`` quando a consulta
        de 2º grau não mostra o número, ``entrada_invalida``,
        ``http_<status>``, ``conexao``, ``timeout`` ou
        ``resposta_inesperada``), e o arquivo baixado que não pode ser lido
        sai ``resposta_inesperada``. As falhas de download e as de leitura
        saem juntas num único ``UserWarning``.
        """
        self.set_method(method)
        path = self.download_path
        # Como no cpopg: o parse lê as falhas do download e avisa uma vez só.
        self._baixar_cposg(id_cnj, path)
        result = cposg_parse_manager(path, metodo="TJSPScraper.cposg")
        if Path(path).exists():
            shutil.rmtree(path)
        else:
            logger.warning("[TJSP] Aviso: diretório %s não existe e não pôde ser removido.", path)
        return result

    def cposg_download(
        self,
        id_cnj: str | list,
        method: Literal["html"] = "html",
        diretorio: str | None = None,
    ):
        """Baixa as paginas HTML do CPOSG.

        Args:
            id_cnj: Numero CNJ ou lista de numeros CNJ.
            method: So ``"html"``, o default. Ver :meth:`cposg`.
            diretorio: Sobrescreve :attr:`download_path` para esta chamada.
                Default ``None``.

        Returns:
            (dict[str, str]): ``{CNJ formatado: motivo_falha}`` dos processos
                que ficaram sem arquivo; vazio quando todos foram baixados. Os
                motivos são os de :meth:`cposg`, e as falhas também saem num
                ``UserWarning``. Elas ficam gravadas na pasta do download, e
                :meth:`cposg_parse` as devolve no DataFrame, como o :meth:`cposg`.
        """
        self.set_method(method)
        falhas = self._baixar_cposg(id_cnj, diretorio or self.download_path)
        avisar_falhas_de_processo(
            falhas, [], "TJSPScraper.cposg_download",
            "Esses processos ficam sem arquivo; cposg_parse os devolve no DataFrame",
        )
        return falhas

    def _baixar_cposg(self, id_cnj: str | list, pasta: str) -> dict[str, str]:
        """Download do cposg sem o aviso, que fica com quem chama: ``cposg_download`` ou o parse do ``cposg``."""
        falhas: dict[str, str] = cposg_download_html(
            id_cnj_list=[id_cnj] if isinstance(id_cnj, str) else id_cnj,
            session=self.session,
            u_base=self.u_base,
            download_path=pasta,
            sleep_time=self.sleep_time,
        )
        return falhas

    def cposg_parse(self, path: str):
        """Parse downloaded CPOSG files into a DataFrame.

        Com a coluna ``motivo_falha``, como no :meth:`cposg`: o arquivo que não
        pode ser lido e o processo que :meth:`cposg_download` não baixou nessa
        pasta saem numa linha com o motivo, e as falhas, num ``UserWarning``.
        """
        return cposg_parse_manager(path)


__all__ = ["QueryTooLongError", "TJSPScraper"]
