"""Inteiro teor do acórdão pela movimentação do processo no cposg do eSAJ.

A rota direta do cjsg (``cjsg/getArquivo.do?cdAcordao=...``) pede login no
TJSP e reCAPTCHA no TJAC. Esta rota, a mesma de ``tjsp_baixar_acordaos_cposg``
no pacote R ``tjsp`` de jjesusfilho, funciona sem nenhum dos dois:

1. ``<cposg>/search.do`` com o número CNJ devolve a página do processo ou o
   modal de incidentes (apelação e embargos têm ``cdProcesso``
   próprio no TJSP);
2. as movimentações trazem links ``a.linkMovVincProc`` com ``cdDocumento``;
   no TJAC vêm na página do processo, no TJSP em
   ``carregarMovimentacoesAjax.do``, paginado por ``cursor``;
3. ``verificarAcessoMovimentacao.do`` devolve, em texto, a URL da pasta
   digital do documento, ou a janela de senha quando o documento é restrito;
4. a pasta traz ``"parametros":"..."``, com o tipo do documento
   (``deTipoDocDigital``), e ``pastadigital/getPDF.do?<parametros>`` devolve
   o PDF do documento inteiro.

O ``verificarAcessoMovimentacao.do`` do TJSP só libera documento que a sessão
já listou (probe 2026-10: o mesmo ``cdDocumento`` devolve uma página HTML em
vez da URL quando a página de movimentações que o contém não foi carregada).
Por isso as movimentações são carregadas antes de qualquer verificação.

O acórdão se escolhe pela ``data_julgamento`` do cjsg: é o primeiro documento
de tipo de acórdão com data de movimentação igual ou posterior a ela. A
movimentação sai no dia do julgamento ou depois (TJAC: julgado em 27/10,
movimentação de 28/10; TJSP: cjsg com 28/10, acórdão registrado em 30/10), e o
acórdão seguinte do mesmo processo (embargos) vem depois deste.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import unquote_plus

import pandas as pd
import requests
from bs4 import BeautifulSoup, Tag

from ...core.failures import (
    COLUNA_MOTIVO_FALHA,
    EXCECOES_DE_FALHA_POR_LINHA,
    MOTIVO_NAO_ENCONTRADO,
    MOTIVO_NAO_PDF,
    MOTIVO_RESPOSTA_INESPERADA,
    MOTIVO_SEM_ACORDAO,
    avisar_falhas,
    motivo_falha,
)
from ...utils import safe_path_component
from ...utils.cnj import clean_cnj, format_cnj
from ...utils.params import coerce_brazilian_date
from .base import EsajSearchScraper
from .download import _CHROME_HEADERS, _ESAJ_HEADERS

logger = logging.getLogger("juscraper._esaj.acordao")

COLUNA_CAMINHO_ACORDAO = "caminho_acordao"
"""Coluna que :meth:`EsajAcordaoScraper.baixar_acordaos` acrescenta."""

_SEM_INFORMACOES = "Não existem informações disponíveis"
_PARAMETROS_RE = re.compile(r'"parametros":"([^"]+)"')


class AcordaoIndisponivelError(Exception):
    """Base dos casos em que a rota responde, mas não entrega o acórdão.

    ``motivo`` é o valor que :meth:`EsajAcordaoScraper.baixar_acordaos`
    grava na coluna ``motivo_falha``.
    """

    motivo: ClassVar[str]

    def __init__(self, processo: str, mensagem: str) -> None:
        self.processo = processo
        super().__init__(f"Processo {processo}: {mensagem}")


class ProcessoNaoEncontradoError(AcordaoIndisponivelError):
    """A consulta pública de 2º grau não mostra o processo.

    O eSAJ responde igual para número inexistente e para processo em segredo
    de justiça, que não aparece na consulta pública; a mensagem cita os dois.
    """

    motivo = MOTIVO_NAO_ENCONTRADO


class AcordaoNaoEncontradoError(AcordaoIndisponivelError):
    """Nenhum documento acessível de tipo de acórdão a partir da data de julgamento."""

    motivo = MOTIVO_SEM_ACORDAO


class RespostaNaoPdfError(AcordaoIndisponivelError):
    """``getPDF.do`` respondeu com algo que não começa por ``%PDF``; nada é gravado."""

    motivo = MOTIVO_NAO_PDF


class RespostaInesperadaError(AcordaoIndisponivelError):
    """Página do cposg ou da pasta fora do formato conhecido.

    Inclui o ``verificarAcessoMovimentacao.do`` que não devolve URL nem pede
    senha. Pular esse documento levaria ao acórdão seguinte do processo, que
    não é o da linha do cjsg; por isso a busca para.
    """

    motivo = MOTIVO_RESPOSTA_INESPERADA


class _DocumentoRestritoError(Exception):
    """O ``verificarAcessoMovimentacao.do`` pediu a senha do processo."""


@dataclass(frozen=True)
class Movimentacao:
    """Movimentação com documento vinculado.

    ``ordem`` é a posição na listagem, que o eSAJ ordena da mais nova para a
    mais antiga; desempata movimentações do mesmo dia.
    """

    cd_processo: str
    data: date
    cd_documento: str
    descricao: str
    ordem: int


def parse_codigos_processo(html: str, processo: str) -> list[str] | None:
    """Códigos (``cdProcesso``) da resposta do ``search.do``.

    Returns:
        A lista de códigos quando a resposta é o modal de incidentes, caso em
        que cada código precisa do próprio ``show.do``; ``None`` nos demais
        casos, em que a resposta deve ser a página do único processo. A
        listagem de processos (``#listagemDeProcessos``) não apareceu na busca
        por número nas sondas e cai em :class:`RespostaInesperadaError`.

    Raises:
        ProcessoNaoEncontradoError: Quando a consulta diz que não há informações.
        ValueError: Código impróprio para URL e nome de arquivo (ver
            :func:`~juscraper.utils.safe_path_component`).
    """
    soup = BeautifulSoup(html, "html.parser")
    mensagem = soup.select_one("#mensagemRetorno")
    if mensagem is not None and _SEM_INFORMACOES in mensagem.get_text():
        raise ProcessoNaoEncontradoError(
            processo,
            "a consulta de 2º grau não o encontra. O número pode não existir no "
            "tribunal, ou o processo está em segredo de justiça, que o eSAJ não "
            "mostra na consulta pública.",
        )
    if soup.select_one("#modalIncidentes") is None:
        return None
    return [
        safe_path_component(entrada["value"], field="processo.codigo")
        for entrada in soup.select("input#processoSelecionado")
    ]


def parse_cd_processo(html: str) -> str | None:
    """``cdProcesso`` da página de um processo, ou ``None`` quando ela não o traz."""
    entrada = BeautifulSoup(html, "html.parser").find("input", {"name": "cdProcesso"})
    valor = entrada.get("value") if entrada is not None else None
    return safe_path_component(valor, field="cdProcesso") if valor else None


def _linhas_movimentacao(html: str) -> list[Tag]:
    """Linhas de movimentação da página do processo ou do fragmento AJAX.

    A página do processo do TJAC repete as últimas movimentações em
    ``#tabelaUltimasMovimentacoes``; só ``#tabelaTodasMovimentacoes`` entra.
    O fragmento do ``carregarMovimentacoesAjax.do`` não tem nenhuma das duas.
    """
    soup = BeautifulSoup(html, "html.parser")
    raiz = soup.select_one("#tabelaTodasMovimentacoes") or soup
    return list(raiz.select("tr.movimentacaoProcesso"))


def _data_da_linha(linha: Tag) -> date:
    celula = linha.select_one("td.dataMovimentacaoProcesso") or linha.find("td")
    if celula is None:
        raise ValueError("Linha de movimentação sem célula de data.")
    return _data_br(celula.get_text(strip=True))


def parse_datas(html: str) -> list[date]:
    """Datas de todas as movimentações, com ou sem documento, na ordem da página."""
    return [_data_da_linha(linha) for linha in _linhas_movimentacao(html)]


def parse_movimentacoes(html: str, cd_processo: str, *, inicio: int = 0) -> list[Movimentacao]:
    """Movimentações com documento; ``inicio`` desloca ``ordem`` nas páginas seguintes."""
    movimentacoes = []
    for ordem, linha in enumerate(_linhas_movimentacao(html), start=inicio):
        # O TJSP põe o mesmo link no ícone e na descrição; a descrição basta.
        link = linha.select_one("td.descricaoMovimentacaoProcesso a.linkMovVincProc")
        if link is None:
            continue
        movimentacoes.append(
            Movimentacao(
                cd_processo=cd_processo,
                data=_data_da_linha(linha),
                cd_documento=safe_path_component(link.get("cddocumento"), field="cdDocumento"),
                descricao=link.get_text(" ", strip=True),
                ordem=ordem,
            )
        )
    return movimentacoes


def parse_cursor(html: str) -> str | None:
    """Cursor da próxima página de movimentações do TJSP, ou ``None`` na última.

    A primeira página traz o cursor no link "Mais"; as seguintes, numa linha
    oculta ``#metaPaginaMovimentacoes`` que diz se há mais páginas.
    """
    soup = BeautifulSoup(html, "html.parser")
    meta = soup.select_one("#metaPaginaMovimentacoes")
    if meta is not None:
        if meta.get("data-tem-mais-paginas") != "true":
            return None
        return str(meta.get("data-cursor") or "") or None
    link = soup.select_one("#linkMaisRecolherMovimentacoes")
    return str(link.get("data-cursor") or "") or None if link is not None else None


def parse_parametros_pasta(html: str) -> str | None:
    """Query string que ``getPDF.do`` espera, tirada da página da pasta digital.

    A pasta lista uma entrada por página do documento, todas com os mesmos
    ``parametros``; ``getPDF.do`` devolve o documento inteiro com qualquer uma.
    """
    encontrado = _PARAMETROS_RE.search(html)
    return encontrado.group(1) if encontrado else None


def tipo_documento(parametros: str) -> str:
    """``deTipoDocDigital`` dos ``parametros``, que o eSAJ codifica em latin-1."""
    for par in parametros.split("&"):
        chave, _, valor = par.partition("=")
        if chave == "deTipoDocDigital":
            return unquote_plus(valor, encoding="latin-1")
    return ""


def _data_br(texto: str) -> date:
    """``date`` de ``DD/MM/AAAA``, sem passar por ``datetime`` ingênuo."""
    dia, mes, ano = texto.strip().split("/")
    return date(int(ano), int(mes), int(dia))


def _como_data(valor: str | date) -> date:
    """``data_julgamento`` do usuário nos formatos de :func:`coerce_brazilian_date`."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    convertida = coerce_brazilian_date(valor, "%d/%m/%Y")
    if not isinstance(convertida, str) or not re.fullmatch(r"\d{2}/\d{2}/\d{4}", convertida):
        raise ValueError(f"data_julgamento inválida: {valor!r}. Use DD/MM/AAAA ou date.")
    return _data_br(convertida)


class EsajAcordaoScraper(EsajSearchScraper):
    """Base eSAJ que baixa o PDF do acórdão a partir de linhas do cjsg; ver o docstring do módulo.

    Atributos que o tribunal define:
        CPOSG_PATH: Caminho da consulta de 2º grau, relativo a ``BASE_URL``
            (``"cposg5/"`` no TJAC, onde ``cposg/`` responde 503).
        MOVIMENTACOES_AJAX: ``True`` quando as movimentações vêm de
            ``carregarMovimentacoesAjax.do`` (TJSP) e não da página do processo.
        TIPOS_DOCUMENTO_ACORDAO: Valores de ``deTipoDocDigital`` aceitos como
            acórdão. O TJAC tipa o acórdão de embargos como "Embargos de
            Declaração" (probe 2026-10, processo 0700021-98.2018.8.01.0001).
    """

    CPOSG_PATH: ClassVar[str]
    MOVIMENTACOES_AJAX: ClassVar[bool] = False
    TIPOS_DOCUMENTO_ACORDAO: ClassVar[frozenset[str]] = frozenset({"Acórdão"})

    def _get_cposg(self, url: str, **kwargs: Any) -> requests.Response:
        headers = _CHROME_HEADERS if self.CJSG_CHROME_UA else _ESAJ_HEADERS
        resposta: requests.Response = self._request_with_retry("GET", url, headers=headers, timeout=60, **kwargs)
        return resposta

    def baixar_acordao(self, processo: str, data_julgamento: str | date, diretorio: str | None = None) -> str:
        """Baixa o PDF do acórdão de uma linha do cjsg pela movimentação do processo.

        Sem login e sem captcha. Devolve o PDF como o tribunal o publica; a
        extração de texto fica com quem usa a biblioteca.

        Args:
            processo (str): Número CNJ, como na coluna ``processo`` do cjsg.
            data_julgamento (str | date): ``DD/MM/AAAA`` ou ``date``, como na
                coluna ``data_julgamento`` do cjsg. Escolhe o acórdão quando o
                processo tem mais de um: vale o primeiro documento de acórdão
                com data de movimentação igual ou posterior a ela.
            diretorio (str | None): Pasta de destino. Default
                :attr:`download_path`. O PDF vai para
                ``<diretorio>/acordaos/<cnj>_<cdProcesso>_<cdDocumento>.pdf``.

        Raises:
            ProcessoNaoEncontradoError: Número inexistente ou processo em
                segredo de justiça (o eSAJ não distingue os dois).
            AcordaoNaoEncontradoError: Nenhum documento de acórdão acessível a
                partir de ``data_julgamento``.
            RespostaNaoPdfError: ``getPDF.do`` respondeu sem ``%PDF``.
            RespostaInesperadaError: Página do cposg ou da pasta fora do formato
                conhecido; a busca para em vez de cair no acórdão seguinte.

        Returns:
            str: Caminho do PDF gravado.

        Examples: Exemplo
            >>> import juscraper as jus
            >>> tjsp = jus.scraper("tjsp")
            >>> caminho = tjsp.baixar_acordao("1001667-32.2025.8.26.0356", "13/10/2026")
        """
        data = _como_data(data_julgamento)
        cnj = format_cnj(str(processo))
        paginas = self._abrir_processo(cnj)
        movimentacoes = [m for cd, html in paginas for m in self._carregar_movimentacoes(cd, html, data)]
        candidatas = sorted(
            (m for m in movimentacoes if m.data >= data),
            key=lambda m: (m.data, -m.ordem),
        )
        restritos = 0
        for mov in candidatas:
            url_pasta = self._url_da_pasta(cnj, mov)
            if url_pasta is None:
                restritos += 1
                continue
            parametros = parse_parametros_pasta(self._get_cposg(url_pasta).text)
            if parametros is None:
                raise RespostaInesperadaError(
                    cnj, f"a pasta digital do documento {mov.cd_documento} não traz 'parametros'."
                )
            tipo = tipo_documento(parametros)
            if tipo not in self.TIPOS_DOCUMENTO_ACORDAO:
                logger.debug("%s: documento %s é %r, não acórdão.", cnj, mov.cd_documento, tipo)
                continue
            return self._gravar_pdf(cnj, mov, parametros, diretorio)
        mensagem = (
            f"nenhum documento de acórdão acessível nas movimentações a partir de "
            f"{data:%d/%m/%Y} ({len(candidatas)} documento(s) olhado(s))."
        )
        if restritos:
            mensagem += (
                f" {restritos} pede(m) a senha do processo, exigida em segredo de "
                "justiça e em peças restritas; o acórdão pode estar entre eles."
            )
        raise AcordaoNaoEncontradoError(cnj, mensagem)

    def baixar_acordaos(self, cjsg: pd.DataFrame, diretorio: str | None = None) -> pd.DataFrame:
        """Baixa o PDF do acórdão de cada linha do cjsg; ver :meth:`baixar_acordao`.

        Args:
            cjsg (pd.DataFrame): Saída de ``cjsg``, ou qualquer tabela com as
                colunas ``processo`` e ``data_julgamento``.
            diretorio (str | None): Pasta de destino. Default :attr:`download_path`.

        Returns:
            pd.DataFrame: As linhas de entrada com ``caminho_acordao`` (``None``
            quando falhou) e ``motivo_falha``. O motivo é ``nao_encontrado``,
            ``sem_acordao``, ``nao_pdf``, ``resposta_inesperada`` ou um motivo de rede de
            :data:`~juscraper.core.failures.MOTIVOS_FALHA`; as falhas saem
            também num único ``UserWarning`` ao fim.
        """
        faltando = {"processo", "data_julgamento"} - set(cjsg.columns)
        if faltando:
            raise ValueError(f"cjsg sem as colunas {sorted(faltando)}.")
        caminhos: list[str | None] = []
        motivos: list[str | None] = []
        falhas: list[str] = []
        for i, linha in enumerate(cjsg.itertuples(index=False)):
            if i and self.sleep_time:
                time.sleep(self.sleep_time)
            try:
                caminho, motivo = self.baixar_acordao(linha.processo, linha.data_julgamento, diretorio), None
            except AcordaoIndisponivelError as erro:
                caminho, motivo = None, erro.motivo
                logger.info("%s", erro)
            except EXCECOES_DE_FALHA_POR_LINHA as erro:
                caminho, motivo = None, motivo_falha(erro)
                logger.info("%s: %s", linha.processo, erro)
            if motivo is not None:
                falhas.append(f"{linha.processo}: {motivo}")
            caminhos.append(caminho)
            motivos.append(motivo)
        avisar_falhas(falhas, f"{type(self).__name__}.baixar_acordaos", "download(s) de acórdão")
        return cjsg.assign(**{COLUNA_CAMINHO_ACORDAO: caminhos, COLUNA_MOTIVO_FALHA: motivos})

    def _abrir_processo(self, cnj: str) -> list[tuple[str, str]]:
        """``(cdProcesso, html da página)`` de cada processo que a busca devolve."""
        digitos = clean_cnj(cnj)
        resposta = self._get_cposg(
            f"{self.BASE_URL}{self.CPOSG_PATH}search.do",
            params={
                "conversationId": "",
                "paginaConsulta": "1",
                "localPesquisa.cdLocal": "-1",
                "cbPesquisa": "NUMPROC",
                "tipoNuProcesso": "UNIFICADO",
                "numeroDigitoAnoUnificado": cnj[:15],
                "foroNumeroUnificado": digitos[-4:],
                "dePesquisaNuUnificado": cnj,
                "dePesquisa": "",
                "uuidCaptcha": "",
                "pbEnviar": "Pesquisar",
            },
        )
        codigos = parse_codigos_processo(resposta.text, cnj)
        if codigos is None:
            cd_processo = parse_cd_processo(resposta.text)
            if cd_processo is None:
                raise RespostaInesperadaError(cnj, "a busca do cposg não devolveu processo, listagem nem mensagem.")
            return [(cd_processo, resposta.text)]
        return [
            (cd, self._get_cposg(f"{self.BASE_URL}{self.CPOSG_PATH}show.do", params={"processo.codigo": cd}).text)
            for cd in codigos
        ]

    def _carregar_movimentacoes(self, cd_processo: str, html_processo: str, desde: date) -> list[Movimentacao]:
        """Movimentações com documento; no TJSP, pagina até passar de ``desde``.

        A listagem vem da mais nova para a mais antiga: quando uma página
        termina antes de ``desde``, as seguintes não têm candidato.
        """
        if not self.MOVIMENTACOES_AJAX:
            return parse_movimentacoes(html_processo, cd_processo)
        movimentacoes: list[Movimentacao] = []
        cursor: str | None = None
        linhas = 0
        while True:
            params = {"cdProcesso": cd_processo, **({"cursor": cursor} if cursor else {})}
            html = self._get_cposg(f"{self.BASE_URL}{self.CPOSG_PATH}carregarMovimentacoesAjax.do", params=params).text
            movimentacoes += parse_movimentacoes(html, cd_processo, inicio=linhas)
            datas = parse_datas(html)
            linhas += len(datas)
            cursor = parse_cursor(html)
            if cursor is None or (datas and min(datas) < desde):
                return movimentacoes

    def _url_da_pasta(self, cnj: str, mov: Movimentacao) -> str | None:
        """URL da pasta digital do documento, ou ``None`` quando ele não abre sem senha."""

        def _senha(resposta: requests.Response) -> None:
            # O 403 da janela de senha é resposta da aplicação, não do WAF:
            # repetir só atrasaria. Ver RETRYABLE_STATUSES em core/http.py.
            if resposta.status_code == 403 and "senhaProcesso" in resposta.text:
                raise _DocumentoRestritoError

        try:
            resposta = self._get_cposg(
                f"{self.BASE_URL}{self.CPOSG_PATH}verificarAcessoMovimentacao.do",
                params={
                    "cdDocumento": mov.cd_documento,
                    "origemRecurso": "M",
                    "cdProcesso": mov.cd_processo,
                    "conversationId": "",
                },
                on_response=_senha,
            )
        except _DocumentoRestritoError:
            return None
        texto = resposta.text.strip()
        # A URL volta do servidor; só segue a que aponta para a pasta do próprio tribunal.
        if not texto.startswith(f"{self.BASE_URL}pastadigital/"):
            raise RespostaInesperadaError(
                cnj,
                f"verificarAcessoMovimentacao.do do documento {mov.cd_documento} não devolveu a URL da "
                f"pasta digital nem pediu senha; começa por {texto[:60]!r}.",
            )
        return texto

    def _gravar_pdf(self, cnj: str, mov: Movimentacao, parametros: str, diretorio: str | None) -> str:
        resposta = self._get_cposg(f"{self.BASE_URL}pastadigital/getPDF.do?{parametros}")
        if not resposta.content.startswith(b"%PDF"):
            inicio = resposta.content[:60].decode("utf-8", "replace")
            raise RespostaNaoPdfError(
                cnj,
                f"getPDF.do do documento {mov.cd_documento} respondeu "
                f"{resposta.headers.get('Content-Type')!r} começando por {inicio!r}; nada foi gravado.",
            )
        pasta = Path(diretorio or self.download_path) / "acordaos"
        pasta.mkdir(parents=True, exist_ok=True)
        caminho = pasta / f"{clean_cnj(cnj)}_{mov.cd_processo}_{mov.cd_documento}.pdf"
        caminho.write_bytes(resposta.content)
        return str(caminho)
