"""scripts/release.py: transformação do CHANGELOG.md e conferências prévias, sem publicação.

O git só roda em repositórios temporários, sem remotos.
"""

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location("release", RAIZ / "scripts" / "release.py")
assert _spec is not None
assert _spec.loader is not None
release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release)

INTRODUCAO = """# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
"""

ANTES = INTRODUCAO + """
## [Unreleased]

Texto de abertura da versão, com crédito a José de Jesus Filho (jjesusfilho).

### Added

- TJSP: `baixar_sentenca` (#451, de vihumelo).

### Fixed

- TJMG: captcha esgotado vira erro.

## [0.5.0] - 2026-10-21

### Added

- Entrada publicada.

[Unreleased]: https://github.com/jtrecenti/juscraper/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/jtrecenti/juscraper/compare/v0.4.0...v0.5.0
"""

DEPOIS = INTRODUCAO + """
## [Unreleased]

## [0.6.0] - 2026-11-16

Texto de abertura da versão, com crédito a José de Jesus Filho (jjesusfilho).

### Added

- TJSP: `baixar_sentenca` (#451, de vihumelo).

### Fixed

- TJMG: captcha esgotado vira erro.

## [0.5.0] - 2026-10-21

### Added

- Entrada publicada.

[Unreleased]: https://github.com/jtrecenti/juscraper/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/jtrecenti/juscraper/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/jtrecenti/juscraper/compare/v0.4.0...v0.5.0
"""

SEM_ENTRADAS = ANTES[:ANTES.index("Texto de abertura")] + "### Added\n\n" + ANTES[ANTES.index("## [0.5.0]"):]


def test_promove_unreleased_preservando_o_resto():
    assert release.promover_unreleased(ANTES, "0.6.0", "2026-11-16") == DEPOIS


def test_changelog_real_do_repositorio_e_promovido():
    """O CHANGELOG.md versionado está no formato que o script espera."""
    conteudo = (RAIZ / "CHANGELOG.md").read_text(encoding="utf-8")

    novo = release.promover_unreleased(conteudo, "99.0.0", "2099-01-01")

    assert "## [Unreleased]\n\n## [99.0.0] - 2099-01-01\n" in novo
    assert "/compare/v99.0.0...HEAD\n[99.0.0]: " in novo


@pytest.mark.parametrize(
    ("conteudo", "versao", "mensagem"),
    [
        (ANTES.replace("## [Unreleased]\n", ""), "0.6.0", "exatamente uma seção"),
        (ANTES + "\n## [Unreleased]\n", "0.6.0", "exatamente uma seção"),
        (ANTES.replace("compare/v0.5.0...HEAD", "releases"), "0.6.0", "precisa do link"),
        (ANTES.replace("## [Unreleased]\n", "") + "\n## [Unreleased]\n", "0.6.0", "precisa do link"),
        (ANTES, "0.5.0", "já tem a seção"),
    ],
    ids=["sem-unreleased", "dois-unreleased", "sem-link", "link-antes-da-secao", "versao-repetida"],
)
def test_formato_inesperado_levanta_erro(conteudo, versao, mensagem):
    with pytest.raises(ValueError, match=mensagem):
        release.promover_unreleased(conteudo, versao, "2026-11-16")


@pytest.mark.parametrize(
    ("changelog", "codigo"),
    [(ANTES, None), (SEM_ENTRADAS, None), (ANTES.replace("compare/v0.5.0...HEAD", "releases"), 1), (None, 1)],
    ids=["valido", "unreleased-vazio", "sem-link", "sem-arquivo"],
)
def test_dry_run_confere_o_changelog_sem_alterar(tmp_path, monkeypatch, capsys, changelog, codigo):
    """O ``--dry-run`` para antes do commit e dos testes; num diretório temporário, só lê os arquivos.

    ``[Unreleased]`` vazio só gera aviso; a tag é conferida à parte, em ``repo_com_tag``.
    """
    (tmp_path / "pyproject.toml").write_text('version = "0.5.0"\n', encoding="utf-8")
    if changelog is not None:
        (tmp_path / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["release.py", "0.6.0", "--dry-run"])
    monkeypatch.setattr(release, "tag_existe", lambda _tag: False)

    if codigo is None:
        release.main()
        saida = capsys.readouterr().out
        assert "DRY RUN" in saida
        assert ("[Unreleased] do CHANGELOG.md está vazio" in saida) is (changelog is SEM_ENTRADAS)
    else:
        with pytest.raises(SystemExit) as saida:
            release.main()
        assert saida.value.code == codigo
        assert "CHANGELOG.md não pode ser atualizado" in capsys.readouterr().out
    if changelog is not None:
        assert (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8") == changelog


@pytest.mark.parametrize(
    ("conteudo", "vazio"),
    [
        (ANTES, False),
        (SEM_ENTRADAS, True),
        (SEM_ENTRADAS.replace("### Added\n\n", ""), True),
        (INTRODUCAO + "\n## [Unreleased]\n\n[Unreleased]: https://x/compare/v0.1.0...HEAD\n", True),
        (INTRODUCAO + "\n## [Unreleased]\n\n- Item.\n\n[Unreleased]: https://x/compare/v0.1.0...HEAD\n", False),
    ],
    ids=["com-entradas", "so-subtitulo", "sem-nada", "unica-secao-vazia", "unica-secao-com-item"],
)
def test_unreleased_vazio(conteudo, vazio):
    assert release.unreleased_vazio(conteudo) is vazio


def _git(repo, *args):
    return subprocess.run(
        ["git", "-c", "user.name=Teste", "-c", "user.email=teste@example.com", "-c", "commit.gpgsign=false", *args],
        cwd=repo, check=True, capture_output=True, text=True,
    ).stdout


@pytest.fixture
def repo_com_tag(tmp_path, monkeypatch):
    """Repositório git temporário, sem remotos, com o release 0.5.0 commitado e a tag v0.6.0."""
    (tmp_path / "pyproject.toml").write_text('version = "0.5.0"\n', encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text(ANTES, encoding="utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "inicial")
    _git(tmp_path, "tag", "v0.6.0")
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.usefixtures("repo_com_tag")
def test_tag_existe_consulta_refs_locais():
    assert release.tag_existe("v0.6.0")
    assert not release.tag_existe("v0.7.0")


@pytest.mark.parametrize("argumentos", [["--skip-tests"], ["--dry-run"]], ids=["release", "dry-run"])
def test_tag_existente_para_antes_de_alterar_arquivos(repo_com_tag, monkeypatch, capsys, argumentos):
    head = _git(repo_com_tag, "rev-parse", "HEAD")
    monkeypatch.setattr(sys, "argv", ["release.py", "0.6.0", *argumentos])

    with pytest.raises(SystemExit) as saida:
        release.main()

    assert saida.value.code == 1
    assert "A tag v0.6.0 já existe" in capsys.readouterr().out
    assert _git(repo_com_tag, "status", "--porcelain") == ""
    assert _git(repo_com_tag, "rev-parse", "HEAD") == head
