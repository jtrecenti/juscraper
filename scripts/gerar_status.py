"""Gera as tabelas documentais a partir de status.toml, sem acessar tribunais."""

import argparse
import html
import sys
import tomllib
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError, model_validator

RAIZ = Path(__file__).resolve().parents[1]
INICIO = "<!-- status:inicio -->"
FIM = "<!-- status:fim -->"
ESTADOS = {
    "funcionando": {"pt": "Funcionando", "en": "Working"},
    "degradado": {"pt": "Degradado", "en": "Degraded"},
    "indisponivel": {"pt": "Indisponível", "en": "Unavailable"},
    "nao_verificado": {"pt": "Não verificado", "en": "Not verified"},
}
TEXTOS = {
    "pt": {
        "titulo": "Implementações e status",
        "aviso": "Status observado no cenário informado, sem garantia de disponibilidade atual. "
        "Sem evidência ou após {dias} dias, o estado passa a não verificado na próxima geração. "
        "A data limite permanece visível entre atualizações. O último relato de falha continua abaixo.",
        "politica": "[Critérios e atualização](CONTRIBUTING.md#status-dos-raspadores)",
        "tribunal": "Tribunais",
        "agregador": "Agregadores",
        "cabecalho": "Fonte | Endpoint | Estado | Verificação | Válido até",
        "ultimo": "último",
        "detalhes": "Evidências e limitações",
        "contexto": "Ambiente/cenário",
        "versao": "Versão ou commit testado",
        "evidencia": "Evidência",
        "excecao": "Exceção relacionada",
    },
    "en": {
        "titulo": "Implementations and status",
        "aviso": "Status observed in the stated scenario, with no guarantee of current availability. "
        "Without evidence or after {dias} days, the next generation marks the endpoint as not verified. "
        "The validity deadline remains visible between updates. Previous failure reports remain below.",
        "politica": "[Criteria and updates](https://github.com/jtrecenti/juscraper/blob/main/"
        "CONTRIBUTING.md#status-dos-raspadores)",
        "tribunal": "Courts",
        "agregador": "Aggregators",
        "cabecalho": "Source | Endpoint | Status | Verified on | Valid until",
        "ultimo": "last",
        "detalhes": "Evidence and limitations",
        "contexto": "Environment/scenario",
        "versao": "Tested version or commit",
        "evidencia": "Evidence",
        "excecao": "Related exception",
    },
}


class Modelo(BaseModel):
    """Rejeita campos desconhecidos e textos vazios no registro editorial."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, str_min_length=1)


class TextoBilingue(Modelo):
    """Mantém o mesmo registro acessível nos dois idiomas das tabelas."""

    pt: str
    en: str


class Observacao(Modelo):
    """Registra uma verificação datada, com evidência e escopo explícitos."""

    estado: str
    verificado_em: date
    versao: str
    motivo: TextoBilingue
    cenario: TextoBilingue
    evidencias: list[HttpUrl] = Field(min_length=1)
    excecao: str | None = None

    @model_validator(mode="after")
    def validar_estado(self):
        """Ausência de observação representa o estado não verificado."""
        if self.estado not in ESTADOS or self.estado == "nao_verificado":
            raise ValueError("Observação deve registrar um estado conhecido com evidência.")
        return self


class Fonte(Modelo):
    """Agrupa endpoints documentados, sem inferir status pela presença do método."""

    sigla: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    nome: str
    tipo: Literal["tribunal", "agregador"]
    endpoints: list[str] = Field(min_length=1)
    observacoes: dict[str, Observacao] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validar_endpoints(self):
        """Impede duplicação de linhas e observações fora do inventário."""
        if len(set(self.endpoints)) != len(self.endpoints):
            raise ValueError("Endpoints duplicados.")
        if any(not nome.isidentifier() or nome.startswith("_") for nome in self.endpoints):
            raise ValueError("Endpoint deve ser um identificador público.")
        if self.observacoes.keys() - set(self.endpoints):
            raise ValueError("Observação sem endpoint correspondente.")
        return self


class Registro(Modelo):
    """Fonte única das tabelas e do prazo editorial de validade."""

    validade_dias: int = Field(gt=0, strict=True)
    fontes: list[Fonte] = Field(min_length=1)

    @model_validator(mode="after")
    def validar_siglas(self):
        """Cada raspador aparece uma vez no inventário."""
        if len({fonte.sigla for fonte in self.fontes}) != len(self.fontes):
            raise ValueError("Siglas duplicadas.")
        return self


def escapar(texto: str) -> str:
    """Protege células contra HTML, pipes e quebras de linha editoriais."""
    return html.escape(texto, quote=False).replace("|", "&#124;").replace("\n", " ").replace("\r", " ")


def renderizar(registro: Registro, idioma: str, hoje: date) -> str:
    """Preserva a observação original quando o prazo de verificação vence."""
    textos = TEXTOS[idioma]
    linhas = [
        INICIO, f"## {textos['titulo']}", "",
        textos["aviso"].format(dias=registro.validade_dias), "", textos["politica"], "",
    ]
    detalhes = []
    for tipo in ("tribunal", "agregador"):
        linhas.extend([f"### {textos[tipo]}", "", f"| {textos['cabecalho']} |", "|---|---|---|---|---|"])
        for fonte in sorted(registro.fontes, key=lambda item: item.sigla):
            if fonte.tipo != tipo:
                continue
            for endpoint in fonte.endpoints:
                observacao = fonte.observacoes.get(endpoint)
                estado = ESTADOS["nao_verificado"][idioma]
                verificado = validade = "-"
                if observacao:
                    if observacao.verificado_em > hoje:
                        raise ValueError(f"Verificação futura: {fonte.sigla}.{endpoint}")
                    limite = observacao.verificado_em + timedelta(days=registro.validade_dias)
                    verificado, validade = observacao.verificado_em.isoformat(), limite.isoformat()
                    ultimo = ESTADOS[observacao.estado][idioma]
                    estado = ultimo if hoje <= limite else f"{estado} ({textos['ultimo']}: {ultimo})"
                    detalhes.extend([
                        f"#### {escapar(fonte.nome)}: `{endpoint}`", "",
                        escapar(getattr(observacao.motivo, idioma)), "",
                        f"{textos['contexto']}: {escapar(getattr(observacao.cenario, idioma))}. "
                        f"{textos['versao']}: {escapar(observacao.versao)}.", "",
                        " · ".join(
                            f"[{textos['evidencia']} {indice}]({url})"
                            for indice, url in enumerate(observacao.evidencias, 1)
                        ), "",
                    ])
                    if observacao.excecao:
                        detalhes.extend([f"{textos['excecao']}: {escapar(observacao.excecao)}.", ""])
                linhas.append(f"| {escapar(fonte.nome)} | `{endpoint}` | {estado} | {verificado} | {validade} |")
        linhas.append("")
    if detalhes:
        linhas.extend([f"### {textos['detalhes']}", "", *detalhes])
    linhas.append(FIM)
    return "\n".join(linhas)


def substituir_bloco(texto: str, bloco: str) -> str:
    """Exige um par único de marcadores para preservar o restante do documento."""
    if texto.count(INICIO) != 1 or texto.count(FIM) != 1:
        raise ValueError("Documento deve conter um único par de marcadores de status.")
    antes, restante = texto.split(INICIO)
    if FIM not in restante:
        raise ValueError("Marcadores de status fora de ordem.")
    _, depois = restante.split(FIM)
    return antes + bloco + depois


def main() -> int:
    """Atualiza os documentos ou falha se estiverem divergentes, sem rede."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verifica sem escrever")
    parser.add_argument("--raiz", type=Path, default=RAIZ, help="raiz do repositório")
    parser.add_argument("--data", type=date.fromisoformat, default=date.today(), help="data ISO de referência")
    argumentos = parser.parse_args()
    try:
        with (argumentos.raiz / "status.toml").open("rb") as arquivo:
            registro = Registro.model_validate(tomllib.load(arquivo))
        alteracoes = []
        # Valida os dois documentos antes de escrever, evitando atualização parcial por erro de marcador.
        for caminho, idioma in (("README.md", "pt"), ("docs/index.qmd", "en")):
            destino = argumentos.raiz / caminho
            atual = destino.read_text(encoding="utf-8")
            novo = substituir_bloco(atual, renderizar(registro, idioma, argumentos.data))
            if atual != novo:
                alteracoes.append((destino, novo))
        for destino, novo in alteracoes:
            print(f"{'Divergente' if argumentos.check else 'Atualizado'}: {destino.relative_to(argumentos.raiz)}")
            if not argumentos.check:
                destino.write_text(novo, encoding="utf-8")
        return int(argumentos.check and bool(alteracoes))
    except (OSError, ValueError, ValidationError) as erro:
        print(f"Registro de status inválido: {erro}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
