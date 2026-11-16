"""Transformação do CHANGELOG.md por scripts/release.py, sem git, tag nem publicação."""

import importlib.util
import re
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
    [(ANTES, None), (ANTES.replace("compare/v0.5.0...HEAD", "releases"), 1), (None, 1)],
    ids=["valido", "sem-link", "sem-arquivo"],
)
def test_dry_run_confere_o_changelog_sem_alterar(tmp_path, monkeypatch, capsys, changelog, codigo):
    """O ``--dry-run`` para antes do git e dos testes; num diretório temporário, só lê os arquivos."""
    (tmp_path / "pyproject.toml").write_text('version = "0.5.0"\n', encoding="utf-8")
    if changelog is not None:
        (tmp_path / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["release.py", "0.6.0", "--dry-run"])

    if codigo is None:
        release.main()
        assert "DRY RUN" in capsys.readouterr().out
    else:
        with pytest.raises(SystemExit) as saida:
            release.main()
        assert saida.value.code == codigo
        assert "CHANGELOG.md não pode ser atualizado" in capsys.readouterr().out
    if changelog is not None:
        assert (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8") == changelog
