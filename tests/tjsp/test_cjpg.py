"""
Tests for TJSP CJPG functionality.
Includes both integration and unit tests.
"""
import logging
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, call

import pandas as pd
import pytest

import juscraper
from juscraper.courts._esaj.cjpg_download import _TIMEOUT, _normalize_pages, cjpg_download
from juscraper.courts._esaj.cjpg_parse import cjpg_n_pags, cjpg_n_results, cjpg_parse_manager, cjpg_parse_single
from tests._helpers import load_sample, load_sample_bytes


def _pagina(corpo: str) -> str:
    """Envelope mínimo para os casos de borda que nenhuma página real do eSAJ traz."""
    return f"<!DOCTYPE html><html><body>{corpo}</body></html>"


def _linhas_de_resultado(quantidade: int) -> str:
    linhas = "".join(f'<tr class="fundocinza1"><td>processo {n}</td></tr>' for n in range(1, quantidade + 1))
    return f'<div id="divDadosResultado"><table>{linhas}</table></div>'


# Cascata de ``cjpg_n_results`` em layouts que a página atual do eSAJ não
# traz: célula ``bgcolor`` sem a palavra "resultado", resumo "Página N, total
# X" e texto em que só o maior número serve. O HTML mínimo fica aqui, e não em
# ``samples/``, porque não é resposta do tribunal.
_CASCATA_CONTAGEM = {
    "bgcolor_legacy": (
        '<table><tr><td bgcolor="#EEEEEE">Mostrando 1 a 10 de 25 ocorrências</td></tr></table>',
        25,
    ),
    "page_summary": ("<table><tr><td>Página 1, total 31 registros encontrados</td></tr></table>", 31),
    "max_number_fallback": (
        "<table><tr><td>Resultados exibidos: itens 1 a 10; total = 47 ocorrências</td></tr></table>",
        47,
    ),
}


@pytest.mark.integration
class TestCJPGIntegration:
    """Integration tests for CJPG that hit the real website."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test fixtures."""
        self.scraper = juscraper.scraper('tjsp')
        yield

    def test_cjpg_basic_search(self):
        """Test basic CJPG search functionality."""
        results = self.scraper.cjpg('golpe do pix', paginas=range(1, 2))

        assert isinstance(results, pd.DataFrame)
        assert len(results) >= 0

    def test_cjpg_with_filters(self):
        """Test CJPG search with filters."""
        results = self.scraper.cjpg(
            pesquisa='direito',
            classe=['Procedimento Comum Cível'],
            paginas=range(1, 2)
        )

        assert isinstance(results, pd.DataFrame)

    def test_cjpg_pagination(self):
        """Test CJPG pagination."""
        results = self.scraper.cjpg('direito', paginas=range(1, 3))

        assert isinstance(results, pd.DataFrame)
        assert len(results) >= 0

    def test_cjpg_date_filters(self):
        """Test CJPG with date filters."""
        results = self.scraper.cjpg(
            'direito',
            data_julgamento_inicio='01/01/2023',
            data_julgamento_fim='31/12/2023',
            paginas=range(1, 2),
        )
        assert isinstance(results, pd.DataFrame)

    def test_cjpg_result_structure(self):
        """Test that CJPG results have expected structure."""
        results = self.scraper.cjpg('direito', paginas=range(1, 2))

        assert isinstance(results, pd.DataFrame)

        if len(results) > 0:
            # Check for expected columns
            assert len(results.columns) > 0


class TestCJPGUnit:
    """Unit tests for CJPG parsing functions."""

    def test_cjpg_n_pags_novo_formato(self):
        """Página real do TJSP, com "Resultados 1 a 10 de N".

        Regression for the bug where TJSP changed the pagination text from
        "Mostrando 1 a 10 de N resultados" to "Resultados 1 a 10 de N",
        breaking the original regex (which required "resultado" after the
        number).
        """
        html = load_sample('tjsp', 'cjpg/results_normal_page_01.html')
        # "Resultados 1 a 10 de 3565472" → ceil(3565472/10) = 356548
        assert cjpg_n_pags(html) == 356548

    @pytest.mark.parametrize("n_results,expected_pags", [
        (1, 1),       # 1 result -> 1 page
        (10, 1),      # exact multiple: 1 page (was incorrectly 2 in old code)
        (11, 2),      # 2 pages
        (20, 2),      # exact multiple
        (25, 3),      # legacy fixture value
        (39764, 3977),  # current TJSP real value
    ])
    def test_cjpg_n_pags_ceiling(self, n_results, expected_pags):
        """Ceiling division: results / 10 rounded up. Covers exact multiples."""
        html = (
            '<html><body><table><tr><td>'
            f'Resultados 1 a 10 de {n_results}'
            '</td></tr></table></body></html>'
        )
        assert cjpg_n_pags(html) == expected_pags

    def test_cjpg_n_pags_missing_selector(self):
        """Test that missing pagination selector raises ValueError."""
        html = "<html><body><p>No pagination</p></body></html>"
        with pytest.raises(ValueError, match="Não foi possível encontrar"):
            cjpg_n_pags(html)

    def test_cjpg_parse_single(self):
        """Test parsing a single CJPG results page."""
        df = cjpg_parse_single(Path(__file__).parent / "samples/cjpg/single_page.html")

        assert len(df) == 2  # "jurimétrica" trouxe duas sentenças
        assert df.iloc[0]['id_processo'] == '0003880-96.2022.8.26.0529'
        assert df.iloc[0]['cd_processo'] == 'EP0005URT0000'
        assert df.iloc[0]['classe'] == 'Cumprimento de sentença'
        # A segunda sentença vem sem a linha "Classe:".
        assert pd.isna(df.iloc[1]['classe'])
        assert df['decisao'].str.startswith('SENTENÇA').all()

    def test_cjpg_parse_manager_directory(self):
        """Test parsing multiple CJPG files from directory."""
        html = load_sample('tjsp', 'cjpg/single_page.html')

        with tempfile.TemporaryDirectory() as temp_dir:
            file1 = Path(temp_dir) / 'page1.html'
            file2 = Path(temp_dir) / 'page2.html'

            with file1.open('w', encoding='utf-8') as f:
                f.write(html)
            with file2.open('w', encoding='utf-8') as f:
                f.write(html)

            df = cjpg_parse_manager(temp_dir)

            assert isinstance(df, pd.DataFrame)
            # 2 processes per file * 2 files = 4 total
            assert len(df) == 4

    def test_cjpg_parse_empty_page(self):
        """Test parsing an empty CJPG page."""
        html = '<html><body><div id="divDadosResultado"></div></body></html>'

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            temp_path = f.name

        try:
            df = cjpg_parse_single(temp_path)
            assert isinstance(df, pd.DataFrame)
            assert len(df) == 0
        finally:
            Path(temp_path).unlink()


class TestCJPGNResults:
    """Tests do helper :func:`cjpg_n_results` (issue #92)."""

    def test_extracts_raw_count_novo_formato(self):
        """Página real: 'Resultados 1 a 10 de 3565472' -> 3565472."""
        html = load_sample("tjsp", "cjpg/results_normal_page_01.html")
        assert cjpg_n_results(html) == 3565472

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "A cascata pega a célula de layout com 'Resultados', e não a do bgcolor; "
            "o '\\d+$' casa com o link da página '1' no fim dela."
        ),
    )
    def test_single_page_conta_os_dois_resultados(self):
        """A página real com "Resultados 1 a 2 de 2" deveria contar 2."""
        html = load_sample("tjsp", "cjpg/single_page.html")
        assert cjpg_n_results(html) == 2

    @pytest.mark.parametrize(("corpo", "expected"), _CASCATA_CONTAGEM.values(), ids=_CASCATA_CONTAGEM.keys())
    def test_selector_and_text_cascades(self, corpo, expected):
        """Characterizes the CJPG-only selectors and shared text cascade."""
        assert cjpg_n_results(_pagina(corpo)) == expected

    def test_counts_result_rows_when_pagination_marker_is_missing(self):
        assert cjpg_n_results(_pagina(_linhas_de_resultado(3))) == 3

    def test_raises_when_full_page_has_no_pagination_marker(self):
        html = _pagina(_linhas_de_resultado(10))
        with pytest.raises(ValueError, match=r"página completa.*sem marcador"):
            cjpg_n_results(html)

    def test_captcha_error_takes_precedence_over_zero_marker(self):
        html = _pagina('<div class="mensagemErro">Falha na verificação do captcha. Nenhum resultado encontrado.</div>')
        with pytest.raises(ValueError, match="Captcha não foi resolvido"):
            cjpg_n_results(html)

    def test_search_form_without_zero_marker_raises_missing_selector(self):
        """The real CJPG form has an empty ``id`` and also appears on result
        pages, so the parser does not claim the search stayed on the form.
        A form page without the zero-results notice gets the generic error.
        """
        zero_notice = "Não foi encontrado nenhum resultado correspondente à busca realizada."
        html = load_sample("tjsp", "cjpg/no_results.html")
        assert zero_notice in html
        html = html.replace(zero_notice, "")
        with pytest.raises(ValueError, match="Não foi possível encontrar o seletor"):
            cjpg_n_results(html)

    def test_empty_results_container_still_raises_missing_selector(self):
        html = _pagina('<div id="divDadosResultado"></div>')
        with pytest.raises(ValueError, match="Não foi possível encontrar o seletor"):
            cjpg_n_results(html)

    def test_raises_when_pagination_marker_has_no_number(self):
        html = _pagina("<table><tr><td>Resultados temporariamente indisponíveis</td></tr></table>")
        with pytest.raises(ValueError, match="Não foi possível extrair o número de resultados"):
            cjpg_n_results(html)

    @pytest.mark.parametrize(
        ("counter", "expected"),
        [(cjpg_n_results, 3565472), (cjpg_n_pags, 356548)],
    )
    def test_accepts_response_content_bytes(self, counter, expected):
        html = load_sample_bytes("tjsp", "cjpg/results_normal_page_01.html")
        assert counter(html) == expected

    def test_zero_results_returns_zero(self):
        html = load_sample("tjsp", "cjpg/no_results.html")
        assert cjpg_n_results(html) == 0

    def test_n_pags_zero_sem_resultados(self):
        """Busca sem resultados dá 0 páginas; o caso com resultados está em ``test_cjpg_n_pags_novo_formato``."""
        assert cjpg_n_pags(load_sample("tjsp", "cjpg/no_results.html")) == 0


class TestCJPGDownload1Based:
    """Unit tests for CJPG download with 1-based pagination using mocks."""

    def _make_mock_response(self, text="<html>page</html>"):
        mock = MagicMock()
        mock.text = text
        mock.content = text.encode('utf-8')
        return mock

    def _download_with_mocks(self, tmp_path, mocker, *, n_pags, paginas=None, sleep_time=0):
        """Run the internal downloader while retaining its collaborators."""
        mock_session = MagicMock()
        r0_response = self._make_mock_response("<html>page1</html>")
        page_response = self._make_mock_response("<html>page2+</html>")
        mock_session.get.side_effect = [r0_response] + [page_response] * (n_pags + 10)
        count_pages = mocker.patch(
            "juscraper.courts._esaj.cjpg_download.cjpg_n_pags",
            return_value=n_pags,
        )

        path = cjpg_download(
            pesquisa="teste",
            session=mock_session,
            u_base="https://esaj.tjsp.jus.br/",
            download_path=str(tmp_path),
            sleep_time=sleep_time,
            paginas=paginas,
        )

        saved_files = sorted(file.name for file in Path(path).iterdir())
        trocar_urls = [
            item.args[0]
            for item in mock_session.get.call_args_list[1:]
            if "trocarDePagina" in item.args[0]
        ]
        return path, saved_files, trocar_urls, mock_session, r0_response, count_pages

    def test_default_all_pages(self, tmp_path, mocker):
        """Default (None) downloads all 3 pages: saves 00001, 00002, 00003."""
        _, files, urls, _, _, _ = self._download_with_mocks(tmp_path, mocker, n_pags=3)
        assert files == ["cjpg_00001.html", "cjpg_00002.html", "cjpg_00003.html"]
        assert len(urls) == 2  # trocarDePagina for pages 2 and 3

    def test_single_page(self, tmp_path, mocker):
        """range(1, 2) downloads only page 1."""
        _, files, urls, _, _, _ = self._download_with_mocks(
            tmp_path,
            mocker,
            n_pags=3,
            paginas=range(1, 2),
        )
        assert files == ["cjpg_00001.html"]
        assert len(urls) == 0  # no trocarDePagina calls

    def test_three_pages(self, tmp_path, mocker):
        """range(1, 4) downloads pages 1, 2, 3."""
        _, files, urls, _, _, _ = self._download_with_mocks(
            tmp_path,
            mocker,
            n_pags=5,
            paginas=range(1, 4),
        )
        assert files == ["cjpg_00001.html", "cjpg_00002.html", "cjpg_00003.html"]
        assert len(urls) == 2

    def test_custom_range(self, tmp_path, mocker):
        """range(6, 11) downloads pages 6-10 (no page 1)."""
        _, files, urls, _, _, _ = self._download_with_mocks(
            tmp_path,
            mocker,
            n_pags=20,
            paginas=range(6, 11),
        )
        assert files == [f"cjpg_{p:05d}.html" for p in range(6, 11)]
        assert len(urls) == 5  # all via trocarDePagina

    def test_exceeds_available(self, tmp_path, mocker):
        """range(1, 101) with only 3 pages available: downloads only 1, 2, 3."""
        _, files, urls, _, _, _ = self._download_with_mocks(
            tmp_path,
            mocker,
            n_pags=3,
            paginas=range(1, 101),
        )
        assert files == ["cjpg_00001.html", "cjpg_00002.html", "cjpg_00003.html"]
        assert len(urls) == 2

    def test_counter_receives_first_page_content_and_return_is_str(self, tmp_path, mocker):
        path, _, _, _, r0_response, count_pages = self._download_with_mocks(
            tmp_path,
            mocker,
            n_pags=1,
            paginas=[1],
        )

        assert isinstance(path, str)
        count_pages.assert_called_once_with(r0_response.content)

    def test_zero_pages_still_saves_first_page(self, tmp_path, mocker):
        path, files, _, mock_session, _, _ = self._download_with_mocks(
            tmp_path,
            mocker,
            n_pags=0,
            paginas=[3],
        )

        assert files == ["cjpg_00001.html"]
        assert Path(path, "cjpg_00001.html").read_text(encoding="utf-8") == "<html>page1</html>"
        assert mock_session.get.call_count == 1

    def test_sparse_page_list_discards_unavailable_pages(self, tmp_path, mocker):
        sleep = mocker.patch("juscraper.courts._esaj.cjpg_download.time.sleep")

        _, files, _, mock_session, _, _ = self._download_with_mocks(
            tmp_path,
            mocker,
            n_pags=3,
            paginas=[1, 3, 99],
            sleep_time=0.25,
        )

        assert files == ["cjpg_00001.html", "cjpg_00003.html"]
        assert mock_session.get.call_args_list[1:] == [
            call("https://esaj.tjsp.jus.br/cjpg/trocarDePagina.do?pagina=3&conversationId=", timeout=_TIMEOUT)
        ]
        sleep.assert_called_once_with(0.25)

    def test_pagina_zero_repetida_e_alem_do_total(self, tmp_path, mocker, caplog):
        """Página 0 e além do total saem num aviso no logger do tribunal; a repetida baixa uma vez."""
        with caplog.at_level(logging.WARNING, logger="juscraper.tjsp"):
            _, files, urls, _, _, _ = self._download_with_mocks(
                tmp_path,
                mocker,
                n_pags=3,
                paginas=[0, 2, 2, 99],
            )

        assert files == ["cjpg_00002.html"]
        assert urls == ["https://esaj.tjsp.jus.br/cjpg/trocarDePagina.do?pagina=2&conversationId="]
        assert [(r.name, r.getMessage()) for r in caplog.records if r.name == "juscraper.tjsp"] == [
            ("juscraper.tjsp", "TJSP: páginas 0, 99 fora do intervalo 1-3"),
        ]

    def test_aviso_sai_no_logger_do_tribunal_de_u_base(self, caplog):
        with caplog.at_level(logging.WARNING, logger="juscraper.tjms"):
            assert _normalize_pages([1, 5], 2, "https://esaj.tjms.jus.br/") == [1]

        assert [(r.name, r.getMessage()) for r in caplog.records] == [
            ("juscraper.tjms", "TJMS: página 5 fora do intervalo 1-2"),
        ]

    def test_range_step_preserves_page_order_and_request_urls(self, tmp_path, mocker):
        sleep = mocker.patch("juscraper.courts._esaj.cjpg_download.time.sleep")

        _, files, _, mock_session, _, _ = self._download_with_mocks(
            tmp_path,
            mocker,
            n_pags=5,
            paginas=range(1, 8, 2),
            sleep_time=0.4,
        )

        assert files == [
            "cjpg_00001.html",
            "cjpg_00003.html",
            "cjpg_00005.html",
        ]
        assert mock_session.get.call_args_list[1:] == [
            call("https://esaj.tjsp.jus.br/cjpg/trocarDePagina.do?pagina=3&conversationId=", timeout=_TIMEOUT),
            call("https://esaj.tjsp.jus.br/cjpg/trocarDePagina.do?pagina=5&conversationId=", timeout=_TIMEOUT),
        ]
        assert sleep.call_args_list == [call(0.4), call(0.4)]

    def test_count_error_saves_debug_html_and_preserves_cause(self, tmp_path, mocker, caplog):
        mock_session = MagicMock()
        mock_session.get.return_value = self._make_mock_response("<html>diagnostico</html>")
        upstream_error = RuntimeError("falha ao contar páginas")
        mocker.patch(
            "juscraper.courts._esaj.cjpg_download.cjpg_n_pags",
            side_effect=upstream_error,
        )
        # A pasta de download ainda não existe: o diagnóstico precisa criá-la
        # junto com ``cjpg_debug``, senão o usuário recebe FileNotFoundError
        # no lugar do ValueError que aponta para o HTML salvo.
        download_path = tmp_path / "ainda_nao_existe"

        with (
            caplog.at_level(logging.ERROR, logger="juscraper.cjpg_download"),
            pytest.raises(ValueError, match="falha ao contar páginas") as exc_info,
        ):
            cjpg_download(
                pesquisa="teste",
                session=mock_session,
                u_base="https://esaj.tjsp.jus.br/",
                download_path=str(download_path),
            )

        assert exc_info.value.__cause__ is upstream_error
        debug_files = list(Path(download_path, "cjpg_debug").glob("cjpg_primeira_pagina_*.html"))
        assert len(debug_files) == 1
        assert debug_files[0].read_text(encoding="utf-8") == "<html>diagnostico</html>"
        assert str(debug_files[0]) in str(exc_info.value)
        assert any(
            record.name == "juscraper.cjpg_download"
            and record.levelno == logging.ERROR
            and "Erro ao extrair número de páginas" in record.getMessage()
            and str(debug_files[0]) in record.getMessage()
            for record in caplog.records
        )


class TestCJPGDateRangeValidation:
    """Pre-request date-range validation for the eSAJ 1-year limit (#91)."""

    def _patched_scraper(self):
        """Build a TJSPScraper whose session.get would fail the test if called."""
        scraper = juscraper.scraper('tjsp')
        # Replace session with a MagicMock that records calls — if validation
        # fails to short-circuit, .get() would be invoked and we can detect it.
        scraper.session = MagicMock()
        return scraper

    def test_range_over_one_year_raises_before_request(self):
        scraper = self._patched_scraper()
        with pytest.raises(ValueError, match="no máximo 1 ano"):
            scraper.cjpg_download(
                pesquisa="direito",
                data_julgamento_inicio="01/01/2020",
                data_julgamento_fim="31/12/2021",
            )
        # Crucially, nothing hit the network.
        scraper.session.get.assert_not_called()
        scraper.session.post.assert_not_called()

    def test_invalid_format_raises_before_request(self):
        # ISO + BR mixed are both accepted (coerced to backend format, refs #173).
        # Use a format the coercer cannot recognize (e.g. dotted) so the
        # downstream validate_intervalo_datas raises the expected error.
        scraper = self._patched_scraper()
        with pytest.raises(ValueError, match="Formato esperado"):
            scraper.cjpg_download(
                pesquisa="direito",
                data_julgamento_inicio="01.01.2020",
                data_julgamento_fim="31.12.2020",
            )
        scraper.session.get.assert_not_called()

    def test_inicio_after_fim_raises_before_request(self):
        scraper = self._patched_scraper()
        with pytest.raises(ValueError, match="posterior"):
            scraper.cjpg_download(
                pesquisa="direito",
                data_julgamento_inicio="31/12/2023",
                data_julgamento_fim="01/01/2023",
            )
        scraper.session.get.assert_not_called()

    def test_valid_one_year_window_proceeds_to_request(self):
        """A valid 1-year window should NOT short-circuit; the download
        proceeds and the mocked session receives the first GET."""
        scraper = self._patched_scraper()
        # Make the mock raise after the first .get() so we don't actually
        # exercise the parsing flow — we only care that validation passed.
        scraper.session.get.side_effect = RuntimeError("short-circuit after validate")
        with pytest.raises(RuntimeError, match="short-circuit"):
            scraper.cjpg_download(
                pesquisa="direito",
                data_julgamento_inicio="01/01/2023",
                data_julgamento_fim="31/12/2023",
            )
        assert scraper.session.get.called


def test_cjpg_download_usa_diretorio_sem_alterar_download_path(tmp_path, mocker):
    """``diretorio`` deve valer somente para a chamada atual."""
    scraper = juscraper.scraper("tjsp", download_path=str(tmp_path / "padrao"))
    alternativo = tmp_path / "alternativo"
    download = mocker.patch(
        "juscraper.courts._esaj.cjpg.cjpg_download_mod",
        return_value=str(alternativo),
    )

    resultado = scraper.cjpg_download(paginas=1, diretorio=str(alternativo))

    assert resultado == str(alternativo)
    assert scraper.download_path == str(tmp_path / "padrao")
    assert download.call_args.kwargs["download_path"] == str(alternativo)


def test_cjpg_download_sem_diretorio_usa_download_path(tmp_path, mocker):
    """Sem ``diretorio``, o caminho configurado no scraper continua valendo."""
    caminho = tmp_path / "padrao"
    scraper = juscraper.scraper("tjsp", download_path=str(caminho))
    download = mocker.patch(
        "juscraper.courts._esaj.cjpg.cjpg_download_mod",
        return_value=str(caminho),
    )

    scraper.cjpg_download(paginas=1)

    assert scraper.download_path == str(caminho)
    assert download.call_args.kwargs["download_path"] == str(caminho)


@pytest.mark.parametrize("tribunal", ["tjsp", "tjms"])
def test_cjpg_download_passa_a_sigla_do_tribunal_ao_download(tmp_path, mocker, tribunal):
    download = mocker.patch(
        "juscraper.courts._esaj.cjpg.cjpg_download_mod", return_value=str(tmp_path),
    )

    juscraper.scraper(tribunal, download_path=str(tmp_path)).cjpg_download(paginas=1)

    assert download.call_args.kwargs["tribunal"] == tribunal.upper()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
