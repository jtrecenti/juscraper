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
from typing import Any, Callable, Optional

import requests
from pydantic import BaseModel, ValidationError

from ...core.base import BaseScraper
from ...utils.params import (
    apply_input_pipeline_search,
    iter_date_windows,
    normalize_datas,
    normalize_pesquisa,
    pop_normalize_aliases,
    raise_on_extra_kwargs,
    run_chunked_search,
)
from .download import download_cjsg_pages
from .forms import build_cjsg_form_body
from .parse import cjsg_n_pags, cjsg_parse_manager
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
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        sniff = normalize_datas(**kwargs)

        dj_i = sniff["data_julgamento_inicio"]
        dj_f = sniff["data_julgamento_fim"]
        windows = list(iter_date_windows(dj_i, dj_f, max_dias=366))
        if len(windows) <= 1:
            return None

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

    def _fetch(win_i: Optional[str], win_f: Optional[str]) -> Any:
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


class EsajSearchScraper(BaseScraper):
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
        super().__init__(self.TRIBUNAL_NAME or type(self).__name__)
        self.session = requests.Session()
        self._configure_session(self.session)
        self.set_verbose(verbose)
        self.set_download_path(download_path)
        self.sleep_time = sleep_time
        self.args = kwargs

    # --- hook -----------------------------------------------------------

    def _configure_session(self, session: requests.Session) -> None:
        """Override to mount custom adapters. Default: no-op.

        TJCE attaches a TLS adapter with ``SECLEVEL=1`` to accept the court's
        outdated cipher suite.
        """

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
                * ``classe`` (str): ID interno da classe processual.
                * ``assunto`` (str): ID interno do assunto.
                * ``comarca`` (str): ID interno da comarca.
                * ``orgao_julgador`` (str): ID interno do orgao julgador.
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
            pd.DataFrame: Resultados parseados; colunas conforme
            :class:`OutputCJSGEsaj` (``processo``, ``ementa``, ``relator``
            via mixin, ``data_publicacao`` via mixin, ``cd_acordao``,
            ``cd_foro``).

        Exemplo:
            >>> import juscraper as jus
            >>> tjac = jus.scraper("tjac")
            >>> df = tjac.cjsg("dano moral", paginas=range(1, 3),
            ...                data_julgamento_inicio="01/01/2024")

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
        chunked = run_auto_chunk(
            method=self.cjsg,
            method_label=f"{type(self).__name__}.cjsg()",
            input_cls=self.INPUT_CJSG,
            dedup_key="cd_acordao",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
        )
        if chunked is not None:
            return chunked

        path = self.cjsg_download(pesquisa=pesquisa, paginas=paginas, **kwargs)
        try:
            return self.cjsg_parse(path)
        finally:
            shutil.rmtree(path, ignore_errors=True)

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
            session=self.session,
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
