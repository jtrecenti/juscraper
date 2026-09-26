"""Scraper for the Court of Justice of Minas Gerais (TJMG)."""
from __future__ import annotations

from typing import Any, Literal

import pandas as pd
import requests
from pydantic import ValidationError

from juscraper.core.http import HTTPScraper
from juscraper.utils.cnj import clean_cnj
from juscraper.utils.params import apply_input_pipeline_search, resolve_deprecated_alias

from .cposg_download import cposg_download as _cposg_download
from .cposg_parse import cposg_parse as _cposg_parse
from .cposg_parse import extract_partes_ids
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
    """

    BASE_URL = "https://www5.tjmg.jus.br/jurisprudencia"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
    )

    def __init__(self, sleep_time: float = 1.0):
        super().__init__("TJMG", sleep_time=sleep_time)

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
        data_julgamento_inicio: str | None = None,
        data_julgamento_fim: str | None = None,
        data_publicacao_inicio: str | None = None,
        data_publicacao_fim: str | None = None,
        **kwargs,
    ) -> list:
        """Run a TJMG acórdão search and return the raw HTML of each page.

        Aceita os mesmos filtros de :meth:`cjsg`; veja la a lista completa.

        Parameters
        ----------
        pesquisa : str
            Free-text search term.
        paginas : int, list, range or None
            Pages to download (1-based). ``None`` downloads every page
            (capped at 400 results, the TJMG limit).
        pesquisar_por : str
            Field to search in: ``"ementa"`` or ``"acordao"``
            (inteiro teor).
        order_by : int
            Sort order: ``2`` data julgamento, ``1`` data publicação,
            ``0`` precisão.
        tamanho_pagina : int
            Results per page (10, 20 or 50). Aceita ``linhas_por_pagina``
            como alias deprecado.
        data_julgamento_inicio, data_julgamento_fim : str
            Julgamento date range (``dd/mm/yyyy`` or ``yyyy-mm-dd``).
        data_publicacao_inicio, data_publicacao_fim : str
            Publicação date range (``dd/mm/yyyy`` or ``yyyy-mm-dd``).
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
            paginas=inp.paginas,
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
        """Transform raw TJMG HTML pages into a DataFrame."""
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
            pesquisa (str): Termo de busca livre.
            paginas (int | list | range | None): Paginas 1-based; ``None`` baixa
                todas. Default ``None`` (cap de 400 resultados, limite do TJMG).
            pesquisar_por ({"ementa", "acordao"}): Campo onde buscar.
                ``"acordao"`` busca no inteiro teor. Default ``"ementa"``.
            order_by (int | str): Ordenacao: ``2`` data julgamento,
                ``1`` data publicacao, ``0`` precisao. Default ``2``.
            tamanho_pagina (int): Resultados por pagina (10, 20 ou 50).
            **kwargs: Filtros aceitos pelo schema :class:`InputCJSGTJMG`.
                Listados abaixo (todos opcionais; ``None`` = sem filtro):

                * ``data_julgamento_inicio`` / ``data_julgamento_fim`` (str):
                  ``DD/MM/AAAA``. Backend: ``dataJulgamentoInicial`` /
                  ``dataJulgamentoFinal``.
                * ``data_publicacao_inicio`` / ``data_publicacao_fim`` (str):
                  ``DD/MM/AAAA``. Backend: ``dataPublicacaoInicial`` /
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

        Returns:
            pd.DataFrame: DataFrame com os acordaos.

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
            extras = [err for err in exc.errors() if err["type"] == "extra_forbidden"]
            if extras and len(extras) == len(exc.errors()):
                names = ", ".join(repr(err["loc"][-1]) for err in extras)
                raise TypeError(
                    f"TJMGScraper.cposg got unexpected keyword argument(s): {names}"
                ) from exc
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

    def cposg_download(self, id_cnj: str | list[str], **kwargs: Any) -> list[dict]:
        """Baixa o HTML de resultado e de partes/advogados de cada processo.

        Retorna uma lista alinhada com ``id_cnj``. Veja :meth:`cposg` para
        os formatos de numero aceitos.
        """
        numeros = self._coerce_id_cnj(id_cnj, **kwargs)
        return _cposg_download(
            numeros,
            request_fn=self._request_with_retry,
            extract_partes_ids=extract_partes_ids,
            sleep_time=self.sleep_time,
        )

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
            id_cnj (str | list[str]): CNJ (20 digitos) ou numero TJMG
                (17 digitos, ex.: ``"1.0000.26.408376-7/001"`` — a coluna
                ``processo_interno`` do :meth:`cjsg`). Mascara opcional.
                Com CNJ, vem todos os recursos vinculados; com numero TJMG,
                so aquele recurso.

        Raises:
            TypeError: Quando um kwarg desconhecido e passado.
            ValueError: Quando um numero nao tem 17 nem 20 digitos.

        Returns:
            pd.DataFrame: Uma linha por recurso, com ``id_cnj``, ``processo``,
            ``processo_interno``, ``segredo_justica``, ``situacao``,
            ``secretaria``, ``classe``, ``assunto``, ``orgao_julgador``,
            ``data_cadastramento``, ``data_distribuicao`` e ``partes``.
            ``partes`` e uma lista de dicts ``{"tipo", "nome", "baixa",
            "advogados"}``, com ``advogados`` = lista de ``{"oab", "nome"}``.
            Numeros nao encontrados geram uma linha so com ``id_cnj``;
            recursos em segredo de justica vem com ``partes=None``.

        Exemplo:
            >>> import juscraper as jus
            >>> tjmg = jus.scraper("tjmg")
            >>> df = tjmg.cposg("5000344-57.2025.8.13.0461")
            >>> advs = df.explode("partes").dropna(subset=["partes"])

        See also:
            :class:`InputCPOSGTJMG` / :class:`OutputCPOSGTJMG`.
        """
        return self.cposg_parse(self.cposg_download(id_cnj, **kwargs))


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
