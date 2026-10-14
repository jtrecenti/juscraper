"""Calendário e relatório da integração semanal, usados pelo workflow Integração."""

import argparse
import json
import re
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
# Códigos de cor ANSI. O nbmake os grava na mensagem, e o pytest troca o ESC,
# que não é válido em XML, pelo texto `#x1B`.
COR_ANSI = re.compile(r"#x1B\[[0-9;]*m")
LINHA_DE_EXCECAO = re.compile(r"^[A-Za-z_][\w.]*: \S")


def em_recesso(dia: date) -> bool:
    """Indica se a data cai no recesso forense, de 20/12 a 20/01, inclusive."""
    return (dia.month == 12 and dia.day >= 20) or (dia.month == 1 and dia.day <= 20)


def deve_rodar(dia: date, evento: str) -> bool:
    """Só a execução agendada respeita o recesso; disparo manual roda sempre."""
    return not (evento == "schedule" and em_recesso(dia))


def resumir_mensagem(mensagem: str) -> str:
    """Escolhe a linha da mensagem de falha que diz o que aconteceu.

    No pytest a primeira linha já é a exceção. No nbmake a mensagem é o
    traceback da célula, que começa por uma linha de hífens e termina na linha
    ``Tipo: mensagem``; nesse caso vale a última linha nesse formato.
    """
    linhas = [linha.strip() for linha in COR_ANSI.sub("", mensagem).splitlines()]
    uteis = [linha for linha in linhas if any(caractere.isalnum() for caractere in linha)]
    if not uteis:
        return ""
    if any("Traceback (most recent call last)" in linha for linha in uteis):
        excecoes = [linha for linha in uteis if LINHA_DE_EXCECAO.match(linha)]
        if excecoes:
            return excecoes[-1]
    return uteis[0]


def ler_suite(caminho: Path) -> dict | None:
    """Conta os casos de um JUnit do pytest; devolve ``None`` se o arquivo não existe."""
    if not caminho.is_file():
        return None
    resumo: dict = {"passaram": 0, "pulados": 0, "falhas": {}}
    # O arquivo é escrito pelo próprio pytest no job anterior, sem DTD nem
    # entidade. Por isso o parser da biblioteca padrão basta, e este script
    # roda no job que tem permissão de escrita em issues sem instalar nada.
    for caso in ET.parse(caminho).getroot().iter("testcase"):  # noqa: S314
        problema = caso.find("failure")
        if problema is None:
            problema = caso.find("error")
        if problema is not None:
            identificador = f"{caso.get('classname', '')}::{caso.get('name', '')}"
            mensagem = problema.get("message") or (problema.text or "")
            # Teste que falha e depois quebra no teardown sai em dois
            # <testcase> com o mesmo id. Fica a primeira mensagem, a do teste.
            resumo["falhas"].setdefault(identificador, resumir_mensagem(mensagem))
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
    # Corpo sem marcador, ou com a lista quebrada, foi editado à mão. Tratar
    # como lista vazia faz toda falha atual contar como nova, e o erro fica do
    # lado de avisar.
    if inicio < 0 or fim < 0:
        return set()
    try:
        lista = json.loads(texto[inicio + len(ABRE_MARCADOR):fim])
    except json.JSONDecodeError:
        return set()
    return {item for item in lista if isinstance(item, str)} if isinstance(lista, list) else set()


def gravar_falhas(identificadores: set[str] | dict[str, str]) -> str:
    """Serializa a lista de falhas dentro do comentário HTML que a guarda.

    O id de um teste parametrizado é texto livre. Escapar `<` e `>` impede que
    um `-->` dentro dele feche o comentário antes da hora e que a abertura do
    marcador reapareça dentro da própria lista.
    """
    lista = json.dumps(sorted(identificadores), ensure_ascii=True)
    lista = lista.replace("<", "\\u003c").replace(">", "\\u003e")
    return f"{ABRE_MARCADOR}{lista}{FECHA_MARCADOR}"


def codigo(texto: str, *, em_tabela: bool) -> str:
    """Põe um texto livre num trecho de código.

    Id de teste e mensagem de erro trazem texto do tribunal. Dentro do trecho
    de código o GitHub não interpreta HTML, link nem menção, então um `@nome`
    na mensagem não notifica ninguém. A barra vertical só precisa de escape
    dentro de tabela; numa lista o escape apareceria como barra invertida.
    """
    limpo = " ".join(texto.split()).replace("`", "'")
    if em_tabela:
        limpo = limpo.replace("|", "\\|")
    return f"`{limpo}`" if limpo else ""


def montar_corpo(
    suites: dict[str, dict | None], falhas: dict[str, str], dia: date, execucao: str, fora: list[str],
) -> str:
    """Monta o corpo da issue, com a lista de falhas gravada num comentário HTML."""
    linhas = [
        AVISO_DE_GERACAO,
        "",
        f"Última execução: {dia.strftime('%d/%m/%Y')} ([registro]({execucao})).",
        "",
    ]
    if fora:
        nomes = ", ".join(f"`{nome}`" for nome in sorted(fora))
        linhas += [f"Fora desta execução, porque dão problema só no runner do GitHub: {nomes}.", ""]
    linhas += [
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
            linhas.append(f"| {codigo(identificador, em_tabela=True)} | {codigo(mensagem, em_tabela=True)} |")
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
            linhas += [f"- {codigo(identificador, em_tabela=False)}" for identificador in sorted(grupo)]
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
    relatorio.add_argument("--fora", default="", help="nomes separados por espaço que ficaram fora da execução")

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
        montar_corpo(suites, falhas, argumentos.data, argumentos.execucao, argumentos.fora.split()), encoding="utf-8",
    )
    anteriores = ler_falhas_anteriores(argumentos.anterior)
    argumentos.comentario.write_text(
        montar_comentario(set(falhas), anteriores, argumentos.data, argumentos.execucao), encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
