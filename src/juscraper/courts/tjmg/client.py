"""Scraper for the Court of Justice of Minas Gerais (TJMG)."""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any, ClassVar, Literal

import pandas as pd
import requests
from pydantic import ValidationError

from juscraper.core.http import HTTPScraper, RequestPolicy
from juscraper.utils.cnj import clean_cnj
from juscraper.utils.params import apply_input_pipeline_search, raise_on_extra_kwargs, resolve_deprecated_alias

from .cposg_download import PERFIL_CPOSG
from .cposg_download import cposg_download as _cposg_download
from .cposg_parse import cposg_parse as _cposg_parse
from .cposg_parse import extract_partes_ids
from .download import PERFIL_CJSG
from .download import cjsg_download as _cjsg_download
from .parse import cjsg_parse as _cjsg_parse
from .schemas import InputCJSGTJMG, InputCPOSGTJMG


class TJMGScraper(HTTPScraper):
    """Scraper for the Court of Justice of Minas Gerais.

    The TJMG jurisprudence search uses a 5-digit numeric image captcha
    that is decoded with
    `txtcaptcha <https://github.com/jtrecenti/txtcaptcha>`_. Captcha
    validation is flagged once per session, so pagination reuses the
    same HTTP session after the first successful decoding.

    Os dois portais derrubam conexoes e travam respostas de forma
    intermitente (#440). Os perfis HTTP ``"cjsg"`` e ``"cposg"`` repetem a
    requisicao em timeout, conexao derrubada (``ConnectionResetError``,
    ``ChunkedEncodingError``) e status 403, 429, 500, 502, 503 e 504, e sao
    ajustaveis com
    ``politica=`` no construtor.
    """

    BASE_URL = "https://www5.tjmg.jus.br/jurisprudencia"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
    )

    #: Prazo de conexao curto para o portal fora do ar falhar logo; leitura
    #: longa porque a busca do cjsg chega a demorar mais de um minuto.
    perfis_http: ClassVar[Mapping[str, RequestPolicy]] = {
        PERFIL_CJSG: RequestPolicy(
            timeout=(10, 120),
            retry_on_timeout=True,
            retry_on_connection_error=True,
        ),
        PERFIL_CPOSG: RequestPolicy(
            timeout=(10, 30),
            retry_on_timeout=True,
            retry_on_connection_error=True,
        ),
    }

    def __init__(
        self,
        sleep_time: float = 1.0,
        *,
        politica: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> None:
        """Cria o raspador.

        Args:
            sleep_time: Pausa, em segundos, entre paginas do ``cjsg`` e entre
                requisicoes do ``cposg`` (resultado e partes de cada recurso).
            politica: Ajustes por campo dos perfis HTTP ``"cjsg"`` e
                ``"cposg"`` (ver :class:`~juscraper.core.http.RequestPolicy`),
                por exemplo ``{"cjsg": {"timeout": 180, "max_retries": 5}}``.
        """
        super().__init__("TJMG", sleep_time=sleep_time, politica=politica)

    def _configure_session(self, session: requests.Session) -> None:
        """TJMG's portal applies User-Agent gating — keep the Chrome UA."""
        session.headers.update({"User-Agent": self.USER_AGENT})

    def cjsg_download(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        pesquisar_por: Literal["ementa", "acordao"] = "ementa",
        order_by: Literal[0, 1, 2, "0", "1", "2"] = 2,
        tamanho_pagina: Literal[10, 20, 50] = 10,
        data_julgamento_inicio: str | date | None = None,
        data_julgamento_fim: str | date | None = None,
        data_publicacao_inicio: str | date | None = None,
        data_publicacao_fim: str | date | None = None,
        **kwargs,
    ) -> list:
        """Executa a busca de acórdãos no TJMG e devolve o HTML bruto de cada página.

        Aceita os mesmos filtros de :meth:`cjsg`; veja la a lista completa.
        Falhas: ver Raises de :meth:`cjsg` (``.resultado`` sai como DataFrame).

        Args:
            pesquisa: Termo de busca livre.
            paginas: Páginas a baixar (1-based). ``None`` baixa todas. Uma busca
                comum com resultados demais levanta ``ValueError`` ("muitos
                resultados"); as listas da busca categorizada não têm esse teto. Na
                busca categorizada, ``paginas`` vale para cada lista.
            pesquisar_por: Campo em que buscar: ``"ementa"`` ou ``"acordao"``
                (inteiro teor).
            order_by: Ordem: ``2`` data de julgamento, ``1`` data de publicação,
                ``0`` precisão.
            tamanho_pagina: Resultados por página (10, 20 ou 50). Aceita
                ``linhas_por_pagina`` como alias deprecado.
            data_julgamento_inicio: Início do intervalo de julgamento:
                ``DD/MM/AAAA``, ``DD-MM-AAAA``, ``AAAA-MM-DD``, ``AAAA/MM/DD``,
                ``date`` ou ``datetime``.
            data_julgamento_fim: Fim do intervalo de julgamento (mesmos formatos).
            data_publicacao_inicio: Início do intervalo de publicação (mesmos
                formatos).
            data_publicacao_fim: Fim do intervalo de publicação (mesmos formatos).
            **kwargs: Aliases deprecados; ver :meth:`cjsg`.
        """
        tamanho_pagina = resolve_deprecated_alias(
            kwargs, "linhas_por_pagina", "tamanho_pagina", tamanho_pagina, sentinel=10
        )
        inp = apply_input_pipeline_search(
            InputCJSGTJMG,
            "TJMGScraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            data_publicacao_inicio=data_publicacao_inicio,
            data_publicacao_fim=data_publicacao_fim,
            pesquisar_por=pesquisar_por,
            order_by=order_by,
            tamanho_pagina=tamanho_pagina,
        )

        return _cjsg_download(
            pesquisa=inp.pesquisa or "",
            paginas=inp.paginas_normalizadas,
            pesquisar_por=inp.pesquisar_por,
            order_by=str(inp.order_by),
            data_julgamento_inicial=_br_date(inp.data_julgamento_inicio),
            data_julgamento_final=_br_date(inp.data_julgamento_fim),
            data_publicacao_inicial=_br_date(inp.data_publicacao_inicio),
            data_publicacao_final=_br_date(inp.data_publicacao_fim),
            linhas_por_pagina=inp.tamanho_pagina,
            sleep_time=self.sleep_time,
            request_fn=self._request_with_retry,
            session=self.session,
        )

    def cjsg_parse(self, raw_pages: list) -> pd.DataFrame:
        """Transform raw TJMG HTML pages into a DataFrame.

        A página "muitos resultados" levanta ``ValueError``, como no
        :meth:`cjsg`; a página com erro de busca ou com a busca categorizada
        levanta :class:`~juscraper.courts.tjmg.parse.TJMGBuscaSemListaError`.
        """
        return _cjsg_parse(raw_pages)

    def cjsg(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        pesquisar_por: Literal["ementa", "acordao"] = "ementa",
        order_by: Literal[0, 1, 2, "0", "1", "2"] = 2,
        tamanho_pagina: Literal[10, 20, 50] = 10,
        **kwargs,
    ) -> pd.DataFrame:
        """Busca jurisprudencia no TJMG (acordaos com captcha numerico).

        Args:
            pesquisa: Termo de busca livre.
            paginas: Paginas 1-based; ``None`` baixa
                todas. Default ``None``. A busca comum com resultados demais
                levanta ``ValueError`` ("muitos resultados").
                Quando ha acordaos de repetitivos no resultado, o portal
                responde com a busca categorizada, uma lista por categoria
                (repetitivos e demais acordaos), sem esse limite; o ``cjsg``
                segue cada lista, e ``paginas`` vale para cada uma delas.
            pesquisar_por: Campo onde buscar.
                ``"acordao"`` busca no inteiro teor. Default ``"ementa"``.
            order_by: Ordenacao: ``2`` data julgamento,
                ``1`` data publicacao, ``0`` precisao. Default ``2``.
            tamanho_pagina: Resultados por pagina (10, 20 ou 50).
            **kwargs: Filtros aceitos pelo schema :class:`InputCJSGTJMG`.
                Listados abaixo (todos opcionais; ``None`` = sem filtro):

                * ``data_julgamento_inicio`` / ``data_julgamento_fim``
                  (str | date | None): ``DD/MM/AAAA``, ``DD-MM-AAAA``,
                  ``AAAA-MM-DD``, ``AAAA/MM/DD``, ``date`` ou ``datetime``.
                  Backend: ``dataJulgamentoInicial`` /
                  ``dataJulgamentoFinal``.
                * ``data_publicacao_inicio`` / ``data_publicacao_fim``
                  (str | date | None): nos mesmos formatos. Backend:
                  ``dataPublicacaoInicial`` /
                  ``dataPublicacaoFinal``.

        Aliases deprecados (popados com ``DeprecationWarning`` antes do pydantic):
            * ``query`` / ``termo`` -> ``pesquisa``
            * ``data_inicio`` / ``data_fim`` -> ``data_julgamento_inicio`` / ``_fim``
            * ``data_julgamento_de`` / ``_ate`` -> ``data_julgamento_inicio`` / ``_fim``
            * ``data_publicacao_de`` / ``_ate`` -> ``data_publicacao_inicio`` / ``_fim``
            * ``linhas_por_pagina`` -> ``tamanho_pagina``

        Raises:
            TypeError: Quando um kwarg desconhecido e passado.
            ValidationError: Quando um filtro tem formato invalido.
            ValueError: A busca comum teve resultados demais ("muitos
                resultados"); restrinja as datas ou os termos.
            ColetaParcialError: Uma pagina falhou depois das tentativas do
                perfil ``"cjsg"``, com outra ja baixada antes dela. A busca
                para nessa pagina; ``.resultado`` traz as anteriores, e a
                mensagem lista as que faltam (e, na busca categorizada, a
                lista da pagina e as seguintes). Sem pagina baixada antes, sobe
                a excecao original (``requests.ConnectionError``, por exemplo).
            TJMGBuscaSemListaError: O portal respondeu a pagina 1 com o erro
                do banco (``ORA-20000 ... DRG-10599``), visto sem filtro de
                data e em faixas longas.
            CaptchaEsgotadoError: O portal recusou o captcha em todas as
                tentativas.

        Returns:
            DataFrame com os acordaos.

        See also:
            :class:`InputCJSGTJMG` — schema pydantic e a fonte da verdade dos
            filtros aceitos.
        """
        return self.cjsg_parse(self.cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            pesquisar_por=pesquisar_por,
            order_by=order_by,
            tamanho_pagina=tamanho_pagina,
            **kwargs,
        ))

    def cpopg(self, id_cnj: str | list[str]):
        """Stub: first degree case search not implemented for TJMG."""
        raise NotImplementedError("TJMG does not implement cpopg.")

    def _coerce_id_cnj(self, id_cnj: str | list[str], **kwargs: Any) -> list[str]:
        """Valida via pydantic e devolve a lista de numeros so com digitos."""
        try:
            inp = InputCPOSGTJMG(id_cnj=id_cnj, **kwargs)
        except ValidationError as exc:
            raise_on_extra_kwargs(exc, "TJMGScraper.cposg")
            raise
        raw = inp.id_cnj if isinstance(inp.id_cnj, list) else [inp.id_cnj]
        numeros = [clean_cnj(c) for c in raw]
        invalid = [n for n in numeros if len(n) not in (17, 20)]
        if invalid:
            raise ValueError(
                "TJMG cposg aceita CNJ (20 digitos) ou numero TJMG (17 digitos); "
                f"recebido: {invalid}"
            )
        return numeros

    def _download_cposg(self, id_cnj: str | list[str], kwargs: dict[str, Any]) -> list[dict]:
        """Corpo comum de :meth:`cposg_download` e :meth:`cposg`.

        O aviso de falhas sai por :func:`juscraper.core.avisos.avisar`, que o
        atribui ao codigo de quem chamou o metodo publico, qualquer que seja
        o caminho ate ele.
        """
        numeros = self._coerce_id_cnj(id_cnj, **kwargs)
        return _cposg_download(
            numeros,
            request_fn=self._request_with_retry,
            extract_partes_ids=extract_partes_ids,
            sleep_time=self.sleep_time,
        )

    def cposg_download(self, id_cnj: str | list[str], **kwargs: Any) -> list[dict]:
        """Baixa o HTML de resultado e de partes/advogados de cada processo.

        Retorna uma lista alinhada com ``id_cnj``. Veja :meth:`cposg` para
        os formatos de numero aceitos e o ``UserWarning`` emitido quando
        alguma consulta falha; aqui a falha aparece como ``None`` no HTML
        correspondente.
        """
        return self._download_cposg(id_cnj, kwargs)

    def cposg_parse(self, raw: list[dict]) -> pd.DataFrame:
        """Converte a saida de :meth:`cposg_download` em DataFrame."""
        return _cposg_parse(raw)

    def cposg(self, id_cnj: str | list[str], **kwargs: Any) -> pd.DataFrame:
        """Consulta processos de 2o grau do TJMG, com partes e advogados.

        Usa a consulta processual publica de 2a instancia
        (``www4.tjmg.jus.br/juridico/sf``), que nao tem captcha. Um CNJ pode
        ter varios recursos (apelacao, embargos, agravo...); cada recurso vira
        uma linha.

        Args:
            id_cnj: CNJ (20 digitos) ou numero TJMG
                (17 digitos, ex.: ``"1.0000.26.408376-7/001"`` — a coluna
                ``processo_interno`` do :meth:`cjsg`). Mascara opcional.
                Com CNJ, vem todos os recursos vinculados; com numero TJMG,
                so aquele recurso.

        Raises:
            TypeError: Quando um kwarg desconhecido e passado.
            ValueError: Quando um numero nao tem 17 nem 20 digitos.

        Returns:
            Uma linha por recurso, com ``id_cnj``, ``processo``,
                ``processo_interno``, ``segredo_justica``, ``situacao``,
                ``secretaria``, ``classe``, ``assunto``, ``orgao_julgador``,
                ``data_cadastramento``, ``data_distribuicao`` e ``partes``.
                ``partes`` e uma lista de dicts ``{"tipo", "nome", "baixa",
                "advogados"}``, com ``advogados`` = lista de ``{"oab", "nome"}``
                (``oab`` como publicada, ou ``None`` quando ausente).
                Numeros nao encontrados geram uma linha so com ``id_cnj``.
                ``partes`` fica ``None`` em dois casos, separados pela coluna
                ``segredo_justica``: recurso em segredo de justica
                (``segredo_justica=True``) ou falha ao baixar a pagina de partes
                (``segredo_justica=False``).

        Avisos:
            ``UserWarning``: Quando alguma consulta falha: timeout, erro de
            conexao ou status retryable (403, 429, 5xx) que persistem
            apos as retentativas, ou outro erro HTTP, que nao e repetido.
            A mensagem lista os numeros afetados. Falha na
            pagina de resultado gera a linha so com ``id_cnj``, igual a
            um numero nao encontrado; falha na de partes deixa
            ``partes=None``.

        Examples: Exemplo
            >>> import juscraper as jus
            >>> tjmg = jus.scraper("tjmg")
            >>> df = tjmg.cposg("5000344-57.2025.8.13.0461")
            >>> advs = df.explode("partes").dropna(subset=["partes"])

        See also:
            :class:`InputCPOSGTJMG` / :class:`OutputCPOSGTJMG`.
        """
        return self.cposg_parse(self._download_cposg(id_cnj, kwargs))


def _br_date(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        formatted: str = value.strftime("%d/%m/%Y")
        return formatted
    text = str(value).strip()
    if not text:
        return ""
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return f"{text[8:10]}/{text[5:7]}/{text[0:4]}"
    return text
