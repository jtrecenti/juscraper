"""Calendário e relatório da integração semanal, usados pelo workflow Integração."""

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

AVISO_DE_GERACAO = (
    "<!-- Gerado por scripts/integration_report.py. "
    "Edições manuais são sobrescritas na próxima execução. -->"
)
ABRE_MARCADOR = "<!-- falhas-integracao: "
FECHA_MARCADOR = " -->"
# O corpo de uma issue aceita 65.536 caracteres. Com a rede do runner fora do
# ar todos os testes falham de uma vez, e a tabela inteira passaria do limite.
LIMITE_DE_LINHAS = 100
LIMITE_DA_MENSAGEM = 160


def em_recesso(dia: date) -> bool:
    """Indica se a data cai no recesso forense, de 20/12 a 20/01, inclusive."""
    return (dia.month == 12 and dia.day >= 20) or (dia.month == 1 and dia.day <= 20)


def deve_rodar(dia: date, evento: str) -> bool:
    """Só a execução agendada respeita o recesso; disparo manual roda sempre."""
    return not (evento == "schedule" and em_recesso(dia))


def ler_suite(caminho: Path) -> dict | None:
    """Conta os casos de um JUnit do pytest; devolve ``None`` se o arquivo não existe.

    Arquivo ausente significa que o pytest não chegou ao fim (tempo esgotado ou
    erro antes da coleta), porque o JUnit só é gravado no encerramento.
    """
    if not caminho.is_file():
        return None
    resumo: dict = {"passaram": 0, "pulados": 0, "falhas": {}}
    # O arquivo é escrito pelo próprio pytest no job anterior, sem DTD nem
    # entidade. Por isso o parser da biblioteca padrão basta, e este script
    # roda no job que tem permissão de escrita em issues sem instalar nada.
    for caso in ET.parse(caminho).getroot().iter("testcase"):  # noqa: S314
        # Um caso pode trazer <failure> e <error> juntos (falha no teste e no
        # teardown). Conta uma vez, com a primeira mensagem.
        problema = caso.find("failure")
        if problema is None:
            problema = caso.find("error")
        if problema is not None:
            identificador = f"{caso.get('classname', '')}::{caso.get('name', '')}"
            mensagem = problema.get("message") or (problema.text or "")
            linhas = mensagem.strip().splitlines()
            resumo["falhas"][identificador] = linhas[0] if linhas else ""
        elif caso.find("skipped") is not None:
            # xfail e o bloqueio anti-bot convertido pelo conftest chegam aqui.
            resumo["pulados"] += 1
        else:
            resumo["passaram"] += 1
    return resumo


def ler_falhas_anteriores(caminho: Path | None) -> set[str] | None:
    """Lê a lista gravada no corpo anterior; ``None`` quando ainda não há issue."""
    if caminho is None or not caminho.is_file():
        return None
    texto = caminho.read_text(encoding="utf-8")
    if not texto.strip():
        return None
    # Vale a última ocorrência. O marcador verdadeiro é a última coisa do
    # corpo, e `gravar_falhas` garante que a abertura não se repete dentro
    # dele; uma mensagem de erro que imite o marcador fica antes e é ignorada.
    inicio = texto.rfind(ABRE_MARCADOR)
    fim = texto.find(FECHA_MARCADOR, inicio)
    if inicio < 0 or fim < 0:
        # Corpo sem marcador foi editado à mão. Tratar como lista vazia faz
        # toda falha atual contar como nova, e o erro fica do lado de avisar.
        return set()
    return set(json.loads(texto[inicio + len(ABRE_MARCADOR):fim]))


def gravar_falhas(identificadores: set[str] | dict[str, str]) -> str:
    """Serializa a lista de falhas dentro do comentário HTML que a guarda.

    O id de um teste parametrizado é texto livre. Escapar `<` e `>` impede que
    um `-->` dentro dele feche o comentário antes da hora e que a abertura do
    marcador reapareça dentro da própria lista.
    """
    lista = json.dumps(sorted(identificadores), ensure_ascii=True)
    lista = lista.replace("<", "\\u003c").replace(">", "\\u003e")
    return f"{ABRE_MARCADOR}{lista}{FECHA_MARCADOR}"


def codigo(texto: str) -> str:
    """Põe um texto livre num trecho de código, dentro de uma célula de tabela.

    Id de teste e mensagem de erro trazem texto do tribunal. Dentro do trecho
    de código o GitHub não interpreta HTML, link nem menção, então um `@nome`
    na mensagem não notifica ninguém.
    """
    limpo = " ".join(texto.split()).replace("`", "'").replace("|", "\\|")
    return f"`{limpo}`" if limpo else ""


def montar_corpo(suites: dict[str, dict | None], falhas: dict[str, str], dia: date, execucao: str) -> str:
    """Monta o corpo da issue, com a lista de falhas gravada num comentário HTML."""
    linhas = [
        AVISO_DE_GERACAO,
        "",
        f"Última execução: {dia.strftime('%d/%m/%Y')} ([registro]({execucao})).",
        "",
        "| Suíte | Passaram | Falharam | Pulados |",
        "| --- | ---: | ---: | ---: |",
    ]
    for rotulo, resumo in suites.items():
        if resumo is None:
            linhas.append(f"| {rotulo} | não terminou | | |")
        else:
            linhas.append(f"| {rotulo} | {resumo['passaram']} | {len(resumo['falhas'])} | {resumo['pulados']} |")
    linhas.append("")
    if falhas:
        linhas += [f"## Falhas ({len(falhas)})", "", "| Teste | Erro |", "| --- | --- |"]
        ordenadas = sorted(falhas)
        for identificador in ordenadas[:LIMITE_DE_LINHAS]:
            mensagem = " ".join(falhas[identificador].split())[:LIMITE_DA_MENSAGEM]
            linhas.append(f"| {codigo(identificador)} | {codigo(mensagem)} |")
        if len(ordenadas) > LIMITE_DE_LINHAS:
            linhas += ["", f"Outras {len(ordenadas) - LIMITE_DE_LINHAS} falhas estão no registro da execução."]
    else:
        linhas.append("Nenhuma falha nesta execução.")
    linhas += ["", gravar_falhas(falhas), ""]
    return "\n".join(linhas)


def montar_comentario(atuais: set[str], anteriores: set[str] | None, dia: date, execucao: str) -> str:
    """Devolve o comentário de mudança, ou texto vazio quando a lista não mudou."""
    if anteriores is None or atuais == anteriores:
        return ""
    linhas = [f"A lista de falhas mudou na execução de {dia.strftime('%d/%m/%Y')} ([registro]({execucao}))."]
    for titulo, grupo in (
        ("Passaram a falhar", atuais - anteriores),
        ("Saíram da lista de falhas", anteriores - atuais),
    ):
        if grupo:
            linhas += ["", f"{titulo}:", ""]
            linhas += [f"- {codigo(identificador)}" for identificador in sorted(grupo)]
    return "\n".join(linhas) + "\n"


def par_de_suite(valor: str) -> tuple[str, Path]:
    """Converte ``rotulo=caminho`` no par usado pelo relatório."""
    rotulo, separador, caminho = valor.partition("=")
    if not separador or not rotulo or not caminho:
        raise argparse.ArgumentTypeError(f"esperado rotulo=caminho, recebido: {valor}")
    return rotulo, Path(caminho)


def main() -> int:
    """Executa o subcomando pedido na linha de comando."""
    analisador = argparse.ArgumentParser(description=__doc__)
    subcomandos = analisador.add_subparsers(dest="subcomando", required=True)

    calendario = subcomandos.add_parser("calendario", help="imprime rodar=true ou rodar=false")
    calendario.add_argument("--data", type=date.fromisoformat, required=True)
    calendario.add_argument("--evento", required=True)

    relatorio = subcomandos.add_parser("relatorio", help="monta o corpo da issue e o comentário de mudança")
    relatorio.add_argument("--suite", type=par_de_suite, action="append", required=True)
    relatorio.add_argument("--anterior", type=Path)
    relatorio.add_argument("--corpo", type=Path, required=True)
    relatorio.add_argument("--comentario", type=Path, required=True)
    relatorio.add_argument("--execucao", required=True)
    relatorio.add_argument("--data", type=date.fromisoformat, required=True)

    argumentos = analisador.parse_args()
    if argumentos.subcomando == "calendario":
        rodar = "true" if deve_rodar(argumentos.data, argumentos.evento) else "false"
        sys.stdout.write(f"rodar={rodar}\n")
        return 0

    suites = {rotulo: ler_suite(caminho) for rotulo, caminho in argumentos.suite}
    falhas: dict[str, str] = {}
    for rotulo, resumo in suites.items():
        if resumo is None:
            # Suíte que não terminou entra na lista para que a mudança de
            # estado (passou a não terminar, voltou a terminar) gere comentário.
            falhas[f"{rotulo}: a suíte não terminou"] = "sem JUnit; ver o registro da execução"
        else:
            falhas.update(resumo["falhas"])
    argumentos.corpo.write_text(
        montar_corpo(suites, falhas, argumentos.data, argumentos.execucao), encoding="utf-8",
    )
    anteriores = ler_falhas_anteriores(argumentos.anterior)
    argumentos.comentario.write_text(
        montar_comentario(set(falhas), anteriores, argumentos.data, argumentos.execucao), encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
