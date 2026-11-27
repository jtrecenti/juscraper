"""
Scraper for the Tribunal de Justica de Pernambuco (TJPE).
"""


from collections.abc import Mapping
from datetime import date
from typing import Any, ClassVar

import pandas as pd

from juscraper.core.http import HTTPScraper, RequestPolicy
from juscraper.utils.params import apply_input_pipeline_search, resolve_deprecated_alias

from .._trf.schemas import InputCpopgTRF
from .consulta_publica import TJPEConsultaPublicaScraper
from .download import cjsg_download
from .parse import cjsg_parse
from .schemas import InputCJSGTJPE


class TJPEScraper(HTTPScraper):
    """Scraper for the Tribunal de Justica de Pernambuco."""

    BASE_URL = "https://www.tjpe.jus.br/consultajurisprudenciaweb"
    #: Schema do ``cpopg``, o mesmo da família PJe ConsultaPública dos TRFs.
    INPUT_CPOPG = InputCpopgTRF

    perfis_http: ClassVar[Mapping[str, RequestPolicy]] = {
        "cjsg": RequestPolicy(timeout=30),
        "cpopg": TJPEConsultaPublicaScraper.perfis_http["cpopg"],
    }

    def __init__(self, *, politica: Mapping[str, Mapping[str, Any]] | None = None):
        super().__init__("TJPE", politica=politica)
        self._consulta_publica: TJPEConsultaPublicaScraper | None = None
        self._politica_cpopg = (
            {"cpopg": dict(politica["cpopg"])} if politica and "cpopg" in politica else None
        )

    def _consulta(self) -> TJPEConsultaPublicaScraper:
        # Sessão própria e criada na primeira consulta: o cjsg roda em outro
        # host, sem WAF, e não precisa dos cabeçalhos de navegador do PJe.
        if self._consulta_publica is None:
            self._consulta_publica = TJPEConsultaPublicaScraper(politica=self._politica_cpopg)
        return self._consulta_publica

    def cpopg_download(self, id_cnj: str | list[str], **kwargs: Any) -> list[str | None]:
        """Baixa o HTML do detalhe de cada ``id_cnj`` na consulta pública do PJe do TJPE.

        Delega a :meth:`juscraper.courts._trf.base.TRFConsultaScraper.cpopg_download`,
        na mesma sessão de :meth:`cpopg`, inclusive o cookie do AWS WAF obtido
        quando o desafio aparece. Não baixa as peças: para elas, usar
        :meth:`cpopg` com ``download_pecas=True``.

        Args:
            id_cnj (str | list[str]): CNJ único ou lista, com ou sem máscara.

        Returns:
            Lista na ordem da entrada, com o HTML do detalhe de cada CNJ.
                ``None`` indica processo que a consulta pública não devolveu:
                segredo de justiça, CNJ inexistente ou falha da requisição.
                Falhas individuais não interrompem o lote; um bloqueio do WAF
                encerra o lote, e o CNJ bloqueado e os seguintes saem ``None``.
                As falhas entram num único ``UserWarning`` ao fim;
                :meth:`cpopg` traz o motivo de cada uma em ``motivo_falha``.

        Raises:
            TypeError: Kwarg desconhecido.
            ImportError: O WAF desafiou e o Playwright não está instalado.

        Examples: Exemplo
            >>> import juscraper as jus
            >>> tjpe = jus.scraper("tjpe")
            >>> cnjs = ["0000000-00.0000.8.17.0000"]
            >>> htmls = tjpe.cpopg_download(cnjs)
            >>> df = tjpe.cpopg_parse(htmls, cnjs)

        See Also:
            :class:`InputCpopgTRF` — schema pydantic e a fonte da verdade dos
            parâmetros aceitos.
        """
        return self._consulta().cpopg_download(id_cnj, **kwargs)

    def cpopg_parse(self, htmls: list[str | None], id_cnj_list: list[str]) -> pd.DataFrame:
        """Parseia os HTMLs de :meth:`cpopg_download` em DataFrame, uma linha por processo.

        Delega a :meth:`juscraper.courts._trf.base.TRFConsultaScraper.cpopg_parse`,
        o parser da família PJe; não faz requisição.

        Args:
            htmls (list[str | None]): HTMLs do detalhe, como
                :meth:`cpopg_download` devolve.
            id_cnj_list (list[str]): CNJs na mesma ordem de ``htmls``.

        Returns:
            Uma linha por CNJ, com as colunas do detalhe de :meth:`cpopg`,
                exceto ``motivo_falha``: um ``None`` de :meth:`cpopg_download`
                pode ser processo ausente ou requisição que falhou, e só
                :meth:`cpopg` sabe qual. A linha de um ``None`` traz só
                ``id_cnj``; um HTML que o parser recusa também, com
                ``UserWarning``, e o lote continua.

        Raises:
            ValueError: ``htmls`` e ``id_cnj_list`` com tamanhos diferentes.
        """
        return self._consulta().cpopg_parse(htmls, id_cnj_list)

    def cpopg(
        self,
        id_cnj: str | list[str],
        download_pecas: bool = False,
        diretorio: str | None = None,
        **kwargs,
    ) -> pd.DataFrame:
        """Consulta processos de 1º grau na consulta pública do PJe do TJPE.

        Delega a :class:`TJPEConsultaPublicaScraper`, que reaproveita o fluxo
        dos TRFs (:meth:`juscraper.courts._trf.base.TRFConsultaScraper.cpopg`).
        Processo sob segredo de justiça não aparece na consulta pública e sai
        como linha só com ``id_cnj`` preenchido, igual a processo inexistente.

        O site fica atrás de um AWS WAF que desafia de forma intermitente.
        Quando o desafio aparece, o cookie ``aws-waf-token`` é obtido com o
        Playwright (extra ``juscraper[waf]``, seguido de
        ``playwright install chromium``); sem desafio, nada disso é preciso.

        Args:
            id_cnj (str | list[str]): CNJ único ou lista, com ou sem máscara.
            download_pecas (bool): Se ``True``, baixa também as peças públicas
                (HTML do visualizador do PJe). Default ``False``.
            diretorio (str | None): Onde gravar as peças, em
                ``<diretorio>/<cnj>/<id>.html``. Default ``None`` (diretório
                temporário).

        Returns:
            Uma linha por CNJ. Colunas: ``id_cnj``, ``processo``,
                ``classe``, ``assunto``, ``data_distribuicao``,
                ``orgao_julgador``, ``jurisdicao``, ``endereco_orgao``,
                ``polo_ativo``, ``polo_passivo``, ``movimentacoes``,
                ``documentos`` e ``motivo_falha``; com ``download_pecas=True``,
                também ``pecas`` e ``pecas_falhas``. ``motivo_falha`` e
                ``pecas_falhas`` seguem a regra de
                :meth:`juscraper.courts._trf.base.TRFConsultaScraper.cpopg`.
                Quando o WAF desafia de novo logo após a renovação do cookie,
                ou o cookie não pôde ser obtido (Chromium do Playwright
                ausente, cookie não emitido no prazo), o lote para ali: as
                linhas anteriores são preservadas, e a bloqueada e as seguintes
                saem com ``motivo_falha`` igual a ``bloqueio_anti_bot``, com um
                :class:`~juscraper.core.exceptions.BloqueioAntiBotWarning`
                (subclasse de ``UserWarning``). Com ``download_pecas=True``, as
                peças de cada processo vêm logo depois do seu detalhe, e os
                processos anteriores ao bloqueio ficam com as peças.

        Raises:
            TypeError: Kwarg desconhecido.
            ImportError: O WAF desafiou e o Playwright não está instalado,
                inclusive durante o download das peças.

        Examples: Exemplo
            >>> import juscraper as jus
            >>> tjpe = jus.scraper("tjpe")
            >>> df = tjpe.cpopg("0000000-00.0000.8.17.0000")

        See also:
            :class:`InputCpopgTRF` — schema pydantic e a fonte da verdade dos
            parâmetros aceitos.
        """
        return self._consulta().cpopg(
            id_cnj, download_pecas=download_pecas, diretorio=diretorio, **kwargs
        )

    def cposg(self, id_cnj: str | list[str]):
        """Stub: second instance case consultation not implemented for TJPE."""
        raise NotImplementedError("Consulta de processos de 2 grau não implementada para TJPE.")

    def cjsg_download(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        data_julgamento_inicio: str | date | None = None,
        data_julgamento_fim: str | date | None = None,
        relator: str | None = None,
        classe: str | None = None,
        assunto: str | None = None,
        meio_tramitacao: str | None = None,
        tipo_decisao: str = "acordaos",
        **kwargs,
    ) -> list:
        """Baixa as paginas brutas do cjsg do TJPE.

        Aceita os mesmos filtros de :meth:`cjsg`; veja la a lista completa,
        e levanta e avisa nos mesmos casos.

        Returns:
            Lista de strings HTML brutas, uma por pagina.
        """
        classe = resolve_deprecated_alias(kwargs, "classe_cnj", "classe", classe)
        assunto = resolve_deprecated_alias(kwargs, "assunto_cnj", "assunto", assunto)
        inp = apply_input_pipeline_search(
            InputCJSGTJPE,
            "TJPEScraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            relator=relator,
            classe=classe,
            assunto=assunto,
            meio_tramitacao=meio_tramitacao,
            tipo_decisao=tipo_decisao,
        )
        return cjsg_download(
            pesquisa=inp.pesquisa,
            paginas=inp.paginas,
            request_fn=self._request_with_retry,
            data_julgamento_inicio=inp.data_julgamento_inicio,
            data_julgamento_fim=inp.data_julgamento_fim,
            relator=inp.relator,
            classe=inp.classe,
            assunto=inp.assunto,
            meio_tramitacao=inp.meio_tramitacao,
            tipo_decisao=inp.tipo_decisao,
        )

    def cjsg_parse(self, raw_pages: list) -> pd.DataFrame:
        """Parseia as paginas brutas de :meth:`cjsg_download` em DataFrame."""
        return cjsg_parse(raw_pages)

    def cjsg(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        data_julgamento_inicio: str | date | None = None,
        data_julgamento_fim: str | date | None = None,
        relator: str | None = None,
        classe: str | None = None,
        assunto: str | None = None,
        meio_tramitacao: str | None = None,
        tipo_decisao: str = "acordaos",
        **kwargs,
    ) -> pd.DataFrame:
        """Busca jurisprudencia no TJPE.

        Wrapper trivial (``download → parse``) sobre :meth:`cjsg_download`.
        O backend e JSF/RichFaces: o fluxo carrega o ``ViewState`` da
        ``consulta.xhtml`` e propaga entre requests; a paginacao usa
        AJAX RichFaces em ``resultado.xhtml`` retornando XML envolto em
        ``<![CDATA[HTML]]>``.

        Args:
            pesquisa (str): Termo de busca livre (ementa). Aceita os aliases
                deprecados ``query`` / ``termo``.
            paginas (int | list | range | None): Paginas 1-based; ``None`` baixa
                todas. Default ``None``.
            data_julgamento_inicio (str | date): Data inicial de julgamento
                (``DD/MM/AAAA``, ``DD-MM-AAAA``, ``AAAA-MM-DD``, ``AAAA/MM/DD``,
                :class:`datetime.date` ou :class:`datetime.datetime`).
            data_julgamento_fim (str | date): Data final de julgamento (mesmos
                formatos de ``data_julgamento_inicio``).
            relator (str): Nome do relator (deve bater exatamente com o valor
                do dropdown do formulario).
            classe (str): Codigo CNJ da classe. Aceita o alias deprecado
                ``classe_cnj``.
            assunto (str): Codigo CNJ do assunto. Aceita o alias deprecado
                ``assunto_cnj``.
            meio_tramitacao (str): Filtro de meio de tramitacao
                (ex.: ``"ELETRONICO"``).
            tipo_decisao (str): ``"acordaos"`` (default), ``"monocraticas"`` ou
                ``"todos"``. Quando ``"todos"``, o backend marca os dois
                checkboxes e o fluxo passa pela pagina de escolha
                (``escolhaResultado.xhtml``), que traz os acórdãos; se a
                busca não tiver acórdão, traz as decisões monocráticas.

        Todos os filtros do schema :class:`InputCJSGTJPE` estao listados
        acima como parametros nomeados. O ``**kwargs`` so e exposto para
        absorver aliases deprecados (listados abaixo) e qualquer kwarg
        desconhecido vira ``TypeError`` via ``raise_on_extra_kwargs``.

        Aliases deprecados (popados com ``DeprecationWarning`` antes do pydantic):
            * ``query`` / ``termo`` -> ``pesquisa``
            * ``classe_cnj`` -> ``classe``
            * ``assunto_cnj`` -> ``assunto``
            * ``data_inicio`` / ``data_fim`` -> ``data_julgamento_inicio`` / ``_fim``
            * ``data_julgamento_de`` / ``_ate`` -> ``data_julgamento_inicio`` / ``_fim``

        Raises:
            TypeError: Quando um kwarg desconhecido e passado.
            ValueError: Quando um canonico e seu alias deprecado sao passados
                simultaneamente.
            ValidationError: Quando um filtro tem formato invalido (ex.: data
                fora dos formatos aceitos, ``tipo_decisao`` fora do enum).
            ValueError: Quando a busca devolve uma pagina fora dos formatos
                conhecidos (nem resultados, nem escolha do tipo, nem "Nenhum
                documento encontrado").

        Avisos:
            ``UserWarning``: Quando o portal responde "Nenhum documento
                encontrado"; o resultado sai vazio. Com a pesquisa fora do ar,
                o portal responde assim a qualquer termo.

        Returns:
            Uma linha por decisao. Colunas canonicas:
                ``processo``, ``classe``, ``assunto``, ``relator``,
                ``orgao_julgador``, ``data_julgamento``, ``data_publicacao``,
                ``ementa``, ``acordao``, ``decisao``, ``meio_tramitacao``,
                ``url_inteiro_teor``. As decisões monocráticas não têm
                ementa no portal e saem com ``ementa`` ``None``; o texto
                delas sai em ``decisao``, coluna que só existe quando a
                busca traz monocráticas (nos acórdãos, o texto sai em
                ``acordao``). O portal não publica ``orgao_julgador`` nem
                ``data_julgamento`` das monocráticas.

        Examples: Exemplo
            >>> import juscraper as jus
            >>> tjpe = jus.scraper("tjpe")
            >>> df = tjpe.cjsg("dano moral", paginas=range(1, 3),
            ...                tipo_decisao="acordaos")

        See also:
            :class:`InputCJSGTJPE` — schema pydantic e a fonte da verdade dos
            filtros aceitos.
        """
        raw = self.cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            relator=relator,
            classe=classe,
            assunto=assunto,
            meio_tramitacao=meio_tramitacao,
            tipo_decisao=tipo_decisao,
            **kwargs,
        )
        return self.cjsg_parse(raw)
