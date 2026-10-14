"""Barra complexidade acima do teto em src/: ciclomática absoluta, cognitiva por catraca."""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

TETO = 15
ALVO = "src"
CORES_ANSI = re.compile(r"\x1b\[[0-9;]*m")


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


def conferir_ciclomatica(raiz: Path) -> list[str]:
    """Nenhuma função de src/ passa do teto, sem lista de exceções."""
    resultado = subprocess.run(
        [sys.executable, "-m", "lizard", "-C", str(TETO), "-w", ALVO],
        cwd=raiz, check=False, capture_output=True, text=True,
    )
    if resultado.returncode == 0:
        return []
    avisos = [linha for linha in resultado.stdout.splitlines() if "warning:" in linha]
    return avisos or [resultado.stdout.strip() or resultado.stderr.strip()]


def conferir_cognitiva(raiz: Path, base: str) -> list[str]:
    """Função nova acima do teto falha; a que já está acima não pode piorar."""
    comando = [executavel_complexipy(), ALVO, "-mx", str(TETO), "--diff", base, "--ratchet", "--no-ignore"]
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
    return conferir_ciclomatica(raiz) + conferir_cognitiva(raiz, base)


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
