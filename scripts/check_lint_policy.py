"""Confere a adoção gradual de lint sem permitir novas dispensas por arquivo."""

import argparse
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path, PurePosixPath


def ler_excecoes(texto: str) -> set[tuple[str, str]]:
    """Lê apenas caminhos literais e códigos completos da configuração central."""
    configuracao = tomllib.loads(texto)
    if set(configuracao) != {"extend", "lint"} or configuracao["extend"] != "pyproject.toml":
        raise ValueError("ruff.toml deve estender pyproject.toml e conter apenas as dispensas temporárias.")
    lint = configuracao["lint"]
    if not isinstance(lint, dict) or set(lint) != {"extend-per-file-ignores"}:
        raise ValueError("ruff.toml deve conter somente lint.extend-per-file-ignores.")
    tabela = lint["extend-per-file-ignores"]
    if not isinstance(tabela, dict):
        raise TypeError("As dispensas devem formar uma tabela por arquivo.")
    pares = set()
    for caminho, regras in tabela.items():
        partes = PurePosixPath(caminho).parts
        if (
            not caminho.startswith(("src/", "tests/"))
            or PurePosixPath(caminho).as_posix() != caminho
            or ".." in partes
            or any(caractere in caminho for caractere in "*?[]{}!\\")
            or not caminho.endswith(".py")
        ):
            raise ValueError(f"Dispensa exige caminho literal de um arquivo Python em src/ ou tests/: {caminho}")
        if not isinstance(regras, list) or not regras:
            raise ValueError(f"Lista de dispensas vazia ou inválida: {caminho}")
        for regra in regras:
            if not isinstance(regra, str) or not re.fullmatch(r"[A-Z]+[0-9]{3,4}", regra):
                raise ValueError(f"Dispensa exige código completo, sem famílias: {caminho}: {regra}")
            if (caminho, regra) in pares:
                raise ValueError(f"Dispensa duplicada: {caminho}: {regra}")
            pares.add((caminho, regra))
    return pares


def executar_git(raiz: Path, *argumentos: str) -> bytes:
    """Executa consultas ao histórico local, sem buscar referências pela rede."""
    executavel = shutil.which("git")
    if executavel is None:
        raise FileNotFoundError("Git não está disponível no PATH.")
    # A referência chega como argumento separado; nenhum comando usa shell.
    return subprocess.run(  # noqa: S603
        [executavel, *argumentos], cwd=raiz, check=True, capture_output=True,
    ).stdout


def medir_regras(raiz: Path, configuracao: Path) -> list[dict]:
    """Mede src e tests sem as dispensas temporárias do ruff.toml."""
    # Executa apenas o Ruff instalado no ambiente deste processo, sem shell.
    resultado = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "ruff", "check", "--config", str(configuracao),
         "--no-cache", "--output-format", "json", "src", "tests"],
        cwd=raiz, check=False, capture_output=True, text=True,
    )
    if resultado.returncode not in {0, 1}:
        raise ValueError(f"Ruff não conseguiu medir o código: {resultado.stderr.strip()}")
    achados: list[dict] = json.loads(resultado.stdout)
    for achado in achados:
        achado["filename"] = Path(achado["filename"]).relative_to(raiz).as_posix()
    return achados


def pares_dos_achados(achados: list[dict]) -> set[tuple[str, str]]:
    """Agrupa as ocorrências pela unidade de dispensa: arquivo e regra."""
    return {(achado["filename"], achado["code"]) for achado in achados}


def excecoes_da_base(raiz: Path, revisao: str) -> set[tuple[str, str]]:
    """Lê a base ou mede o código antigo na primeira adoção da política."""
    arquivos = executar_git(raiz, "ls-tree", "--name-only", revisao).decode().splitlines()
    if "ruff.toml" in arquivos:
        return ler_excecoes(executar_git(raiz, "show", f"{revisao}:ruff.toml").decode())

    # A primeira adoção também precisa rejeitar dispensas de problemas introduzidos
    # pelo próprio PR. Só o código da base, medido com a nova régua, pode autorizá-las.
    arquivo = executar_git(raiz, "archive", "--format=zip", revisao, "src", "tests")
    with tempfile.TemporaryDirectory(prefix="juscraper-lint-") as temporario:
        destino = Path(temporario)
        with zipfile.ZipFile(io.BytesIO(arquivo)) as pacote:
            for nome in pacote.namelist():
                partes = PurePosixPath(nome).parts
                if ".." in partes or PurePosixPath(nome).is_absolute():
                    raise ValueError(f"Caminho inválido no histórico: {nome}")
                if nome.endswith(".py"):
                    caminho = destino / nome
                    caminho.parent.mkdir(parents=True, exist_ok=True)
                    caminho.write_bytes(pacote.read(nome))
        # --config explícito resolve os padrões relativos ao cwd do snapshot.
        return pares_dos_achados(medir_regras(destino, raiz / "pyproject.toml"))


def conferir(raiz: Path, referencia: str) -> list[str]:
    """Rejeita dispensas novas, obsoletas e violações não dispensadas."""
    excecoes = ler_excecoes((raiz / "ruff.toml").read_text(encoding="utf-8"))
    revisao = executar_git(raiz, "merge-base", "HEAD", referencia).decode().strip()
    anteriores = excecoes_da_base(raiz, revisao)
    achados = medir_regras(raiz, raiz / "pyproject.toml")
    erros = []
    for caminho, regra in sorted(excecoes - anteriores):
        erros.append(f"Nova dispensa proibida: {caminho}: {regra}")
    for caminho, regra in sorted(excecoes - pares_dos_achados(achados)):
        erros.append(f"Remova a dispensa obsoleta: {caminho}: {regra}")
    erros.extend(
        f"{achado['filename']}:{achado['location']['row']}: {achado['code']}: {achado['message']}"
        for achado in achados if (achado["filename"], achado["code"]) not in excecoes
    )
    return erros


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
    except (OSError, ValueError, TypeError) as erro:
        sys.stderr.write(f"Política de lint inválida: {erro}\n")
        return 1
    if erros:
        sys.stderr.write("\n".join(erros) + "\n")
        return 1
    sys.stdout.write("Política de lint válida: nenhuma dispensa nova ou obsoleta; código dentro da régua.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
