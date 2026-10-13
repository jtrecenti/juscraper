"""Gera as tabelas documentais a partir de status.toml, sem acessar tribunais."""

import argparse
import html
import re
import sys
import tomllib
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError, model_validator

RAIZ = Path(__file__).resolve().parents[1]
INICIO = "<!-- status:inicio -->"
FIM = "<!-- status:fim -->"
DOCUMENTOS = ("README.md", "docs/index.qmd")
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
    "gerado": "Tabelas geradas em {data}.",
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


# Derivado do texto do bloco para que a leitura da data acompanhe qualquer mudança na frase.
REFERENCIA = re.compile(re.escape(TEXTOS["gerado"]).replace(r"\{data\}", r"(\d{4}-\d{2}-\d{2})"))


def escapar(texto: str) -> str:
    """Protege células contra HTML, pipes e quebras de linha editoriais."""
    return html.escape(texto, quote=False).replace("|", "&#124;").replace("\n", " ").replace("\r", " ")


def prazo(observacao: Observacao, registro: Registro) -> date | None:
    """Último dia de validade; tentativa inconclusiva não tem prazo porque nada atestou."""
    if observacao.estado == "nao_verificado":
        return None
    return observacao.verificado_em + timedelta(days=registro.validade_dias)


def vencidas(registro: Registro, hoje: date) -> set[str]:
    """Observações cujo prazo terminou antes da data de referência."""
    return {
        f"{fonte.sigla}.{endpoint}"
        for fonte in registro.fontes
        for endpoint, observacao in fonte.observacoes.items()
        if (limite := prazo(observacao, registro)) and hoje > limite
    }


def renderizar(registro: Registro, hoje: date) -> str:
    """Preserva a observação original quando o prazo de verificação vence."""
    textos = TEXTOS
    linhas = [
        INICIO, f"## {textos['titulo']}", "",
        textos["aviso"].format(dias=registro.validade_dias), "",
        textos["gerado"].format(data=hoje.isoformat()), "", textos["politica"], "",
    ]
    fora_do_prazo = vencidas(registro, hoje)
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
                        raise ValueError(
                            f"Verificação de {fonte.sigla}.{endpoint} posterior à data de referência "
                            f"{hoje.isoformat()}; regenerar as tabelas."
                        )
                    verificado = observacao.verificado_em.isoformat()
                    ultimo = ESTADOS[observacao.estado]
                    if limite := prazo(observacao, registro):
                        validade = limite.isoformat()
                        vencida = f"{fonte.sigla}.{endpoint}" in fora_do_prazo
                        estado = f"{estado} ({textos['ultimo']}: {ultimo})" if vencida else ultimo
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


def data_gravada(documentos: dict[Path, str]) -> date:
    """Data em que os blocos versionados foram gerados, igual nos dois documentos."""
    datas = {data for texto in documentos.values() for data in REFERENCIA.findall(texto)}
    if len(datas) != 1 or any(len(REFERENCIA.findall(texto)) != 1 for texto in documentos.values()):
        raise ValueError("Tabelas sem data de referência única; regenerar com scripts/gerar_status.py.")
    return date.fromisoformat(datas.pop())


def main() -> int:
    """Atualiza os documentos ou falha se estiverem divergentes, sem rede."""
    parser = argparse.ArgumentParser(description=__doc__)
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument("--check", action="store_true", help="verifica a sincronia sem escrever nem ler o relógio")
    modo.add_argument(
        "--vencimento", action="store_true",
        help="falha se alguma observação venceu depois da geração das tabelas",
    )
    parser.add_argument("--raiz", type=Path, default=RAIZ, help="raiz do repositório")
    parser.add_argument(
        "--data", type=date.fromisoformat,
        help="data ISO de referência; por padrão, a gravada nas tabelas com --check e a corrente nos demais modos",
    )
    argumentos = parser.parse_args()
    try:
        with (argumentos.raiz / "status.toml").open("rb") as arquivo:
            registro = Registro.model_validate(tomllib.load(arquivo))
        documentos = {
            destino: destino.read_text(encoding="utf-8")
            for destino in (argumentos.raiz / caminho for caminho in DOCUMENTOS)
        }
        if argumentos.vencimento:
            # Só interessa o que venceu depois da geração: o que já aparece como vencido não pede nova geração.
            ja_exibidas = vencidas(registro, data_gravada(documentos))
            pendentes = vencidas(registro, argumentos.data or date.today()) - ja_exibidas
            for nome in sorted(pendentes):
                print(f"Vencida: {nome}")
            return int(bool(pendentes))
        # A sincronia reproduz a geração na data gravada; com a data corrente, o resultado mudaria no vencimento.
        hoje = argumentos.data or (data_gravada(documentos) if argumentos.check else date.today())
        alteracoes = []
        # Valida os dois documentos antes de escrever, evitando atualização parcial por erro de marcador.
        for destino, atual in documentos.items():
            novo = substituir_bloco(atual, renderizar(registro, hoje))
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
