"""Pydantic schemas for TJRN scraper endpoints."""
from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import model_validator

from ...schemas import (
    BuscarEm,
    DataJulgamentoMixin,
    OutputCJSGBase,
    OutputDataPublicacaoMixin,
    OutputRelatoriaMixin,
    SearchBase,
)

# Dominios dos filtros de ``cjsg``, usados tambem nas assinaturas de ``TJRNScraper``.
Sistema = Literal["", "PJE", "SAJ"]
Decisoes = Literal["", "Decisão", "Acórdão", "Sentença"]
Jurisdicoes = Literal["", "TJ", "TR"]
Grau = Literal["", "1", "2"]

# Grau dos valores de ``decisoes`` e ``jurisdicoes`` que so existem num grau no
# portal; "Decisão" (monocratica) existe nos dois. Valores de graus diferentes,
# entre si ou com ``grau``, devolvem 0 resultados sem erro, em qualquer periodo
# e termo (26 e 27/11/2026). O formulario do portal esconde "TR" quando o grau e "1".
_GRAU_DO_VALOR = {"Sentença": "1", "Acórdão": "2", "TJ": "2", "TR": "2"}

# Palavras que o portal ignora no termo: as preposicoes essenciais e as conjuncoes
# "e" e "ou", so em minusculas. Termo feito so delas conta como busca vazia e traz
# tudo; "A", "o" ou "da" ja sao termos (27/11/2026).
_PALAVRAS_IGNORADAS = frozenset({
    "a", "ante", "após", "até", "com", "contra", "de", "desde", "e", "em",
    "entre", "ou", "para", "perante", "por", "sem", "sob", "sobre", "trás",
})


class InputCJSGTJRN(SearchBase, DataJulgamentoMixin):
    """Accepted input for TJRN ``cjsg`` / ``cjsg_download``.

    Wired em :meth:`juscraper.courts.tjrn.client.TJRNScraper.cjsg_download`
    desde o #183 — kwargs desconhecidos viram :class:`TypeError` em ambos
    ``cjsg`` e ``cjsg_download``. ``cjsg`` e wrapper trivial
    (``download → parse``).

    Endpoint REST JSON (Elasticsearch). ``pesquisa`` aceita os aliases
    deprecados ``query`` / ``termo`` via
    :func:`juscraper.utils.params.normalize_pesquisa`, que roda *antes*
    deste modelo. Datas de julgamento aceitam os aliases
    ``data_inicio``/``data_fim`` via
    :func:`juscraper.utils.params.normalize_datas` (``data_publicacao_*``
    nao e suportado pelo backend e fica fora do schema). Filtro de data
    de julgamento herdado de :class:`DataJulgamentoMixin`.

    ``BACKEND_DATE_FORMAT`` (``YYYY-MM-DD``) e so o formato interno do
    pipeline. O portal espera ``DD-MM-YYYY`` com hifens: a conversao fica em
    :func:`juscraper.courts.tjrn.client._to_tjrn_date`, porque o backend
    ignora datas com barras ou em ISO e devolve resultados sem filtro.
    """

    BACKEND_DATE_FORMAT: ClassVar[str] = "%Y-%m-%d"

    numero_processo: str | None = None
    id_classe: str | None = None
    id_orgao_julgador: str | None = None
    id_relator: str | None = None
    id_colegiado: str | None = None
    # Valores do seletor "Sistema" do portal (``field-sistema.js``). O backend
    # diferencia maiusculas: "pje" ou outro valor da 0 resultados sem aviso.
    sistema: Sistema | None = None
    # Valores do seletor "Decisoes" do portal (``field-decisao.js``), que o backend
    # compara com ``tipo_teor``: "Decisão" sao as monocraticas, "Acórdão" as
    # colegiadas e "Sentença" as de 1o grau. Vazio (ou ``None``) busca todas.
    decisoes: Decisoes | None = None
    # Valores do seletor "Jurisdicoes" do portal (``field-jurisdicao.js``): "TJ"
    # (Tribunal de Justica) e "TR" (Turmas Recursais e TUJ). Vazio (ou ``None``)
    # busca todas. Os nomes por extenso fazem o portal responder 502/503.
    jurisdicoes: Jurisdicoes | None = None
    # Valores dos radios ``radioGrau`` do portal. Outro valor da 0 resultados.
    grau: Grau | None = None
    buscar_em: BuscarEm = "ementa"

    @model_validator(mode="after")
    def _filtros_do_mesmo_grau(self) -> InputCJSGTJRN:
        pedidos = {
            f'{campo}="{valor}"': valor if campo == "grau" else _GRAU_DO_VALOR.get(valor)
            for campo, valor in (
                ("decisoes", self.decisoes),
                ("jurisdicoes", self.jurisdicoes),
                ("grau", self.grau),
            )
            if valor
        }
        graus = {filtro: grau for filtro, grau in pedidos.items() if grau}
        if len(set(graus.values())) > 1:
            conflito = ", ".join(f"{filtro} ({grau}o grau)" for filtro, grau in graus.items())
            raise ValueError(
                f"Os filtros pedem graus diferentes, e o portal nao devolve resultados: {conflito}. "
                '"Sentença" e do 1o grau, "Acórdão" do 2o e "Decisão" (monocratica) dos dois; '
                'jurisdicoes "TJ" e "TR" so cobrem o 2o grau. Para o 1o grau, use grau="1", '
                '"Sentença" ou "Decisão", sem jurisdicoes; para o 2o, grau="2", "Acórdão" ou '
                '"Decisão", com ou sem jurisdicoes.'
            )
        return self

    @model_validator(mode="after")
    def _termo_na_ementa_de_quem_tem(self) -> InputCJSGTJRN:
        # No portal so os acordaos tem ementa. As monocraticas com ementa sao poucas
        # do SAJ, de 2008, e nenhuma entra em "TJ" ou "TR". Com termo na ementa, os
        # filtros abaixo voltam com 0 resultados sem erro, em qualquer periodo e termo.
        if self.buscar_em != "ementa" or set(self.pesquisa.split()) <= _PALAVRAS_IGNORADAS:
            return self
        sem_ementa = [
            filtro
            for filtro, pedido in (
                ('decisoes="Sentença"', self.decisoes == "Sentença"),
                ('grau="1"', self.grau == "1"),
                (f'decisoes="Decisão" com jurisdicoes="{self.jurisdicoes}"',
                 self.decisoes == "Decisão" and bool(self.jurisdicoes)),
            )
            if pedido
        ]
        if sem_ementa:
            raise ValueError(
                f"pesquisa busca na ementa, e no portal so os acordaos tem ementa: com "
                f'{", ".join(sem_ementa)}, a busca nao traz resultados. Para buscar o termo '
                'no texto integral da decisao, use buscar_em="inteiro_teor"; para trazer '
                'todas as decisoes do filtro, use pesquisa="" com periodo de julgamento.'
            )
        return self


class OutputCJSGTJRN(OutputCJSGBase, OutputRelatoriaMixin, OutputDataPublicacaoMixin):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJRNScraper.cjsg`.

    Reflete ``tjrn.parse.cjsg_parse_manager`` apos renomeacao canonica
    (``classe_judicial`` -> ``classe``). ``data_publicacao`` vem de
    ``dt_publicacao`` do backend Elasticsearch, convertida para ``date``.
    ``relator`` vem de ``magistrado`` (na sentenca, o juiz de 1o grau) e
    ``tipo_decisao`` de ``tipo_teor``: ``"Acórdão"``, ``"Decisão"``
    (monocratica) ou ``"Sentença"``.
    """

    classe: str | None = None
    colegiado: str | None = None
    tipo_decisao: str | None = None
    sistema: str | None = None
    sigiloso: bool | str | None = None
