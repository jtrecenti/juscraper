#!/usr/bin/env python3
"""
Script para automatizar o processo de release do juscraper.
"""

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def run_command(cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    """Execute um comando shell."""
    print(f"Executando: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        print(f"Erro ao executar comando: {cmd}")
        print(f"Stdout: {result.stdout}")
        print(f"Stderr: {result.stderr}")
        sys.exit(1)
    return result


def get_current_version() -> str:
    """Obtém a versão atual do pyproject.toml."""
    pyproject_path = Path("pyproject.toml")
    if not pyproject_path.exists():
        print("Arquivo pyproject.toml não encontrado!")
        sys.exit(1)

    content = pyproject_path.read_text(encoding="utf-8")
    match = re.search(r'version = "([^"]+)"', content)
    if not match:
        print("Versão não encontrada no pyproject.toml!")
        sys.exit(1)

    return match.group(1)


def update_version(new_version: str) -> None:
    """Atualiza a versão no pyproject.toml."""
    pyproject_path = Path("pyproject.toml")
    content = pyproject_path.read_text(encoding="utf-8")

    # Atualiza a versão
    content = re.sub(
        r'version = "[^"]+"',
        f'version = "{new_version}"',
        content
    )

    pyproject_path.write_text(content, encoding="utf-8")
    print(f"Versão atualizada para {new_version}")


def promover_unreleased(conteudo: str, versao: str, data: str) -> str:
    """Transforma ``[Unreleased]`` na seção ``[versao] - data`` do CHANGELOG.

    Segue o passo 2 do método 2 do PUBLISHING.md: as entradas de ``[Unreleased]``
    passam à versão nova, um ``[Unreleased]`` vazio fica acima dela e, nos links do
    fim do arquivo, ``[Unreleased]`` passa a comparar a partir da tag nova, que
    ganha o link da comparação com a tag anterior. O resto do texto não muda.
    Levanta ``ValueError`` quando falta a seção ou o link de ``[Unreleased]`` ou
    quando a versão já está no arquivo.
    """
    if re.search(rf"^## \[{re.escape(versao)}\]", conteudo, flags=re.MULTILINE):
        raise ValueError(f"CHANGELOG.md já tem a seção [{versao}].")
    secoes = list(re.finditer(r"^## \[Unreleased\][ \t]*$", conteudo, flags=re.MULTILINE))
    if len(secoes) != 1:
        raise ValueError("CHANGELOG.md precisa de exatamente uma seção '## [Unreleased]'.")
    secao = secoes[0]
    link = re.search(
        r"^\[Unreleased\]: (?P<base>\S+/compare/)(?P<anterior>\S+)\.\.\.HEAD[ \t]*$",
        conteudo,
        flags=re.MULTILINE,
    )
    if link is None or link.start() < secao.end():
        raise ValueError("CHANGELOG.md precisa do link '[Unreleased]: .../compare/<tag>...HEAD' no fim.")

    base, anterior = link["base"], link["anterior"]
    return (
        conteudo[:secao.end()]
        + f"\n\n## [{versao}] - {data}"
        + conteudo[secao.end():link.start()]
        + f"[Unreleased]: {base}v{versao}...HEAD\n[{versao}]: {base}{anterior}...v{versao}"
        + conteudo[link.end():]
    )


def preparar_changelog(version: str) -> str:
    """Lê o CHANGELOG.md e devolve o texto com ``[Unreleased]`` promovido à versão nova.

    Encerra o script se o arquivo faltar ou estiver fora do formato esperado.
    """
    try:
        conteudo = Path("CHANGELOG.md").read_text(encoding="utf-8")
        return promover_unreleased(conteudo, version, datetime.now().strftime("%Y-%m-%d"))
    except (OSError, ValueError) as erro:
        print(f"CHANGELOG.md não pode ser atualizado: {erro}")
        sys.exit(1)


def main():
    """Entry point for the release script."""
    parser = argparse.ArgumentParser(description="Script de release do juscraper")
    parser.add_argument("version", help="Nova versão (ex: 0.2.0)")
    parser.add_argument("--dry-run", action="store_true", help="Apenas simula as ações")
    parser.add_argument("--skip-tests", action="store_true", help="Pula a execução dos testes")

    args = parser.parse_args()

    # Validação da versão
    if not re.match(r'^\d+\.\d+\.\d+$', args.version):
        print("Formato de versão inválido! Use o formato: X.Y.Z")
        sys.exit(1)

    current_version = get_current_version()
    print(f"Versão atual: {current_version}")
    print(f"Nova versão: {args.version}")

    # Confere o CHANGELOG.md antes de qualquer alteração, inclusive no dry run
    changelog = preparar_changelog(args.version)

    if args.dry_run:
        print("=== MODO DRY RUN - Nenhuma alteração será feita ===")
        return

    # Verifica se o repositório está limpo
    result = run_command("git status --porcelain")
    if result.stdout.strip():
        print("Repositório tem alterações não commitadas!")
        print("Faça commit das alterações antes de fazer o release.")
        sys.exit(1)

    # Executa testes e linting se não foi solicitado para pular
    if not args.skip_tests:
        print("Executando linting...")
        run_command("uv run pylint src/juscraper/")
        run_command("uv run isort --check-only src/ tests/")
        run_command("uv run flake8 src/ tests/")

        print("Executando testes...")
        run_command("uv run pytest tests/ -v")

    # Atualiza versão
    update_version(args.version)

    # Atualiza changelog
    Path("CHANGELOG.md").write_text(changelog, encoding="utf-8")
    print(f"CHANGELOG.md atualizado com versão {args.version}")

    # Commit das alterações
    run_command('git add pyproject.toml CHANGELOG.md')
    run_command(f'git commit -m "chore: bump version to {args.version}"')

    # Cria tag
    run_command(f'git tag -a v{args.version} -m "Release version {args.version}"')

    print(f"\n✅ Release {args.version} preparado!")
    print("Para finalizar:")
    print("1. git push origin main")
    print(f"2. git push origin v{args.version}")
    print(f"3. Criar release no GitHub com a tag v{args.version}")


if __name__ == "__main__":
    main()
