"""PDF do acórdão pelo ``cd_acordao`` do cjsg do eSAJ, sem login nem captcha.

O link de inteiro teor da página do cjsg leva a
``cjsg/getArquivo.do?cdAcordao=...&cdForo=...``, e a linha do cjsg já traz os
dois códigos (``cd_acordao`` e ``cd_foro``). No TJMS (sonda de 2026-10-31) e
no TJCE (sonda de 2026-11-15), essa URL devolve o PDF direto, numa sessão
nova: um pedido por acórdão. Como o código é do próprio acórdão, não há
escolha entre os acórdãos do processo.

A mesma URL devolve a página de reCAPTCHA no TJAC, TJAL e TJAM e pede login
no TJSP; o TJAC e o TJSP baixam o acórdão pela movimentação do processo, em
:mod:`.acordao`. Por isso a resposta só é gravada quando começa por ``%PDF``.
"""

from __future__ import annotations

import logging
import re
from functools import partial
from pathlib import Path

import pandas as pd

from ...core.lote import DownloadEmLote, baixar_em_lote
from .acordao import COLUNA_CAMINHO_ACORDAO, EntradaInvalidaError, codigo_da_linha
from .base import EsajSearchScraper
from .pasta import DocumentoIndisponivelError, DocumentoNaoPdfError, conteudo_pdf, gravar_pdf

logger = logging.getLogger("juscraper._esaj.acordao_cjsg")

_CODIGO = re.compile(r"[0-9]+")


_LOTE_ACORDAO_CJSG = DownloadEmLote(
    origem="cjsg",
    colunas=("cd_acordao", "cd_foro"),
    erros_com_motivo=(DocumentoIndisponivelError, EntradaInvalidaError),
    coluna_caminho=COLUNA_CAMINHO_ACORDAO,
    descricao="download(s) de acórdão",
    logger=logger,
    rotulo=lambda linha: str(getattr(linha, "processo", None) or linha.cd_acordao),
)


class EsajAcordaoCjsgScraper(EsajSearchScraper):
    """Base eSAJ que baixa o PDF do acórdão pelo ``cd_acordao`` do cjsg; ver o docstring do módulo."""

    def baixar_acordao(self, cd_acordao: str | float, cd_foro: str | float, diretorio: str | None = None) -> str:
        """Baixa o PDF do inteiro teor do acórdão de uma linha do cjsg.

        Um pedido por acórdão, sem login e sem captcha. Devolve o PDF como o
        tribunal o publica; a extração de texto fica com quem usa a biblioteca.

        Args:
            cd_acordao: Coluna ``cd_acordao`` do cjsg; o ``float``
                inteiro da coluna lida de CSV também vale.
            cd_foro: Coluna ``cd_foro`` do cjsg, também como
                ``float`` inteiro.
            diretorio: Pasta de destino. Default
                :attr:`download_path`. O PDF vai para
                ``<diretorio>/acordaos/<cd_acordao>.pdf``.

        Raises:
            EntradaInvalidaError: Código vazio ou que não é só dígitos. Herda
                de ``ValueError``.
            DocumentoNaoPdfError: ``getArquivo.do`` respondeu sem ``%PDF``
                (página "Arquivo não localizado", captcha ou login); nada é
                gravado.

        Returns:
            Caminho do PDF gravado.

        Examples: Exemplo
            >>> import juscraper as jus
            >>> tjms = jus.scraper("tjms")
            >>> df = tjms.cjsg("dano moral", paginas=1)
            >>> caminho = tjms.baixar_acordao(df.cd_acordao[0], df.cd_foro[0])
        """
        acordao = codigo_da_linha("cd_acordao", cd_acordao, _CODIGO, "cjsg")
        foro = codigo_da_linha("cd_foro", cd_foro, _CODIGO, "cjsg")
        resposta = self._get_espacado(
            f"{self.BASE_URL}cjsg/getArquivo.do", params={"cdAcordao": acordao, "cdForo": foro}
        )
        conteudo = conteudo_pdf(resposta, "getArquivo.do", partial(DocumentoNaoPdfError, acordao))
        destino = Path(diretorio or self.download_path) / "acordaos" / f"{acordao}.pdf"
        return str(gravar_pdf(conteudo, destino))

    def baixar_acordaos(self, cjsg: pd.DataFrame, diretorio: str | None = None) -> pd.DataFrame:
        """Baixa o PDF do acórdão de cada linha do cjsg; ver :meth:`baixar_acordao`.

        Args:
            cjsg: Saída de ``cjsg``, ou qualquer tabela com as
                colunas ``cd_acordao`` e ``cd_foro``.
            diretorio: Pasta de destino. Default :attr:`download_path`.

        Returns:
            As linhas de entrada com ``caminho_acordao`` (``None`` quando
                falhou) e ``motivo_falha``. O motivo é ``entrada_invalida``,
                ``nao_pdf`` ou um motivo de rede de
                :data:`~juscraper.core.failures.MOTIVOS_FALHA`; as falhas saem
                também num único ``UserWarning`` ao fim. O primeiro
                ``bloqueio_anti_bot`` encerra o lote: as linhas seguintes saem
                com o mesmo motivo, sem pedido ao tribunal. O mesmo vale para
                o ``erro_de_gravacao``, do PDF que chegou e não pôde ser
                gravado (disco cheio, pasta sem permissão).
        """
        return baixar_em_lote(
            cjsg,
            lambda linha: self.baixar_acordao(linha.cd_acordao, linha.cd_foro, diretorio),
            _LOTE_ACORDAO_CJSG,
            f"{type(self).__name__}.baixar_acordaos",
        )
