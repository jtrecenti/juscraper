"""Main scraper for Tribunal de Justiça de São Paulo (TJSP)."""
from __future__ import annotations

import logging
import shutil
import tempfile
from collections.abc import Iterable
from contextlib import suppress
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel

from ...utils.params import SEARCH_ALIASES, normalize_pesquisa
from .._esaj.acordao import EsajAcordaoScraper
from .._esaj.cjpg import EsajCjpgScraper
from ._falhas import avisar_falhas_de_processo
from .cpopg_download import cpopg_download_html, validar_download_pecas
from .cpopg_parse import cpopg_parse_manager, get_cpopg_download_links, tabelas_vazias
from .cposg_download import cposg_download_html
from .cposg_parse import cposg_parse_manager
from .exceptions import QueryTooLongError, validate_pesquisa_length
from .forms import build_tjsp_cjsg_body
from .schemas import InputCJSGTJSP

logger = logging.getLogger("juscraper.tjsp")


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


def _apagar_pasta_da_chamada(pasta: str, *, raiz_criada: bool) -> None:
    """Apaga a pasta da chamada e, se ``download_path`` nasceu com ela e ficou vazio, ele também."""
    shutil.rmtree(pasta)
    if raiz_criada:
        # Se outra chamada gravou na raiz enquanto isso, ela não está vazia e fica.
        with suppress(OSError):
            Path(pasta).parent.rmdir()


def _lista_de_cnjs(id_cnj: str | Iterable) -> list:
    """Um CNJ ou vários, como lista: o composto lê os CNJs no download e no parse, e um gerador se esgotaria."""
    return [id_cnj] if isinstance(id_cnj, str) else list(id_cnj)


class TJSPScraper(EsajCjpgScraper, EsajAcordaoScraper):
    """Raspador principal do TJSP, pelas páginas do eSAJ."""

    BASE_URL = "https://esaj.tjsp.jus.br/"
    TRIBUNAL_NAME = "TJSP"
    CPOSG_PATH = "cposg/"
    MOVIMENTACOES_AJAX = True
    INPUT_CJSG = InputCJSGTJSP
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
        self.method: Literal["html"] | None = None

    def set_download_path(self, path: str | None = None) -> None:
        """Set download base dir; with ``None``, a tempdir is created on first use."""
        self._download_path = path

    def _pasta_da_chamada(self) -> tuple[str, bool]:
        """Cria pasta própria e registra se a raiz nasceu com esta chamada."""
        # A propriedade cria a raiz temporária na primeira leitura: registrar
        # sua origem antes dela para não deixar a raiz vazia após o composto.
        caminho_atual = self._download_path
        raiz_criada = caminho_atual is None or not Path(caminho_atual).exists()
        raiz = Path(self.download_path)
        raiz.mkdir(parents=True, exist_ok=True)
        return tempfile.mkdtemp(prefix="composto_", dir=raiz), raiz_criada

    def set_method(self, method: str) -> None:
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
    ) -> pd.DataFrame | int:
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
            Resultados parseados (colunas conforme
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
    ) -> dict[str, pd.DataFrame]:
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
                que o exige: ``cpopg`` apaga ao terminar a pasta em que baixou.
                Os PDFs vao para
                ``<diretorio>/cpopg/<cnj>/documentos/<cdDocumento>.pdf``. Nao
                pode ficar dentro de :attr:`download_path`. Default ``None``.

        Raises:
            ValueError: Quando ``method`` nao e suportado, quando ha
                arquivos baixados, nenhum pode ser lido e nenhum outro
                processo do lote falhou no download (nesse caso a pasta da
                chamada, dentro de :attr:`download_path`, nao e apagada), ou quando
                ``download_pecas`` e ``diretorio`` nao combinam com os demais
                argumentos.

        Returns:
            Tabelas ``basicos``, ``partes``, ``movimentacoes`` e
                ``peticoes_diversas``. ``basicos`` traz a ``situacao`` do
                cabecalho ("Extinto", "Suspenso" etc.) e ``movimentacoes`` traz
                a lista completa, que o download busca pagina a pagina. Em
                ``movimentacoes``, ``cd_documento`` e ``documento_publico``
                dizem se a linha tem documento e se ele abre sem senha;
                ``caminho_documento`` traz o PDF baixado, ou ``None`` sem
                ``download_pecas``, para documento com senha e para o que falhou
                (as falhas saem num ``UserWarning``).

                Todo CNJ pedido, e so ele, aparece em ``basicos``. O ``cpopg``
                baixa numa pasta nova dentro de :attr:`download_path` e, ao
                terminar, apaga so ela: o que um ``cpopg_download`` anterior ou
                o usuario deixou em :attr:`download_path` nao e lido nem
                apagado. A coluna ``motivo_falha``
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
                "cpopg apaga ao terminar a pasta em que baixou."
            )
        if diretorio is not None and Path(diretorio).resolve().is_relative_to(Path(self.download_path).resolve()):
            raise ValueError(f"diretorio {diretorio!r} fica dentro de download_path, onde cpopg baixa e apaga.")
        ids = _lista_de_cnjs(id_cnj)
        # Lote vazio: nada foi pedido, e o parse da pasta vazia levantaria.
        if not ids:
            return tabelas_vazias()
        pasta, raiz_criada = self._pasta_da_chamada()
        # Sem o aviso do download: o parse lê as falhas que ele gravou na
        # pasta e avisa uma vez só, junto com as de leitura.
        self._baixar_cpopg(ids, pasta, baixar_movimentacoes=baixar_movimentacoes, download_pecas=download_pecas)
        result = cpopg_parse_manager(pasta, metodo="TJSPScraper.cpopg", pedidos=ids)
        if diretorio is not None:
            result["movimentacoes"] = _mover_documentos(result["movimentacoes"], pasta, diretorio)
        _apagar_pasta_da_chamada(pasta, raiz_criada=raiz_criada)
        return result

    def cpopg_download(
        self,
        id_cnj: str | list[str],
        method: Literal["html"] = "html",
        diretorio: str | None = None,
        *,
        baixar_movimentacoes: bool = True,
        download_pecas: bool = False,
    ) -> dict[str, str]:
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
            ``{CNJ formatado: motivo_falha}`` dos processos que ficaram sem arquivo;
                vazio quando todos foram baixados. Os motivos sao os de
                :meth:`cpopg`, e as falhas tambem saem num ``UserWarning``. Elas
                ficam gravadas na pasta do download, e :meth:`cpopg_parse` as
                devolve em ``basicos``, como o :meth:`cpopg`.
        """
        self.set_method(method)
        validar_download_pecas(baixar_movimentacoes, download_pecas)
        falhas = self._baixar_cpopg(
            _lista_de_cnjs(id_cnj), diretorio or self.download_path,
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
        return cpopg_download_html(
            id_cnj_list=ids,
            session=self.session,
            u_base=self.u_base,
            download_path=pasta,
            sleep_time=self.sleep_time,
            get_links_callback=get_cpopg_download_links,
            baixar_movimentacoes=baixar_movimentacoes,
            download_pecas=download_pecas,
        )

    def cpopg_parse(self, path: str) -> dict[str, pd.DataFrame]:
        """Le os arquivos baixados do CPOPG e devolve um dict de DataFrames.

        ``basicos`` traz a coluna ``motivo_falha``, como no :meth:`cpopg`:
        o arquivo que nao pode ser lido e o processo que
        :meth:`cpopg_download` nao baixou nessa pasta saem numa linha com o
        motivo, e as falhas, num ``UserWarning``.

        Raises:
            ValueError: Quando ``path`` e um diretorio sem falha de download
                registrada e nenhum arquivo dele pode ser lido, ou quando
                ``path`` e um arquivo com extensao diferente de ``.html``. Ver
                :func:`cpopg_parse_manager`.
        """
        return cpopg_parse_manager(path)

    # --- cposg ----------------------------------------------------------

    def cposg(self, id_cnj: str, method: Literal["html"] = "html") -> pd.DataFrame:
        """Fetch a second-degree process by CNJ and return a DataFrame.

        ``method`` aceita só ``"html"``, o default; o ``"api"`` foi removido e
        levanta ``ValueError``.

        Todo CNJ pedido, e só ele, aparece no DataFrame. O ``cposg`` baixa
        numa pasta nova dentro de :attr:`download_path` e, ao terminar, apaga
        só ela: o que um ``cposg_download`` anterior ou o usuário deixou em
        :attr:`download_path` não é lido nem apagado. A coluna ``motivo_falha`` é
        ``None`` no processo lido; o CNJ que não foi baixado ganha uma linha
        só com ``processo`` e o motivo (``nao_encontrado`` quando a consulta
        de 2º grau não mostra o número, ``entrada_invalida``,
        ``http_<status>``, ``conexao``, ``timeout`` ou
        ``resposta_inesperada``), e o arquivo baixado que não pode ser lido
        sai ``resposta_inesperada``. As falhas de download e as de leitura
        saem juntas num único ``UserWarning``.
        """
        self.set_method(method)
        ids = _lista_de_cnjs(id_cnj)
        pasta, raiz_criada = self._pasta_da_chamada()
        # Como no cpopg: o parse lê as falhas do download e avisa uma vez só.
        self._baixar_cposg(ids, pasta)
        result = cposg_parse_manager(pasta, metodo="TJSPScraper.cposg", pedidos=ids)
        _apagar_pasta_da_chamada(pasta, raiz_criada=raiz_criada)
        return result

    def cposg_download(
        self,
        id_cnj: str | list,
        method: Literal["html"] = "html",
        diretorio: str | None = None,
    ) -> dict[str, str]:
        """Baixa as paginas HTML do CPOSG.

        Args:
            id_cnj: Numero CNJ ou lista de numeros CNJ.
            method: So ``"html"``, o default. Ver :meth:`cposg`.
            diretorio: Sobrescreve :attr:`download_path` para esta chamada.
                Default ``None``.

        Returns:
            ``{CNJ formatado: motivo_falha}`` dos processos que ficaram sem
                arquivo; vazio quando todos foram baixados. Os motivos são os de
                :meth:`cposg`, e as falhas também saem num ``UserWarning``. Elas
                ficam gravadas na pasta do download, e :meth:`cposg_parse` as
                devolve no DataFrame, como o :meth:`cposg`.
        """
        self.set_method(method)
        falhas = self._baixar_cposg(_lista_de_cnjs(id_cnj), diretorio or self.download_path)
        avisar_falhas_de_processo(
            falhas, [], "TJSPScraper.cposg_download",
            "Esses processos ficam sem arquivo; cposg_parse os devolve no DataFrame",
        )
        return falhas

    def _baixar_cposg(self, ids: list, pasta: str) -> dict[str, str]:
        """Download do cposg sem o aviso, que fica com quem chama: ``cposg_download`` ou o parse do ``cposg``."""
        return cposg_download_html(
            id_cnj_list=ids,
            session=self.session,
            u_base=self.u_base,
            download_path=pasta,
            sleep_time=self.sleep_time,
        )

    def cposg_parse(self, path: str) -> pd.DataFrame:
        """Parse downloaded CPOSG files into a DataFrame.

        Com a coluna ``motivo_falha``, como no :meth:`cposg`: o arquivo que não
        pode ser lido e o processo que :meth:`cposg_download` não baixou nessa
        pasta saem numa linha com o motivo, e as falhas, num ``UserWarning``.
        """
        return cposg_parse_manager(path)


__all__ = ["QueryTooLongError", "TJSPScraper"]
