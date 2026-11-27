"""Raspador do Tribunal Superior Eleitoral (TSE)."""

from __future__ import annotations

import logging
import numbers
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, ClassVar, NoReturn

import pandas as pd

from juscraper.core.download import gravar_arquivo
from juscraper.core.failures import MOTIVO_LIMITE_DE_REQUISICOES
from juscraper.core.http import HTTPScraper, RequestPolicy
from juscraper.core.intervalo import IntervaloEntrePedidos
from juscraper.core.lote import DownloadEmLote, baixar_em_lote

from .download import (
    CATALOGO_BODY,
    INTERVALO_INTEIRO_TEOR,
    CodigoInvalidoError,
    InteiroTeorIndisponivelError,
    catalogo_url,
    inteiro_teor_url,
    normalizar_codigo_decisao,
    normalizar_tribunal,
    pdf_da_resposta,
)
from .parse import COLUNAS_CLASSES, COLUNAS_NORMAS, parse_lista, parse_registros

logger = logging.getLogger("juscraper.tse")

COLUNA_CODIGO_DECISAO = "codigo_decisao"
COLUNA_CAMINHO_INTEIRO_TEOR = "caminho_inteiro_teor"
"""Coluna do caminho do PDF em :meth:`TSEScraper.baixar_inteiros_teores`."""

# Recusas por excesso de requisições, uma depois da outra, que encerram o
# lote: insistir num serviço que está recusando só prolonga a recusa.
RECUSAS_SEGUIDAS = 2

_LOTE_INTEIRO_TEOR = DownloadEmLote(
    origem="codigos_decisao",
    colunas=(COLUNA_CODIGO_DECISAO,),
    erros_com_motivo=(InteiroTeorIndisponivelError, CodigoInvalidoError),
    coluna_caminho=COLUNA_CAMINHO_INTEIRO_TEOR,
    descricao="download(s) de inteiro teor",
    logger=logger,
    rotulo=lambda linha: str(linha.codigo_decisao),
    encerrar=lambda motivos: motivos[-RECUSAS_SEGUIDAS:] == [MOTIVO_LIMITE_DE_REQUISICOES] * RECUSAS_SEGUIDAS,
)


class TSEScraper(HTTPScraper):
    """Raspador do Tribunal Superior Eleitoral.

    Cobre o que o portal de jurisprudência entrega sem captcha: o PDF do
    inteiro teor pelo código da decisão, do TSE ou de um TRE, e os catálogos
    do formulário (classes, relatores, eleições e normas), do TSE e dos TREs.
    A busca de jurisprudência exige um token de captcha validado no servidor,
    que requisições HTTP puras não têm como gerar, e não está implementada;
    ver :meth:`cjsg`.

    Args:
        sleep_time: Segundos entre dois pedidos de inteiro teor (default 10).
            O serviço recusa pedidos mais próximos com "Excesso de requisições".
            O intervalo conta entre todas as instâncias do processo, porque o
            serviço não distingue uma da outra; cada pedido espera o
            ``sleep_time`` da instância que o faz.
        download_path: Pasta padrão dos PDFs. ``None`` usa um diretório temporário.
        verbose: Nível de detalhe do log.
        politica: Ajustes dos perfis HTTP ``catalogo`` e ``inteiro_teor``, por
            campo de :class:`~juscraper.core.http.RequestPolicy`.
    """

    perfis_http: ClassVar[Mapping[str, RequestPolicy]] = {
        "catalogo": RequestPolicy(timeout=60, expect_json=True),
        # Status retentável (429, 5xx) ganha uma nova tentativa só, depois do
        # intervalo que o serviço aceita: a 2 s, o backoff padrão, ela voltaria
        # recusada. A recusa por excesso de requisições vem em HTTP 200 e não
        # é retentada; ver ``pdf_da_resposta``.
        "inteiro_teor": RequestPolicy(timeout=120, max_retries=2, base_backoff=INTERVALO_INTEIRO_TEOR),
    }

    # Na classe: o serviço limita por cliente, e duas instâncias somam pedidos.
    _intervalo_inteiro_teor: ClassVar[IntervaloEntrePedidos] = IntervaloEntrePedidos()

    def __init__(
        self,
        *,
        sleep_time: float = INTERVALO_INTEIRO_TEOR,
        download_path: str | None = None,
        verbose: int = 0,
        politica: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> None:
        """Cria o raspador; os argumentos estão na docstring da classe."""
        super().__init__(
            "TSE", sleep_time=sleep_time, download_path=download_path, verbose=verbose, politica=politica
        )

    def cjsg(self, *args: object, **kwargs: object) -> NoReturn:
        """Stub: a busca de jurisprudência do TSE exige captcha e não está implementada."""
        raise NotImplementedError(
            "Busca de jurisprudência não implementada para o TSE: o portal exige um token de captcha, "
            "validado no servidor, e responde 'Falha na verificação antirrobô.' sem ele. "
            "Estão disponíveis baixar_inteiro_teor(), baixar_inteiros_teores() e os catálogos listar_*()."
        )

    def _catalogo(self, catalogo: str, tribunal: str) -> object:
        url = catalogo_url(catalogo, normalizar_tribunal(tribunal))
        return self._request_with_retry("POST", url, json=CATALOGO_BODY, perfil="catalogo").json()

    def listar_classes(self, tribunal: str = "tse") -> pd.DataFrame:
        """Lista as classes processuais do formulário de jurisprudência do TSE ou dos TREs.

        Args:
            tribunal: ``"tse"`` (default), um TRE (``"tre-sp"``) ou
                ``"tres"``, os 27 TREs juntos. Vale o mesmo nos demais
                ``listar_*``.

        Raises:
            ValueError: ``tribunal`` desconhecido, antes de qualquer pedido.

        Returns:
            Colunas ``sigla_classe`` e ``descricao_classe``, como o portal as
                devolve. A mesma descrição aparece com mais de uma sigla
                (``RESPE`` e ``REspEl``, por exemplo).

        Examples: Exemplo
            >>> import juscraper as jus
            >>> tse = jus.scraper("tse")
            >>> classes = tse.listar_classes()
            >>> classes_tre_sp = tse.listar_classes(tribunal="tre-sp")
        """
        return parse_registros(self._catalogo("classes", tribunal), "classes", COLUNAS_CLASSES)

    def listar_relatores(self, tribunal: str = "tse") -> pd.DataFrame:
        """Lista os relatores do formulário de jurisprudência do TSE ou dos TREs.

        Args:
            tribunal: Ver :meth:`listar_classes`.

        Returns:
            Coluna ``relator``, com o nome como o portal o devolve. Nos TREs
                a lista traz também textos que não são nomes, digitados no
                campo do relator.
        """
        return parse_lista(self._catalogo("relatorias", tribunal), "relatorias", "relator")

    def listar_eleicoes(self, tribunal: str = "tse") -> pd.DataFrame:
        """Lista as eleições do formulário de jurisprudência do TSE ou dos TREs.

        Args:
            tribunal: Ver :meth:`listar_classes`.

        Returns:
            Coluna ``eleicao``, com o ano em texto, como o portal o devolve.
        """
        return parse_lista(self._catalogo("eleicoes", tribunal), "eleicoes", "eleicao")

    def listar_normas(self, tribunal: str = "tse") -> pd.DataFrame:
        """Lista as normas (legislação) do formulário de jurisprudência do TSE ou dos TREs.

        Args:
            tribunal: Ver :meth:`listar_classes`.

        Returns:
            Colunas ``sigla``, ``tipo``, ``numero``, ``ano`` e ``norma`` (a
                ementa ou o nome da norma), como o portal as devolve.
        """
        return parse_registros(self._catalogo("normas", tribunal), "normas", COLUNAS_NORMAS)

    def baixar_inteiro_teor(self, codigo_decisao: int | str, diretorio: str | None = None) -> str:
        """Baixa o PDF do inteiro teor de uma decisão do TSE ou de um TRE.

        Um pedido por decisão, sem login e sem captcha. Devolve o PDF como o
        tribunal o publica; a extração de texto fica com quem usa a
        biblioteca. O serviço é o mesmo para o TSE e os TREs, e o código
        basta para achar a decisão. Pedidos seguidos guardam ``sleep_time``
        entre si, também entre instâncias diferentes do raspador no mesmo
        processo; processos diferentes não se enxergam.

        Args:
            codigo_decisao: Código da decisão no portal (o
                ``codigoDecisao`` da busca, que também aparece no fim do link
                de inteiro teor, ``.../rest/download/pdf/<codigo>``).
            diretorio: Pasta de destino. Default
                :attr:`download_path`. O PDF vai para
                ``<diretorio>/inteiro_teor/<codigo_decisao>.pdf``.

        Raises:
            CodigoInvalidoError: Código que não é inteiro nem texto só de
                dígitos, antes de qualquer pedido. Herda de ``ValueError``.
            LimiteDeRequisicoesError: O serviço recusou o pedido por excesso
                de requisições; nada é gravado. Herda de
                ``InteiroTeorIndisponivelError``.
            InteiroTeorIndisponivelError: O serviço respondeu sem PDF, como
                faz com código que não existe; nada é gravado. As três
                exceções ficam em ``juscraper.courts.tse.download``.

        Returns:
            Caminho do PDF gravado.

        Examples: Exemplo
            >>> import juscraper as jus
            >>> tse = jus.scraper("tse")
            >>> caminho = tse.baixar_inteiro_teor(3522031)
        """
        codigo = normalizar_codigo_decisao(codigo_decisao)
        with self._intervalo_inteiro_teor.pedido(self.sleep_time):
            resposta = self._request_with_retry("GET", inteiro_teor_url(codigo), perfil="inteiro_teor")
        destino = Path(diretorio or self.download_path) / "inteiro_teor" / f"{codigo}.pdf"
        return str(gravar_arquivo(pdf_da_resposta(resposta, codigo), destino))

    def baixar_inteiros_teores(
        self, codigos_decisao: Iterable[int | str], diretorio: str | None = None
    ) -> pd.DataFrame:
        """Baixa o PDF do inteiro teor de várias decisões, uma linha por código.

        Chama :meth:`baixar_inteiro_teor` para cada código, na ordem da
        entrada, com ``sleep_time`` entre os pedidos: são 10 s por decisão no
        default. A falha de uma decisão não interrompe o lote; duas recusas
        seguidas por excesso de requisições, sim, e as linhas seguintes saem
        ``limite_de_requisicoes`` sem pedido. O erro ao gravar um PDF também
        encerra o lote: a linha e as seguintes saem ``erro_de_gravacao``.

        Args:
            codigos_decisao: Códigos das decisões, como
                em :meth:`baixar_inteiro_teor`; uma lista ou a coluna de um
                DataFrame. Código repetido é baixado de novo.
            diretorio: Pasta de destino, como em
                :meth:`baixar_inteiro_teor`.

        Raises:
            TypeError: ``codigos_decisao`` é um código só (texto ou inteiro),
                e não uma coleção deles.

        Returns:
            Colunas ``codigo_decisao`` (como veio na entrada),
                ``caminho_inteiro_teor`` (``None`` na falha) e
                ``motivo_falha``: ``None`` no sucesso, ``nao_pdf`` (resposta
                sem PDF, como a de código que não existe),
                ``limite_de_requisicoes`` (o serviço recusou o pedido; basta
                pedir de novo as linhas que falharam), ``entrada_invalida``
                (código que não é inteiro nem texto só de dígitos, como a
                célula vazia; nada é pedido), ``erro_de_gravacao`` (o PDF
                chegou, mas não pôde ser gravado: disco cheio, pasta sem
                permissão) ou um motivo de rede de
                :data:`~juscraper.core.failures.MOTIVOS_FALHA`. As falhas
                saem também num único ``UserWarning`` ao fim.

        Examples: Exemplo
            >>> import juscraper as jus
            >>> tse = jus.scraper("tse")
            >>> baixados = tse.baixar_inteiros_teores([2972172, 3522031])
        """
        if isinstance(codigos_decisao, (str, bytes, numbers.Real)):
            raise TypeError(
                "codigos_decisao deve ser uma coleção de códigos; para um código só, use baixar_inteiro_teor()."
            )
        return baixar_em_lote(
            pd.DataFrame({COLUNA_CODIGO_DECISAO: pd.Series(list(codigos_decisao), dtype=object)}),
            lambda linha: self.baixar_inteiro_teor(linha.codigo_decisao, diretorio),
            _LOTE_INTEIRO_TEOR,
            "TSEScraper.baixar_inteiros_teores",
        )
