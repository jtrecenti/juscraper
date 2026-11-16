"""Pydantic schemas for TJRJ scraper endpoints."""
from __future__ import annotations

from typing import Literal

from pydantic import field_validator, model_validator

from ...schemas import OutputCJSGBase, OutputDataPublicacaoMixin, OutputRelatoriaMixin, SearchBase
from ...utils.params import validate_intervalo_datas


class InputCJSGTJRJ(SearchBase):
    """Accepted input for TJRJ ``cjsg`` / ``cjsg_download``.

    Endpoint ASPX (ejuris). ``pesquisa`` aceita os aliases deprecados
    ``query`` / ``termo`` via :func:`juscraper.utils.params.normalize_pesquisa`,
    que roda *antes* deste modelo. O TJRJ so expoe filtro por ano
    (``ano_inicio``/``ano_fim``); ``data_julgamento_*`` e
    ``data_publicacao_*`` nao sao aceitos — o backend ASPX nao expoe esses
    filtros, e este schema rejeita via ``extra="forbid"``.
    """

    ano_inicio: str | int | None = None
    ano_fim: str | int | None = None
    # Opcoes de ``cmbCompetencia`` e ``cmbOrigem`` no formulario do ejuris. A
    # lista de competencias muda com a origem (``"3"`` Fazendaria so aparece na
    # Turma Recursal; o Conselho da Magistratura so tem ``"0"``, "Selecione...").
    # O download confere a combinacao com o form da origem; ``None`` usa a
    # primeira opcao do form, como o navegador.
    competencia: Literal["1", "2", "3"] | None = None
    origem: Literal["1", "2", "3", "4", "5"] = "1"
    tipo_acordao: bool = True
    tipo_monocratica: bool = True
    magistrado_codigo: str | None = None
    orgao_codigo: str | None = None

    @field_validator("competencia", "origem", mode="before")
    @classmethod
    def _coerce_int(cls, value):
        # O backend ASPX espera string no body, mas o usuario tipicamente
        # pensa em valores discretos pequenos (1/2/3) — aceitar ``int`` evita
        # surpresa do tipo `competencia=2 -> ValidationError`. Coerce so para
        # int "puro"; bool nao entra (Python trata bool como subtipo de int).
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return str(value)
        return value

    @model_validator(mode="after")
    def _anos_em_ordem(self) -> InputCJSGTJRJ:
        # O JS do portal (``ValidarIntervaloData``) nao deixa submeter intervalo
        # invertido; enviado mesmo assim, o portal devolve 0 documentos.
        inicio, fim = str(self.ano_inicio or ""), str(self.ano_fim or "")
        if inicio.isdigit() and fim.isdigit():
            validate_intervalo_datas(inicio, fim, max_dias=None, formato="%Y", rotulo="ano")
        return self


class OutputCJSGTJRJ(OutputCJSGBase, OutputRelatoriaMixin, OutputDataPublicacaoMixin):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJRJScraper.cjsg`.

    Reflete ``tjrj.parse.cjsg_parse`` — backend ASPX (ejuris) com datas no
    formato ``/Date(millis)/`` ja convertidas.
    """

    cod_documento: str | int | None = None
    numero_antigo: str | None = None
    classe: str | None = None
    tipo_documento: str | None = None
