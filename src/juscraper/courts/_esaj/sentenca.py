"""PDF da sentença do cjpg do eSAJ, sem login, pela rota 3 de :mod:`.pasta`.

A linha do cjpg traz os quatro códigos do link "Visualizar Inteiro Teor"
(``cd_processo``, ``cd_foro``, ``nm_alias``, ``cd_documento``), e
``cjpg/obterArquivo.do`` com eles leva à pasta do documento sem depender da
busca: são dois pedidos por sentença (a pasta e o ``getPDF.do``), numa sessão
qualquer.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd

from ...core.lote import DownloadEmLote, baixar_em_lote
from .acordao import EntradaInvalidaError, codigo_da_linha
from .base import EsajSearchScraper
from .pasta import DocumentoIndisponivelError, gravar_pdf, pdf_pela_pasta

logger = logging.getLogger("juscraper._esaj.sentenca")

COLUNA_CAMINHO_SENTENCA = "caminho_sentenca"
"""Coluna que :meth:`EsajSentencaScraper.baixar_sentencas` acrescenta."""

COLUNAS_CODIGOS_SENTENCA = ("cd_processo", "cd_foro", "nm_alias", "cd_documento")
"""Colunas do cjpg que :meth:`EsajSentencaScraper.baixar_sentencas` lê, na ordem do atributo ``name``."""

# cdProcesso é alfanumérico (``3I0006RUY0000``); foro e documento, só dígitos;
# o alias é o nome da base (``PG5SJCADS``) e pode vir vazio.
_FORMATOS = {
    "cd_processo": re.compile(r"[0-9A-Z]+"),
    "cd_foro": re.compile(r"\d+"),
    "nm_alias": re.compile(r"[0-9A-Za-z_]*"),
    "cd_documento": re.compile(r"\d+"),
}


_LOTE_SENTENCA = DownloadEmLote(
    origem="cjpg",
    colunas=COLUNAS_CODIGOS_SENTENCA,
    erros_com_motivo=(DocumentoIndisponivelError, EntradaInvalidaError),
    coluna_caminho=COLUNA_CAMINHO_SENTENCA,
    descricao="download(s) de sentença",
    logger=logger,
    rotulo=lambda linha: f"{linha.cd_processo}/{linha.cd_documento}",
)


class EsajSentencaScraper(EsajSearchScraper):
    """Base eSAJ que baixa o PDF da sentença a partir de linhas do cjpg; ver o docstring do módulo."""

    def baixar_sentenca(
        self,
        cd_processo: str,
        cd_foro: str | float,
        cd_documento: str | float,
        nm_alias: str | float | None = None,
        diretorio: str | None = None,
    ) -> str:
        """Baixa o PDF da sentença de uma linha do cjpg.

        Sem login e sem captcha. Devolve o PDF como o tribunal o publica; a
        extração de texto fica com quem usa a biblioteca (o cjpg já traz o
        texto na coluna ``decisao``; o PDF guarda a formatação e as
        assinaturas).

        Args:
            cd_processo: Coluna ``cd_processo`` do cjpg.
            cd_foro: Coluna ``cd_foro`` do cjpg; o ``float``
                inteiro (``126.0``) da coluna lida de CSV também vale.
            cd_documento: Coluna ``cd_documento`` do cjpg,
                também como ``float`` inteiro.
            nm_alias: Coluna ``nm_alias`` do cjpg, que costuma
                vir vazia no TJSP (``NaN`` quando lida de CSV). Default ``None``.
            diretorio: Pasta de destino. Default
                :attr:`download_path`. O PDF vai para
                ``<diretorio>/sentencas/<cd_processo>_<cd_documento>.pdf``.

        Raises:
            EntradaInvalidaError: Código vazio ou fora do formato do eSAJ.
                Herda de ``ValueError``.
            PastaInesperadaError: A página da pasta não veio.
            DocumentoNaoPdfError: ``getPDF.do`` respondeu sem ``%PDF``.

        Returns:
            Caminho do PDF gravado.

        Examples: Exemplo
            >>> import juscraper as jus
            >>> tjsp = jus.scraper("tjsp")
            >>> df = tjsp.cjpg("atraso de voo", paginas=1)
            >>> linha = df.iloc[0]
            >>> caminho = tjsp.baixar_sentenca(linha.cd_processo, linha.cd_foro, linha.cd_documento, linha.nm_alias)
        """
        codigos = {
            campo: codigo_da_linha(campo, valor, _FORMATOS[campo], "cjpg")
            for campo, valor in zip(
                COLUNAS_CODIGOS_SENTENCA, (cd_processo, cd_foro, nm_alias, cd_documento), strict=True
            )
        }
        consulta = urlencode(
            {
                "cdProcesso": codigos["cd_processo"],
                "cdForo": codigos["cd_foro"],
                "nmAlias": codigos["nm_alias"],
                "cdDocumento": codigos["cd_documento"],
            }
        )
        conteudo = pdf_pela_pasta(
            self._get_espacado,
            f"{self.BASE_URL}cjpg/obterArquivo.do?{consulta}",
            self.BASE_URL,
            codigos["cd_documento"],
        )
        destino = (
            Path(diretorio or self.download_path)
            / "sentencas"
            / f"{codigos['cd_processo']}_{codigos['cd_documento']}.pdf"
        )
        return str(gravar_pdf(conteudo, destino))

    def baixar_sentencas(self, cjpg: pd.DataFrame, diretorio: str | None = None) -> pd.DataFrame:
        """Baixa o PDF da sentença de cada linha do cjpg; ver :meth:`baixar_sentenca`.

        Args:
            cjpg: Saída de ``cjpg``, ou qualquer tabela com as
                colunas ``cd_processo``, ``cd_foro``, ``nm_alias`` e
                ``cd_documento``.
            diretorio: Pasta de destino. Default :attr:`download_path`.

        Returns:
            As linhas de entrada com ``caminho_sentenca`` (``None``
                quando falhou) e ``motivo_falha``. O motivo é ``entrada_invalida``,
                ``nao_pdf``, ``resposta_inesperada`` ou um motivo de rede de
                :data:`~juscraper.core.failures.MOTIVOS_FALHA`; as falhas saem
                também num único ``UserWarning`` ao fim. O primeiro
                ``bloqueio_anti_bot`` encerra o lote: as linhas seguintes saem
                com o mesmo motivo, sem pedido ao tribunal. O mesmo vale para
                o ``erro_de_gravacao``, do PDF que chegou e não pôde ser
                gravado (disco cheio, pasta sem permissão).
        """
        return baixar_em_lote(
            cjpg,
            lambda linha: self.baixar_sentenca(
                linha.cd_processo, linha.cd_foro, linha.cd_documento, linha.nm_alias, diretorio
            ),
            _LOTE_SENTENCA,
            f"{type(self).__name__}.baixar_sentencas",
        )
