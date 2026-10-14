"""Barra complexidade acima do teto em src/: ciclomática absoluta, cognitiva por catraca."""

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TETO = 15
ALVO = "src"
CORES_ANSI = re.compile(r"\x1b\[[0-9;]*m")
# O Lizard aceita dispensa no fonte (#lizard forgives, forgive global) e não
# tem opção que a desligue; o gate reprova a diretiva antes de medir.
DISPENSA_LIZARD = re.compile(r"#\s*lizard\s*forgive", re.IGNORECASE)


def executar_git(raiz: Path, *argumentos: str) -> str:
    """Executa o Git na raiz do repositório e devolve a saída sem espaços nas pontas."""
    resultado = subprocess.run(["git", *argumentos], cwd=raiz, check=True, capture_output=True)
    return resultado.stdout.decode().strip()


def executavel_complexipy() -> str:
    """Localiza o Complexipy do ambiente do interpretador, porque ele não roda como ``python -m``."""
    vizinho = Path(sys.executable).with_name("complexipy")
    if vizinho.exists():
        return str(vizinho)
    encontrado = shutil.which("complexipy")
    if encontrado is None:
        raise FileNotFoundError("complexipy não está instalado no ambiente do gate.")
    return encontrado


def nao_rastreados(raiz: Path) -> list[str]:
    """Arquivos Python de src/ fora do Git, relativos a src/: rascunho local não entra na medição."""
    saida = executar_git(raiz, "ls-files", "--others", "--", ALVO)
    return [Path(caminho).relative_to(ALVO).as_posix() for caminho in saida.splitlines() if caminho.endswith(".py")]


def conferir_dispensas(raiz: Path) -> list[str]:
    """Reprova dispensa do Lizard em arquivo rastreado de src/."""
    erros = []
    for caminho in executar_git(raiz, "ls-files", "--", ALVO).splitlines():
        if not caminho.endswith(".py"):
            continue
        for numero, linha in enumerate((raiz / caminho).read_text(encoding="utf-8").splitlines(), start=1):
            if DISPENSA_LIZARD.search(linha):
                erros.append(f"{caminho}:{numero}: dispensa do Lizard proibida")
    return erros


def conferir_ciclomatica(raiz: Path, excluidos: list[str]) -> list[str]:
    """Nenhuma função de src/ passa do teto, sem lista de exceções."""
    # Sem -W, o Lizard lê whitelizard.txt da raiz; a lista vazia desliga essa exceção.
    with tempfile.NamedTemporaryFile("w", suffix=".txt") as lista_vazia:
        exclusoes = [argumento for caminho in excluidos for argumento in ("-x", f"{ALVO}/{caminho}")]
        resultado = subprocess.run(
            [sys.executable, "-m", "lizard", "-C", str(TETO), "-W", lista_vazia.name, *exclusoes, "-w", ALVO],
            cwd=raiz, check=False, capture_output=True, text=True,
        )
    if resultado.returncode == 0:
        return []
    avisos = [linha for linha in resultado.stdout.splitlines() if "warning:" in linha]
    return avisos or [resultado.stdout.strip() or resultado.stderr.strip()]


def conferir_cognitiva(raiz: Path, base: str, excluidos: list[str]) -> list[str]:
    """Função nova acima do teto falha; a que já está acima não pode piorar."""
    exclusoes = [argumento for caminho in excluidos for argumento in ("-e", caminho)]
    comando = [
        executavel_complexipy(), ALVO, "-mx", str(TETO), "--diff", base, "--ratchet", "--no-ignore", *exclusoes,
    ]
    resultado = subprocess.run([*comando, "--quiet"], cwd=raiz, check=False, capture_output=True, text=True)
    if resultado.returncode == 0:
        return []
    # Com --quiet o Complexipy não diz o que falhou. Sem ele, imprime a nota de
    # todas as funções antes do diff, e só o diff interessa a quem lê o erro.
    detalhe = subprocess.run(comando, cwd=raiz, check=False, capture_output=True, text=True)
    saida = CORES_ANSI.sub("", detalhe.stdout + detalhe.stderr)
    inicio = saida.find("Complexity diff")
    return [saida[inicio:].strip() if inicio >= 0 else saida.strip()]


def conferir(raiz: Path, referencia: str) -> list[str]:
    """Roda os dois controles contra o ancestral comum de HEAD e da referência."""
    # Num ramo atrás da main, comparar com a ponta dela atribuiria ao ramo, como
    # piora, as melhorias que a main ganhou depois de o ramo sair.
    base = executar_git(raiz, "merge-base", "HEAD", referencia)
    excluidos = nao_rastreados(raiz)
    return conferir_dispensas(raiz) + conferir_ciclomatica(raiz, excluidos) + conferir_cognitiva(raiz, base, excluidos)


def main() -> int:
    """Executa o mesmo controle no pre-commit e no CI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", default="origin/main", help="Base do PR disponível no Git local.")
    argumentos = parser.parse_args()
    raiz = Path(__file__).resolve().parents[1]
    try:
        erros = conferir(raiz, argumentos.base_ref)
    except subprocess.CalledProcessError as erro:
        sys.stderr.write(f"Falha ao consultar a base Git: {erro.stderr.decode().strip()}\n")
        sys.stderr.write("Atualize a referência com git fetch ou informe --base-ref.\n")
        return 1
    except FileNotFoundError as erro:
        sys.stderr.write(f"Gate de complexidade sem ferramenta: {erro}\n")
        return 1
    if erros:
        sys.stderr.write(f"Complexidade acima de {TETO}:\n" + "\n".join(erros) + "\n")
        return 1
    sys.stdout.write(
        f"Complexidade dentro da régua: ciclomática até {TETO} em {ALVO}/ e nenhuma função nova "
        f"ou piorada acima de {TETO} na cognitiva.\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
