"""scripts/release.py: transformação do CHANGELOG.md e conferências prévias, sem publicação.

O git só roda em repositórios temporários; o ``origin``, quando existe, é um repositório
local temporário.
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

ORIGIN_INACESSIVEL = "/caminho/que/nao/existe"

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
        [
            "git", "-c", "user.name=Teste", "-c", "user.email=teste@example.com",
            "-c", "commit.gpgsign=false", "-c", "tag.gpgSign=false", *args,
        ],
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


@pytest.fixture
def repo_com_origin(repo_com_tag, tmp_path_factory):
    """``repo_com_tag`` com um ``origin`` local onde só existe a tag v0.7.0."""
    origin = tmp_path_factory.mktemp("origin")
    _git(origin, "init", "-q", "--bare")
    _git(repo_com_tag, "remote", "add", "origin", str(origin))
    _git(repo_com_tag, "tag", "-a", "v0.7.0", "-m", "Release version 0.7.0")
    _git(repo_com_tag, "push", "-q", "origin", "v0.7.0")
    _git(repo_com_tag, "tag", "-d", "v0.7.0")
    return repo_com_tag


@pytest.mark.usefixtures("repo_com_origin")
def test_tag_existe_consulta_refs_locais_e_origin():
    assert release.tag_existe("v0.6.0") is True
    assert release.tag_existe("v0.7.0") is True
    assert release.tag_existe("v0.8.0") is False


@pytest.mark.parametrize("origin", [None, ORIGIN_INACESSIVEL], ids=["sem-origin", "origin-inacessivel"])
def test_tag_existe_levanta_erro_se_o_origin_falha(repo_com_tag, origin):
    if origin is not None:
        _git(repo_com_tag, "remote", "add", "origin", origin)

    assert release.tag_existe("v0.6.0") is True
    with pytest.raises(RuntimeError, match="Não foi possível consultar as tags do origin"):
        release.tag_existe("v0.7.0")


def _main_para_sem_alterar(repo, monkeypatch, capsys, argv):
    """Roda ``main()``, que deve sair com 1, e confere árvore, HEAD e tags intactos; devolve a saída."""
    estado = [_git(repo, "rev-parse", "HEAD"), _git(repo, "tag")]
    monkeypatch.setattr(sys, "argv", ["release.py", *argv])

    with pytest.raises(SystemExit) as saida:
        release.main()

    assert saida.value.code == 1
    assert _git(repo, "status", "--porcelain") == ""
    assert [_git(repo, "rev-parse", "HEAD"), _git(repo, "tag")] == estado
    return capsys.readouterr().out


@pytest.mark.parametrize("argumentos", [["--skip-tests"], ["--dry-run"]], ids=["release", "dry-run"])
@pytest.mark.parametrize("versao", ["0.6.0", "0.7.0"], ids=["tag-local", "tag-so-no-origin"])
def test_tag_existente_para_antes_de_alterar_arquivos(repo_com_origin, monkeypatch, capsys, argumentos, versao):
    saida = _main_para_sem_alterar(repo_com_origin, monkeypatch, capsys, [versao, *argumentos])

    assert f"A tag v{versao} já existe" in saida


def test_origin_inacessivel_para_o_release_antes_de_alterar_arquivos(repo_com_tag, monkeypatch, capsys):
    _git(repo_com_tag, "remote", "add", "origin", ORIGIN_INACESSIVEL)

    saida = _main_para_sem_alterar(repo_com_tag, monkeypatch, capsys, ["0.7.0", "--skip-tests"])

    assert "nenhum arquivo foi alterado" in saida


def test_origin_inacessivel_so_avisa_no_dry_run(repo_com_tag, monkeypatch, capsys):
    _git(repo_com_tag, "remote", "add", "origin", ORIGIN_INACESSIVEL)
    monkeypatch.setattr(sys, "argv", ["release.py", "0.7.0", "--dry-run"])

    release.main()

    saida = capsys.readouterr().out
    assert "Aviso: o dry run segue sem conferir a tag v0.7.0 no origin" in saida
    assert "DRY RUN" in saida
    assert _git(repo_com_tag, "status", "--porcelain") == ""


def test_lint_roda_o_pre_commit_e_falha_antes_de_alterar_a_versao(repo_com_origin, monkeypatch, capsys):
    """Sem ``--skip-tests``, o lint é o pre-commit e, se ele falha, a versão não é alterada.

    A falha é simulada; os hooks reais que corrigem arquivos podem deixar essas correções na árvore.
    """
    executar = release.run_command
    comandos = []

    def run_command(cmd, *, check=True):
        comandos.append(cmd)
        if "pre-commit" in cmd:
            return executar("false", check=check)
        return executar(cmd, check=check)

    monkeypatch.setattr(release, "run_command", run_command)

    _main_para_sem_alterar(repo_com_origin, monkeypatch, capsys, ["0.8.0"])

    assert [cmd for cmd in comandos if not cmd.startswith("git ")] == ["SKIP=pytest uv run pre-commit run --all-files"]
