"""Scraper for the Tribunal de Justiça do Ceará (TJCE)."""
import logging
import re
from pathlib import Path

import pandas as pd
import requests

from ...core.failures import COLUNA_MOTIVO_FALHA, EXCECOES_DE_FALHA_POR_LINHA, avisar_falhas, motivo_falha
from .._esaj.acordao import COLUNA_CAMINHO_ACORDAO, EntradaInvalidaError, _ausente
from .._esaj.base import EsajSearchScraper
from .._esaj.pasta import DocumentoIndisponivelError, DocumentoNaoPdfError, gravar_pdf
from ._tls import _TJCETLSAdapter

logger = logging.getLogger("juscraper.tjce")

_TITULO = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def _codigo(campo: str, valor: object) -> str:
    """Código numérico da linha do cjsg; recusa o vazio e o que não é só dígitos.

    Aceita o ``float`` inteiro (``3834193.0``), que a coluna vira ao voltar de
    CSV ou parquet com alguma célula vazia.
    """
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    texto = "" if _ausente(valor) else str(valor).strip()
    if not re.fullmatch(r"[0-9]+", texto):
        raise EntradaInvalidaError(f"{campo} inválido: {valor!r}. Use o valor da coluna {campo} do cjsg.")
    return texto


class TJCEScraper(EsajSearchScraper):
    """TJCE usa o eSAJ com adaptador TLS (SECLEVEL=1).

    O inteiro teor do acórdão sai direto do ``cd_acordao`` do cjsg
    (``cjsg/getArquivo.do``), sem login e sem captcha (sonda de 2026-11). A
    mesma rota pede reCAPTCHA no TJAC, TJAL e TJAM e login no TJSP.
    """

    BASE_URL = "https://esaj.tjce.jus.br/"
    TRIBUNAL_NAME = "TJCE"

    def _configure_session(self, session: requests.Session) -> None:
        session.mount("https://", _TJCETLSAdapter())

    def baixar_acordao(self, cd_acordao: str, cd_foro: str, diretorio: str | None = None) -> str:
        """Baixa o PDF do inteiro teor do acórdão de uma linha do cjsg.

        Um pedido por acórdão, sem login e sem captcha. Devolve o PDF como o
        tribunal o publica; a extração de texto fica com quem usa a biblioteca.

        Args:
            cd_acordao (str): Coluna ``cd_acordao`` do cjsg.
            cd_foro (str): Coluna ``cd_foro`` do cjsg.
            diretorio (str | None): Pasta de destino. Default
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
            >>> tjce = jus.scraper("tjce")
            >>> df = tjce.cjsg("dano moral", paginas=1)
            >>> caminho = tjce.baixar_acordao(df.cd_acordao[0], df.cd_foro[0])
        """
        acordao = _codigo("cd_acordao", cd_acordao)
        foro = _codigo("cd_foro", cd_foro)
        resposta = self._get_espacado(
            f"{self.BASE_URL}cjsg/getArquivo.do", params={"cdAcordao": acordao, "cdForo": foro}
        )
        if not resposta.content.startswith(b"%PDF"):
            inicio = resposta.content[:4096].decode("utf-8", "replace")
            titulo = _TITULO.search(inicio)
            descricao = titulo.group(1).strip() if titulo else inicio[:60].strip()
            raise DocumentoNaoPdfError(
                acordao,
                f"getArquivo.do respondeu {resposta.headers.get('Content-Type')!r} ({descricao!r}); "
                "nada foi gravado.",
            )
        destino = Path(diretorio or self.download_path) / "acordaos" / f"{acordao}.pdf"
        return str(gravar_pdf(resposta.content, destino))

    def baixar_acordaos(self, cjsg: pd.DataFrame, diretorio: str | None = None) -> pd.DataFrame:
        """Baixa o PDF do acórdão de cada linha do cjsg; ver :meth:`baixar_acordao`.

        Args:
            cjsg (pd.DataFrame): Saída de ``cjsg``, ou qualquer tabela com as
                colunas ``cd_acordao`` e ``cd_foro``.
            diretorio (str | None): Pasta de destino. Default :attr:`download_path`.

        Returns:
            As linhas de entrada com ``caminho_acordao`` (``None`` quando
                falhou) e ``motivo_falha``. O motivo é ``entrada_invalida``,
                ``nao_pdf`` ou um motivo de rede de
                :data:`~juscraper.core.failures.MOTIVOS_FALHA`; as falhas saem
                também num único ``UserWarning`` ao fim.
        """
        faltando = {"cd_acordao", "cd_foro"} - set(cjsg.columns)
        if faltando:
            raise ValueError(f"cjsg sem as colunas {sorted(faltando)}.")
        caminhos: list[str | None] = []
        motivos: list[str | None] = []
        falhas: list[str] = []
        for linha in cjsg.itertuples(index=False):
            try:
                caminho, motivo = self.baixar_acordao(linha.cd_acordao, linha.cd_foro, diretorio), None
            except (DocumentoIndisponivelError, EntradaInvalidaError) as erro:
                caminho, motivo = None, erro.motivo
                logger.info("%s: %s", linha.cd_acordao, erro)
            except EXCECOES_DE_FALHA_POR_LINHA as erro:
                caminho, motivo = None, motivo_falha(erro)
                logger.info("%s: %s", linha.cd_acordao, erro)
            if motivo is not None:
                falhas.append(f"{getattr(linha, 'processo', None) or linha.cd_acordao}: {motivo}")
            caminhos.append(caminho)
            motivos.append(motivo)
        avisar_falhas(falhas, f"{type(self).__name__}.baixar_acordaos", "download(s) de acórdão")
        return cjsg.assign(**{COLUNA_CAMINHO_ACORDAO: caminhos, COLUNA_MOTIVO_FALHA: motivos})
