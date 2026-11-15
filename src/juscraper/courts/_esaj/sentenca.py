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

from ...core.failures import COLUNA_MOTIVO_FALHA, EXCECOES_DE_FALHA_POR_LINHA, avisar_falhas, motivo_falha
from .acordao import EntradaInvalidaError, _ausente
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


def _codigo(campo: str, valor: object) -> str:
    """Código da linha do cjpg, validado contra o formato que o eSAJ usa."""
    texto = "" if _ausente(valor) else str(valor).strip()
    if not _FORMATOS[campo].fullmatch(texto):
        raise EntradaInvalidaError(f"{campo} inválido: {valor!r}. Use o valor da coluna {campo} do cjpg.")
    return texto


class EsajSentencaScraper(EsajSearchScraper):
    """Base eSAJ que baixa o PDF da sentença a partir de linhas do cjpg; ver o docstring do módulo."""

    def baixar_sentenca(
        self,
        cd_processo: str,
        cd_foro: str,
        cd_documento: str,
        nm_alias: str | None = None,
        diretorio: str | None = None,
    ) -> str:
        """Baixa o PDF da sentença de uma linha do cjpg.

        Sem login e sem captcha. Devolve o PDF como o tribunal o publica; a
        extração de texto fica com quem usa a biblioteca (o cjpg já traz o
        texto na coluna ``decisao``; o PDF guarda a formatação e as
        assinaturas).

        Args:
            cd_processo (str): Coluna ``cd_processo`` do cjpg.
            cd_foro (str): Coluna ``cd_foro`` do cjpg.
            cd_documento (str): Coluna ``cd_documento`` do cjpg.
            nm_alias (str | None): Coluna ``nm_alias`` do cjpg, que costuma vir
                vazia no TJSP. Default ``None``.
            diretorio (str | None): Pasta de destino. Default
                :attr:`download_path`. O PDF vai para
                ``<diretorio>/sentencas/<cd_processo>_<cd_documento>.pdf``.

        Raises:
            EntradaInvalidaError: Código vazio ou fora do formato do eSAJ.
                Herda de ``ValueError``.
            PastaInesperadaError: A página da pasta não veio.
            DocumentoNaoPdfError: ``getPDF.do`` respondeu sem ``%PDF``.

        Returns:
            str: Caminho do PDF gravado.

        Examples: Exemplo
            >>> import juscraper as jus
            >>> tjsp = jus.scraper("tjsp")
            >>> df = tjsp.cjpg("atraso de voo", paginas=1)
            >>> linha = df.iloc[0]
            >>> caminho = tjsp.baixar_sentenca(linha.cd_processo, linha.cd_foro, linha.cd_documento, linha.nm_alias)
        """
        codigos = {
            campo: _codigo(campo, valor)
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
            cjpg (pd.DataFrame): Saída de ``cjpg``, ou qualquer tabela com as
                colunas ``cd_processo``, ``cd_foro``, ``nm_alias`` e
                ``cd_documento``.
            diretorio (str | None): Pasta de destino. Default :attr:`download_path`.

        Returns:
            pd.DataFrame: As linhas de entrada com ``caminho_sentenca`` (``None``
            quando falhou) e ``motivo_falha``. O motivo é ``entrada_invalida``,
            ``nao_pdf``, ``resposta_inesperada`` ou um motivo de rede de
            :data:`~juscraper.core.failures.MOTIVOS_FALHA`; as falhas saem
            também num único ``UserWarning`` ao fim.
        """
        faltando = set(COLUNAS_CODIGOS_SENTENCA) - set(cjpg.columns)
        if faltando:
            raise ValueError(f"cjpg sem as colunas {sorted(faltando)}.")
        caminhos: list[str | None] = []
        motivos: list[str | None] = []
        falhas: list[str] = []
        for linha in cjpg.itertuples(index=False):
            try:
                caminho = self.baixar_sentenca(
                    linha.cd_processo, linha.cd_foro, linha.cd_documento, linha.nm_alias, diretorio
                )
                motivo = None
            except (DocumentoIndisponivelError, EntradaInvalidaError) as erro:
                caminho, motivo = None, erro.motivo
                logger.info("%s: %s", linha.cd_processo, erro)
            except EXCECOES_DE_FALHA_POR_LINHA as erro:
                caminho, motivo = None, motivo_falha(erro)
                logger.info("%s: %s", linha.cd_processo, erro)
            if motivo is not None:
                falhas.append(f"{linha.cd_processo}/{linha.cd_documento}: {motivo}")
            caminhos.append(caminho)
            motivos.append(motivo)
        avisar_falhas(falhas, f"{type(self).__name__}.baixar_sentencas", "download(s) de sentença")
        return cjpg.assign(**{COLUNA_CAMINHO_SENTENCA: caminhos, COLUNA_MOTIVO_FALHA: motivos})
