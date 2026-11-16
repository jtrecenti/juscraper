"""Raspador do Tribunal Superior Eleitoral (TSE)."""

from __future__ import annotations

import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar, NoReturn

import pandas as pd

from juscraper.core.download import gravar_arquivo
from juscraper.core.http import HTTPScraper, RequestPolicy

from .download import (
    CATALOGO_BODY,
    INTERVALO_INTEIRO_TEOR,
    catalogo_url,
    inteiro_teor_url,
    normalizar_codigo_decisao,
    pdf_da_resposta,
)
from .parse import COLUNAS_CLASSES, COLUNAS_NORMAS, parse_lista, parse_registros


class TSEScraper(HTTPScraper):
    """Raspador do Tribunal Superior Eleitoral.

    Cobre o que o portal de jurisprudência entrega sem captcha: o PDF do
    inteiro teor pelo código da decisão e os catálogos do formulário (classes,
    relatores, eleições e normas). A busca de jurisprudência exige um token de
    captcha validado no servidor, que requisições HTTP puras não têm como
    gerar, e não está implementada; ver :meth:`cjsg`.

    Args:
        sleep_time: Segundos entre dois pedidos de inteiro teor (default 10).
            O serviço recusa pedidos mais próximos com "Excesso de requisições".
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

    _ultimo_inteiro_teor: float | None = None

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
            "Estão disponíveis baixar_inteiro_teor() e os catálogos listar_*()."
        )

    def _catalogo(self, catalogo: str) -> object:
        resposta = self._request_with_retry("POST", catalogo_url(catalogo), json=CATALOGO_BODY, perfil="catalogo")
        return resposta.json()

    def listar_classes(self) -> pd.DataFrame:
        """Lista as classes processuais do formulário de jurisprudência do TSE.

        Returns:
            Colunas ``sigla_classe`` e ``descricao_classe``, como o portal as
                devolve. A mesma descrição aparece com mais de uma sigla
                (``RESPE`` e ``REspEl``, por exemplo).

        Examples: Exemplo
            >>> import juscraper as jus
            >>> tse = jus.scraper("tse")
            >>> classes = tse.listar_classes()
        """
        return parse_registros(self._catalogo("classes"), "classes", COLUNAS_CLASSES)

    def listar_relatores(self) -> pd.DataFrame:
        """Lista os relatores do formulário de jurisprudência do TSE.

        Returns:
            Coluna ``relator``, com o nome como o portal o devolve.
        """
        return parse_lista(self._catalogo("relatorias"), "relatorias", "relator")

    def listar_eleicoes(self) -> pd.DataFrame:
        """Lista as eleições do formulário de jurisprudência do TSE.

        Returns:
            Coluna ``eleicao``, com o ano em texto, como o portal o devolve.
        """
        return parse_lista(self._catalogo("eleicoes"), "eleicoes", "eleicao")

    def listar_normas(self) -> pd.DataFrame:
        """Lista as normas (legislação) do formulário de jurisprudência do TSE.

        Returns:
            Colunas ``sigla``, ``tipo``, ``numero``, ``ano`` e ``norma`` (a
                ementa ou o nome da norma), como o portal as devolve.
        """
        return parse_registros(self._catalogo("normas"), "normas", COLUNAS_NORMAS)

    def baixar_inteiro_teor(self, codigo_decisao: int | str, diretorio: str | None = None) -> str:
        """Baixa o PDF do inteiro teor de uma decisão do TSE.

        Um pedido por decisão, sem login e sem captcha. Devolve o PDF como o
        tribunal o publica; a extração de texto fica com quem usa a
        biblioteca. Pedidos seguidos na mesma instância guardam ``sleep_time``
        entre si.

        Args:
            codigo_decisao (int | str): Código da decisão no portal (o
                ``codigoDecisao`` da busca, que também aparece no fim do link
                de inteiro teor, ``.../rest/download/pdf/<codigo>``).
            diretorio (str | None): Pasta de destino. Default
                :attr:`download_path`. O PDF vai para
                ``<diretorio>/inteiro_teor/<codigo_decisao>.pdf``.

        Raises:
            ValueError: Código que não é inteiro nem texto só de dígitos,
                antes de qualquer pedido.
            LimiteDeRequisicoesError: O serviço recusou o pedido por excesso
                de requisições; nada é gravado. Herda de
                ``InteiroTeorIndisponivelError``.
            InteiroTeorIndisponivelError: O serviço respondeu sem PDF, como
                faz com código que não existe; nada é gravado. As duas
                exceções ficam em ``juscraper.courts.tse.download``.

        Returns:
            Caminho do PDF gravado.

        Examples: Exemplo
            >>> import juscraper as jus
            >>> tse = jus.scraper("tse")
            >>> caminho = tse.baixar_inteiro_teor(3522031)
        """
        codigo = normalizar_codigo_decisao(codigo_decisao)
        if self._ultimo_inteiro_teor is not None and self.sleep_time:
            espera = self.sleep_time - (time.monotonic() - self._ultimo_inteiro_teor)
            if espera > 0:
                time.sleep(espera)
        try:
            resposta = self._request_with_retry("GET", inteiro_teor_url(codigo), perfil="inteiro_teor")
        finally:
            self._ultimo_inteiro_teor = time.monotonic()
        destino = Path(diretorio or self.download_path) / "inteiro_teor" / f"{codigo}.pdf"
        return str(gravar_arquivo(pdf_da_resposta(resposta, codigo), destino))
