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
    "funcionando": "Funcionando",
    "degradado": "Degradado",
    "indisponivel": "Indisponível",
    "nao_verificado": "Não verificado",
}
TEXTOS = {
    "titulo": "Implementações e status",
    "aviso": "Status observado no cenário informado, sem garantia de disponibilidade atual. "
    "Sem evidência ou após {dias} dias, o estado passa a não verificado na próxima geração. "
    "A data limite permanece visível entre atualizações. O último relato de falha continua abaixo.",
    "politica": "[Critérios e atualização](https://github.com/jtrecenti/juscraper/blob/main/"
    "CONTRIBUTING.md#status-dos-raspadores)",
    "tribunal": "Tribunais",
    "agregador": "Agregadores",
    "cabecalho": "Fonte | Endpoint | Estado | Verificação | Válido até",
    "ultimo": "último",
    "detalhes": "Evidências e limitações",
    "contexto": "Ambiente/cenário",
    "versao": "Versão ou commit testado",
    "evidencia": "Evidência",
    "excecao": "Exceção relacionada",
}


class Modelo(BaseModel):
    """Rejeita campos desconhecidos e textos vazios no registro editorial."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, str_min_length=1)


class Observacao(Modelo):
    """Registra uma verificação datada, com evidência e escopo explícitos."""

    estado: str
    verificado_em: date
    versao: str
    motivo: str
    cenario: str
    evidencias: list[HttpUrl] = Field(min_length=1)
    excecao: str | None = None

    @model_validator(mode="after")
    def validar_estado(self):
        """Uma tentativa inconclusiva também exige cenário e evidência."""
        if self.estado not in ESTADOS:
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


def renderizar(registro: Registro, hoje: date) -> str:
    """Preserva a observação original quando o prazo de verificação vence."""
    textos = TEXTOS
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
                estado = ESTADOS["nao_verificado"]
                verificado = validade = "-"
                if observacao:
                    if observacao.verificado_em > hoje:
                        raise ValueError(f"Verificação futura: {fonte.sigla}.{endpoint}")
                    limite = observacao.verificado_em + timedelta(days=registro.validade_dias)
                    verificado = observacao.verificado_em.isoformat()
                    ultimo = ESTADOS[observacao.estado]
                    if observacao.estado != "nao_verificado":
                        validade = limite.isoformat()
                        estado = ultimo if hoje <= limite else f"{estado} ({textos['ultimo']}: {ultimo})"
                    detalhes.extend([
                        f"#### {escapar(fonte.nome)}: `{endpoint}`", "",
                        escapar(observacao.motivo), "",
                        f"{textos['contexto']}: {escapar(observacao.cenario)}. "
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
        for caminho in ("README.md", "docs/index.qmd"):
            destino = argumentos.raiz / caminho
            atual = destino.read_text(encoding="utf-8")
            novo = substituir_bloco(atual, renderizar(registro, argumentos.data))
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
