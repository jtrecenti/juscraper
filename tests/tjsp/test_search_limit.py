"""Limite de 120 caracteres do campo de busca no CJPG/CJSG do TJSP (refs #35)."""
from unittest.mock import MagicMock

import pytest

from juscraper.courts.tjsp.cjpg_download import cjpg_download
from juscraper.courts.tjsp.cjsg_download import cjsg_download


def _is_length_guard_error(exc: BaseException) -> bool:
    """True se o erro for o ValueError do guard de 120 chars (e não outro ValueError qualquer)."""
    return (
        isinstance(exc, ValueError)
        and "pesquisa" in str(exc)
        and "120" in str(exc)
    )


class TestCjpgSearchLimit:
    def test_120_chars_passes_validation(self):
        # 120 caracteres é exatamente o limite — o guard NÃO deve rejeitar.
        # A execução prossegue e falha downstream (MagicMock / URL inválida);
        # qualquer erro downstream é aceitável, desde que não seja o guard.
        pesquisa = "a" * 120
        with pytest.raises(Exception) as exc_info:
            cjpg_download(
                pesquisa=pesquisa,
                session=MagicMock(),
                u_base="https://example.invalid/",
                download_path="/tmp",
                get_n_pags_callback=None,
            )
        assert not _is_length_guard_error(exc_info.value), (
            f"guard de 120 chars rejeitou indevidamente 120 caracteres: {exc_info.value}"
        )

    def test_121_chars_raises(self):
        pesquisa = "a" * 121
        with pytest.raises(ValueError, match="120 caracteres"):
            cjpg_download(
                pesquisa=pesquisa,
                session=MagicMock(),
                u_base="https://example.invalid/",
                download_path="/tmp",
                get_n_pags_callback=lambda r: 1,
            )


class TestCjsgSearchLimit:
    def test_120_chars_passes_validation(self):
        pesquisa = "a" * 120
        with pytest.raises(Exception) as exc_info:
            cjsg_download(
                pesquisa=pesquisa,
                download_path="/tmp",
                u_base="https://example.invalid/",
                get_n_pags_callback=None,
            )
        assert not _is_length_guard_error(exc_info.value), (
            f"guard de 120 chars rejeitou indevidamente 120 caracteres: {exc_info.value}"
        )

    def test_121_chars_raises(self):
        pesquisa = "a" * 121
        with pytest.raises(ValueError, match="120 caracteres"):
            cjsg_download(
                pesquisa=pesquisa,
                download_path="/tmp",
                u_base="https://example.invalid/",
                get_n_pags_callback=lambda r: 1,
            )
