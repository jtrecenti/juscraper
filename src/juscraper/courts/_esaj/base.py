"""Base class for eSAJ cjsg scrapers.

Absorbs the constructor + ``cjsg``/``cjsg_download``/``cjsg_parse`` template
shared by TJAC/TJAL/TJAM/TJCE/TJMS. Subclasses set ``BASE_URL`` and the
pydantic input schema; TJSP adds a Chrome UA and conversationId
propagation via class attributes.

Hooks a subclass may override:

* ``_configure_session`` — mount custom HTTPAdapter (TJCE TLS).
* ``INPUT_CJSG`` — swap ``InputCJSGEsajPuro`` for a tribunal-specific
  schema (TJSP uses ``InputCJSGTJSP`` which enforces a 120-char limit).
"""
from __future__ import annotations

import logging
import shutil
import warnings
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from ...core.http import HTTPScraper
from ...utils.params import (
    DATE_ALIAS_TO_CANONICAL,
    DATE_CANONICAL,
    apply_input_pipeline_search,
    coerce_brazilian_date,
    fill_open_ended_dates,
    iter_date_windows,
    normalize_datas,
    normalize_pesquisa,
    pop_normalize_aliases,
    raise_on_extra_kwargs,
    run_chunked_search,
    validate_intervalo_datas,
)
from .download import download_cjsg_pages, fetch_cjsg_first_page
from .forms import build_cjsg_form_body
from .parse import cjsg_n_pags, cjsg_n_results, cjsg_parse_manager
from .schemas import InputCJSGEsajPuro

logger = logging.getLogger("juscraper._esaj.base")


def run_auto_chunk(
    *,
    method: Callable[..., Any],
    method_label: str,
    input_cls: type[BaseModel],
    dedup_key: str,
    pesquisa: str,
    paginas: Any,
    kwargs: dict,
) -> Any:
    """Orquestra a busca auto-chunked pelo limite de janela do eSAJ (#130).

    Consolida o boilerplate compartilhado entre :meth:`EsajSearchScraper.cjsg`
    e :meth:`TJSPScraper.cjpg`:

    1. Pop ``auto_chunk`` (default ``True``) — se ``False``, retorna ``None``.
    2. Sniff de ``normalize_datas`` (com warnings suprimidos para nao
       duplicar a emissao do caminho ``*_download``).
    3. Se a janela cabe em ``max_dias=366``, retorna ``None`` (caller cai no
       caminho noop).
    4. Detecta conflito ``pesquisa + query/termo`` antes do
       :func:`pop_normalize_aliases` descartar o alias silentemente.
    5. Pop aliases + canonicals de data, monta ``extras`` (dates
       nao-julgamento sniffadas), valida o schema upfront para converter
       ``extra_forbidden`` em ``TypeError`` cedo.
    6. Constroi ``_fetch`` que delega de volta para ``method`` com
       ``auto_chunk=False`` e os ``extras`` re-injetados em cada janela
       (probe TJAC 2026-04: backend AND'a julgamento + publicacao).

    Returns:
        ``None`` quando o chunking nao se aplica (auto_chunk=False ou
        janela curta) — caller deve seguir o caminho noop. Caso contrario,
        retorna o ``pd.DataFrame`` deduplicado.

    Side effects:
        Quando o chunking dispara, muta ``kwargs`` removendo aliases/canonicals
        de data (ja absorvidos no sniff e re-injetados via ``extras``).
    """
    auto_chunk = kwargs.pop("auto_chunk", True)
    if not auto_chunk:
        return None

    # Suprimir DeprecationWarning aqui evita duplicacao quando o caminho
    # *_download chamar normalize_datas/normalize_pesquisa de novo.
    # ``fill_open_ended_dates`` emite ``UserWarning`` (categoria diferente),
    # que passa pelo filtro acima e chega ao usuário. Auto-fill ANTES de
    # ``iter_date_windows``: se ``_inicio`` chega ``None`` com ``_fim``
    # preenchido, sem o fill ``iter_date_windows`` faria passthrough e o
    # auto-chunk pularia exatamente o caso que precisa dividir.
    date_format = getattr(input_cls, "BACKEND_DATE_FORMAT", "%d/%m/%Y")
    schema_field_names = set(input_cls.model_fields.keys())
    has_data_publicacao = {"data_publicacao_inicio", "data_publicacao_fim"}.issubset(schema_field_names)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        sniff = normalize_datas(**kwargs)

    # Coage formato não-canônico antes do auto-fill. Sem isso, um valor em
    # formato divergente do backend (ex.: ISO "2024-01-01" num backend BR)
    # chegaria ao ``iter_date_windows`` e quebraria com ``ValueError`` técnico
    # do ``strptime``. ``coerce_brazilian_date`` é passthrough seguro — formato
    # realmente inválido cai depois no ``validate_intervalo_datas`` com
    # mensagem amigável.
    for _key in DATE_CANONICAL:
        sniff[_key] = coerce_brazilian_date(sniff[_key], date_format)

    # Auto-fill fora do ``catch_warnings`` para que ``UserWarning`` chegue.
    fill_open_ended_dates(sniff, formato=date_format, rotulo="data_julgamento")
    # Também preenche ``data_publicacao`` aqui — caso contrário, no caminho
    # auto-chunk com N janelas o fill seria refeito dentro de cada chunk
    # pelo ``apply_input_pipeline_search``, emitindo o ``UserWarning`` N
    # vezes (uma por chunk, antes do filtro padrão do warnings deduplicar).
    # Pre-fill aqui garante 1 warning total.
    if has_data_publicacao:
        fill_open_ended_dates(sniff, formato=date_format, rotulo="data_publicacao")

    dj_i = sniff["data_julgamento_inicio"]
    dj_f = sniff["data_julgamento_fim"]
    windows = list(iter_date_windows(dj_i, dj_f, max_dias=366))
    if len(windows) <= 1:
        # Caminho noop: o caller cai em ``cjpg_download`` direto, e o
        # ``apply_input_pipeline_search`` lá faria seu próprio auto-fill,
        # duplicando o warning. Propaga o ``sniff`` canonicalizado para
        # ``kwargs`` para que o pipeline downstream veja ambas datas
        # preenchidas e seu auto-fill vire noop. Como ``normalize_datas``
        # rodou sob ``catch_warnings`` (silenciou ``DeprecationWarning``)
        # e popou os aliases, re-emitimos manualmente aqui o warning para
        # cada alias que estava em ``kwargs`` original — preservando o
        # contrato do ``normalize_datas`` downstream que esperava esse
        # warning. Fonte única dos aliases: :data:`DATE_ALIAS_TO_CANONICAL`.
        for _alias, _canonical in DATE_ALIAS_TO_CANONICAL.items():
            if _alias in kwargs:
                warnings.warn(
                    f"O parâmetro '{_alias}' está deprecado. Use '{_canonical}' em vez disso.",
                    DeprecationWarning,
                    stacklevel=3,
                )
                kwargs.pop(_alias)
        kwargs["data_julgamento_inicio"] = dj_i
        kwargs["data_julgamento_fim"] = dj_f
        # Propaga ``data_publicacao`` (já filled acima quando aplicável)
        # para que o pipeline downstream veja ambas as datas preenchidas
        # e seu auto-fill vire noop.
        for _key in ("data_publicacao_inicio", "data_publicacao_fim"):
            if sniff.get(_key) is not None:
                kwargs[_key] = sniff[_key]
        return None

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)

        # Detectar conflito pesquisa + alias deprecado ANTES de
        # pop_normalize_aliases, que descartaria o alias silentemente. cjpg
        # admite pesquisa="" — passar None para nao bater no falso positivo
        # de normalize_pesquisa quando so o alias foi fornecido.
        has_search_alias = "query" in kwargs or "termo" in kwargs
        if pesquisa or has_search_alias:
            normalize_pesquisa(pesquisa or None, **kwargs)

    pop_normalize_aliases(kwargs, include_canonical=True)
    extras = {
        k: v for k, v in sniff.items()
        if v is not None and not k.startswith("data_julgamento")
    }

    try:
        input_cls(
            pesquisa=pesquisa,
            paginas=paginas,
            data_julgamento_inicio=dj_i,
            data_julgamento_fim=dj_f,
            **extras,
            **kwargs,
        )
    except ValidationError as exc:
        raise_on_extra_kwargs(exc, method_label)
        raise

    def _fetch(win_i: str | None, win_f: str | None) -> Any:
        return method(
            pesquisa=pesquisa,
            paginas=None,
            data_julgamento_inicio=win_i,
            data_julgamento_fim=win_f,
            auto_chunk=False,
            **extras,
            **kwargs,
        )

    return run_chunked_search(
        _fetch,
        data_inicio=dj_i,
        data_fim=dj_f,
        dedup_key=dedup_key,
        max_dias=366,
        paginas=paginas,
        rotulo="data_julgamento",
        origem="O eSAJ",
    )


class EsajSearchScraper(HTTPScraper):
    """Shared scaffolding for eSAJ cjsg scrapers.

    Class attributes:
        BASE_URL: eSAJ root, e.g. ``https://esaj.tjac.jus.br/`` (must end
            with ``/``).
        TRIBUNAL_NAME: Used in logs and :attr:`BaseScraper.tribunal_name`.
        INPUT_CJSG: Pydantic model validating ``cjsg`` inputs. Defaults to
            :class:`InputCJSGEsajPuro`. TJSP overrides with its own model.
        CJSG_CHROME_UA: TJSP only — sends the Chrome-flavoured UA that the
            eSAJ form expects from browsers.
        CJSG_EXTRACT_CONVERSATION_ID: TJSP only — capture ``conversationId``
            from the first-page HTML and propagate to subsequent GETs.

    Session lifecycle (issue #203):
        ``self.session`` é criada por :class:`HTTPScraper.__init__`; o hook
        :meth:`_configure_session` é chamado lá com a mesma assinatura.
        Subclasses que sobrepõem o hook (TJCE para TLS) continuam funcionando
        sem alteração.
    """

    BASE_URL: str = ""
    TRIBUNAL_NAME: str = ""
    INPUT_CJSG: type[BaseModel] = InputCJSGEsajPuro
    CJSG_CHROME_UA: bool = False
    CJSG_EXTRACT_CONVERSATION_ID: bool = False

    def __init__(
        self,
        verbose: int = 0,
        download_path: str | None = None,
        sleep_time: float = 1.0,
        **kwargs: Any,
    ):
        if not self.BASE_URL:
            raise NotImplementedError(
                f"{type(self).__name__} must set BASE_URL as a class attribute."
            )
        super().__init__(
            self.TRIBUNAL_NAME or type(self).__name__,
            verbose=verbose,
            download_path=download_path,
            sleep_time=sleep_time,
            **kwargs,
        )

    # --- search template ------------------------------------------------

    def _run_search(
        self,
        *,
        endpoint: str,
        input_cls: type[BaseModel],
        dedup_key: str,
        pesquisa: str,
        paginas: int | list | range | None,
        kwargs: dict,
        pre_normalize: Callable[[dict], None] | None = None,
    ) -> Any:
        """Template Method que orquestra um endpoint de busca eSAJ (refs #205).

        Compartilhado por :meth:`cjsg` e :meth:`TJSPScraper.cjpg`. O fluxo —
        probe ``count_only`` -> auto-chunk -> download -> parse -> cleanup do
        diretorio temporario — e identico entre os dois endpoints. O que
        diverge (schema, chave de dedup, normalizacao previa, metodos de
        download/parse/count) entra por parametro ou e resolvido por nome via
        ``getattr``, mantendo este metodo agnostico a HTTP e parsing.

        Args:
            endpoint: ``"cjsg"`` ou ``"cjpg"``. Resolve os hooks
                ``<endpoint>_download``, ``<endpoint>_parse`` e
                ``_<endpoint>_count_only`` por ``getattr(self, ...)``.
            input_cls: Schema pydantic do endpoint (``INPUT_CJSG`` /
                ``INPUT_CJPG``), repassado ao auto-chunk.
            dedup_key: Coluna usada para deduplicar resultados cross-janela no
                auto-chunk (``cd_acordao`` no cjsg, ``id_processo`` no cjpg).
            pre_normalize: Hook opcional aplicado a ``kwargs`` antes de tudo —
                cjpg usa para popar os aliases plurais (#232).

        Returns:
            ``pd.DataFrame`` com os resultados parseados, ou ``int`` quando
            ``count_only=True``.
        """
        if pre_normalize is not None:
            pre_normalize(kwargs)

        # count_only=True: probe leve antes do run_auto_chunk (issue #92).
        # auto_chunk soma DataFrames com dedup; count_only soma ints brutos.
        if kwargs.get("count_only", False):
            count_probe = getattr(self, f"_{endpoint}_count_only")
            return count_probe(pesquisa=pesquisa, paginas=paginas, **kwargs)

        chunked = run_auto_chunk(
            method=getattr(self, endpoint),
            method_label=f"{type(self).__name__}.{endpoint}()",
            input_cls=input_cls,
            dedup_key=dedup_key,
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
        )
        if chunked is not None:
            return chunked

        download = getattr(self, f"{endpoint}_download")
        parse = getattr(self, f"{endpoint}_parse")
        path = download(pesquisa=pesquisa, paginas=paginas, **kwargs)
        try:
            return parse(path)
        finally:
            shutil.rmtree(path, ignore_errors=True)

    # --- cjsg -----------------------------------------------------------

    def cjsg(
        self,
        pesquisa: str,
        paginas: int | list | range | None = None,
        **kwargs: Any,
    ):
        """Pesquisa jurisprudencia de segundo grau do tribunal (CJSG).

        Delega para :meth:`cjsg_download` + :meth:`cjsg_parse` e remove o
        diretorio temporario antes de retornar.

        Args:
            pesquisa (str): Termo livre buscado no acordao/ementa.
            paginas (int | list | range | None): Paginas 1-based;
                ``None`` baixa todas. Default ``None``.
            **kwargs: Filtros aceitos pelo schema configurado em
                :attr:`INPUT_CJSG` (default :class:`InputCJSGEsajPuro`,
                herdado por TJAC/TJAL/TJAM/TJCE/TJMS). Subclasses podem
                trocar ``INPUT_CJSG`` e mudar a lista de filtros — TJSP
                usa :class:`InputCJSGTJSP`. Filtros do schema padrao
                (todos opcionais; ``None`` = sem filtro):

                * ``ementa`` (str): Termo buscado especificamente na
                  ementa.
                * ``numero_recurso`` (str): Numero do recurso.
                * ``classe`` (int | str | list[int | str]): ID(s) interno(s)
                  da classe processual. Backend:
                  ``classesTreeSelection.values`` (CSV).
                * ``assunto`` (int | str | list[int | str]): ID(s) interno(s)
                  do assunto. Backend: ``assuntosTreeSelection.values``
                  (CSV).
                * ``comarca`` (int | str): ID interno da comarca. Backend:
                  ``cdComarca`` (single-value, nao aceita lista).
                * ``orgao_julgador`` (int | str | list[int | str]): ID(s)
                  interno(s) do orgao julgador. Backend:
                  ``secoesTreeSelection.values`` (CSV).
                * ``origem`` (Literal["T", "R"]): ``"T"`` (segundo grau,
                  default) ou ``"R"`` (colegio recursal).
                * ``tipo_decisao`` (Literal["acordao", "monocratica"]):
                  Default ``"acordao"``.
                * ``data_julgamento_inicio`` / ``data_julgamento_fim``
                  (str, ``DD/MM/AAAA``): Intervalo de julgamento.
                * ``data_publicacao_inicio`` / ``data_publicacao_fim``
                  (str, ``DD/MM/AAAA``): Intervalo de publicacao.
                * ``auto_chunk`` (bool): Default ``True``. Quando o
                  intervalo ``data_julgamento_*`` excede 366 dias,
                  divide internamente em janelas, baixa cada uma e
                  concatena com dedup por ``cd_acordao``. Veja a secao
                  "Auto-chunking" abaixo.
                * ``count_only`` (bool): Default ``False``. Se ``True``,
                  faz so a chamada inicial da pagina 1, extrai o total
                  de resultados via ``cjsg_n_results`` e retorna ``int``
                  em vez de ``pd.DataFrame``. Util pra estimar wall-clock
                  antes de uma coleta longa (issue #92). Com
                  ``auto_chunk=True`` + janela > 366 dias, itera janelas
                  disjuntas e soma — **soma bruta** (sem dedup por
                  ``cd_acordao``), pode divergir ligeiramente de
                  ``len(cjsg(...))`` quando ha acordaos republicados.
                  ``paginas`` e ignorado (emite ``UserWarning``).

        Aliases deprecados (popados com ``DeprecationWarning`` antes do
        pydantic):

            * ``query`` / ``termo`` -> ``pesquisa``
            * ``data_inicio`` / ``data_fim`` -> ``data_julgamento_inicio`` / ``_fim``
            * ``data_julgamento_de`` / ``_ate`` -> ``data_julgamento_inicio`` / ``_fim``
            * ``data_publicacao_de`` / ``_ate`` -> ``data_publicacao_inicio`` / ``_fim``

        Raises:
            TypeError: Quando um kwarg desconhecido e passado (via
                :func:`raise_on_extra_kwargs`).
            ValidationError: Quando um filtro tem formato invalido.

        Returns:
            pd.DataFrame | int: Resultados parseados (colunas conforme
            :class:`OutputCJSGEsaj` — ``processo``, ``ementa``, ``relator``
            via mixin, ``data_publicacao`` via mixin, ``cd_acordao``,
            ``cd_foro``); ``int`` com o total de resultados quando
            ``count_only=True``.

        Exemplo:
            >>> import juscraper as jus
            >>> tjac = jus.scraper("tjac")
            >>> df = tjac.cjsg("dano moral", paginas=range(1, 3),
            ...                data_julgamento_inicio="01/01/2024")
            >>> # Estimativa pre-scraping (issue #92):
            >>> n = tjac.cjsg("dano moral", count_only=True)

        See also:
            :class:`InputCJSGEsajPuro` (ou
            :class:`~juscraper.courts.tjsp.schemas.InputCJSGTJSP`) —
            schema pydantic e a fonte da verdade dos filtros aceitos.

        Auto-chunking (issue #130):
            Se ``auto_chunk=True`` (default herdado de
            :class:`~juscraper.schemas.AutoChunkMixin`) e o intervalo
            ``data_julgamento_*`` exceder 366 dias, a busca e dividida em
            janelas internas, baixadas e concatenadas com dedup por
            ``cd_acordao``. Falhas por janela viram :class:`UserWarning`
            (parcial + warning). ``auto_chunk=True`` + ``paginas != None``
            em janela > 366 dias e :class:`ValueError`. Para o
            comportamento estrito antigo (``ValueError`` em janelas
            longas), passe ``auto_chunk=False``.
        """
        return self._run_search(
            endpoint="cjsg",
            input_cls=self.INPUT_CJSG,
            dedup_key="cd_acordao",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
        )

    def _cjsg_count_only(
        self,
        pesquisa: str,
        paginas: int | list | range | None,
        **kwargs: Any,
    ) -> int:
        """Probe leve para ``cjsg(count_only=True)`` — refs #92.

        Faz POST + GET da primeira pagina por janela, extrai ``n_results``
        via :func:`cjsg_n_results` e retorna a soma. ``paginas`` e
        ignorado (count_only sempre olha a pagina 1).

        Multi-janela: se o intervalo ``data_julgamento_*`` excede 366 dias
        e ``auto_chunk=True`` (default), itera janelas disjuntas
        (:func:`iter_date_windows`) e soma. ``auto_chunk=False`` + janela
        > 366 dias levanta :class:`ValueError` (mesmo comportamento do
        caminho normal). Intervalo ``data_publicacao_*`` > 366 dias tambem
        levanta :class:`ValueError` em qualquer ``auto_chunk`` — auto-chunk
        so pivota em ``data_julgamento``, entao publicacao precisa ser
        validada explicitamente para consistencia com o caminho normal.

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

        # Validacao do schema com max_dias=None — vamos iterar janelas
        # manualmente ou disparar ValueError abaixo conforme auto_chunk.
        # ``consume_pesquisa_aliases=True`` deixa o helper consumir
        # ``query``/``termo`` em uma unica passagem; sem ``nullable_pesquisa``
        # porque o caminho normal de cjsg tambem nao aceita pesquisa vazia
        # sem filtro (excecao TJSP, onde a chamada parte com ``pesquisa=""``
        # e seguiria pelo mesmo fluxo do caminho normal).
        input_model = apply_input_pipeline_search(
            self.INPUT_CJSG,
            f"{type(self).__name__}.cjsg(count_only=True)",
            pesquisa=pesquisa,
            paginas=None,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            max_dias=None,
            origem_mensagem="O eSAJ",
        )

        di = input_model.data_julgamento_inicio
        df_ = input_model.data_julgamento_fim
        auto_chunk = input_model.auto_chunk
        tipo_decisao = input_model.tipo_decisao

        # ``data_publicacao_*`` existe so em InputCJSGEsajPuro (via
        # DataPublicacaoMixin); InputCJSGTJSP nao herda. ``getattr`` cobre
        # ambos os schemas sem ramo if/else.
        dp_i = getattr(input_model, "data_publicacao_inicio", None)
        dp_f = getattr(input_model, "data_publicacao_fim", None)

        # auto_chunk=False + janela > 366d: replicar o ValueError do caminho
        # normal para consistencia. validate_intervalo_datas tolera None.
        # ``data_julgamento`` so quando auto_chunk=False (auto_chunk=True
        # divide em janelas). ``data_publicacao`` sempre, porque auto-chunk
        # nao pivota em publicacao — caminho normal valida nos dois fluxos.
        if not auto_chunk:
            validate_intervalo_datas(
                di, df_, max_dias=366, rotulo="data_julgamento", origem="O eSAJ",
            )
        validate_intervalo_datas(
            dp_i, dp_f, max_dias=366, rotulo="data_publicacao", origem="O eSAJ",
        )

        def _probe(win_i: str | None, win_f: str | None) -> int:
            body_input = input_model.model_copy(update={
                "data_julgamento_inicio": win_i,
                "data_julgamento_fim": win_f,
            })
            body = self._build_cjsg_body(body_input)
            html = fetch_cjsg_first_page(
                scraper=self,
                base_url=self.BASE_URL,
                body=body,
                tipo_decisao=tipo_decisao,
                sleep_time=self.sleep_time,
                chrome_ua=self.CJSG_CHROME_UA,
            )
            return cjsg_n_results(html)

        if not auto_chunk or di is None or df_ is None:
            return _probe(di, df_)

        return sum(_probe(win_i, win_f) for win_i, win_f in iter_date_windows(di, df_, max_dias=366))

    def cjsg_download(
        self,
        pesquisa: str,
        paginas: int | list | range | None = None,
        diretorio: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Baixa as paginas HTML brutas do CJSG (sem parsear).

        Faz o GET inicial, extrai o numero de paginas, paga o resto e
        salva todos os HTMLs em disco. Aceita os mesmos filtros de
        :meth:`cjsg`; consulte la a lista completa.

        Args:
            pesquisa (str): Termo livre buscado.
            paginas (int | list | range | None): Paginas 1-based;
                ``None`` baixa todas. Default ``None``.
            diretorio (str | None): Sobrescreve :attr:`download_path`
                para esta unica chamada. Default ``None``.
            **kwargs: Mesmos filtros aceitos por :meth:`cjsg` (validados
                por :attr:`INPUT_CJSG`). Veja a docstring de :meth:`cjsg`
                para a lista detalhada e os aliases deprecados.

        Raises:
            TypeError: Quando um kwarg desconhecido e passado.
            ValidationError: Quando um filtro tem formato invalido.

        Returns:
            str: Caminho do diretorio onde os HTMLs foram salvos.
        """
        pesquisa = normalize_pesquisa(pesquisa, **kwargs)

        input_model = apply_input_pipeline_search(
            self.INPUT_CJSG,
            f"{type(self).__name__}.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            max_dias=366,
            origem_mensagem="O eSAJ",
        )

        body = self._build_cjsg_body(input_model)

        return download_cjsg_pages(
            scraper=self,
            base_url=self.BASE_URL,
            download_path=diretorio or self.download_path,
            body=body,
            tipo_decisao=getattr(input_model, "tipo_decisao", "acordao"),
            paginas=input_model.paginas,
            get_n_pags_callback=cjsg_n_pags,
            sleep_time=self.sleep_time,
            chrome_ua=self.CJSG_CHROME_UA,
            extract_conversation_id=self.CJSG_EXTRACT_CONVERSATION_ID,
            progress_desc=f"Baixando CJSG {self.tribunal_name}",
        )

    def cjsg_parse(self, path: str):
        """Parse downloaded ``cjsg`` HTML files into a ``pd.DataFrame``."""
        return cjsg_parse_manager(path)

    def _build_cjsg_body(self, inp: BaseModel) -> dict:
        """Convert the validated pydantic input into the eSAJ form body.

        Default builder assumes :class:`InputCJSGEsajPuro`. TJSP overrides
        because its body drops ``conversationId``/``dtPublicacao*`` and
        swaps ``origem`` for ``baixar_sg``.
        """
        data = inp.model_dump()
        body: dict = build_cjsg_form_body(
            pesquisa=data["pesquisa"],
            ementa=data.get("ementa"),
            numero_recurso=data.get("numero_recurso"),
            classe=data.get("classe"),
            assunto=data.get("assunto"),
            comarca=data.get("comarca"),
            orgao_julgador=data.get("orgao_julgador"),
            data_julgamento_inicio=data.get("data_julgamento_inicio"),
            data_julgamento_fim=data.get("data_julgamento_fim"),
            data_publicacao_inicio=data.get("data_publicacao_inicio"),
            data_publicacao_fim=data.get("data_publicacao_fim"),
            origem=data.get("origem", "T"),
            tipo_decisao=data.get("tipo_decisao", "acordao"),
        )
        return body
