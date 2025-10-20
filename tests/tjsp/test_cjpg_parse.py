"""Tests for CJPG parsing functions."""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.juscraper.courts.tjsp.cjpg_parse import cjpg_n_pags


def test_cjpg_n_pags_with_results():
    """Test cjpg_n_pags with valid results."""
    html = """
    <html>
    <body>
    <div id="divDadosResultado">
        <tr class="fundocinza1"><td>Process 1</td></tr>
        <tr class="fundocinza1"><td>Process 2</td></tr>
    </div>
    <table>
    <tr bgcolor="#EEEEEE">
    <td>Resultados 1 a 10 de 150</td>
    </tr>
    </table>
    </body>
    </html>
    """
    result = cjpg_n_pags(html)
    assert result == 16  # 150 / 10 + 1 = 16


def test_cjpg_n_pags_with_small_results():
    """Test cjpg_n_pags with few results."""
    html = """
    <html>
    <body>
    <div id="divDadosResultado">
        <tr class="fundocinza1"><td>Process 1</td></tr>
    </div>
    <table>
    <tr bgcolor="#EEEEEE">
    <td>Resultados 1 a 5 de 5</td>
    </tr>
    </table>
    </body>
    </html>
    """
    result = cjpg_n_pags(html)
    assert result == 1  # 5 / 10 + 1 = 1


def test_cjpg_n_pags_no_results_empty_div():
    """Test cjpg_n_pags with no results (empty divDadosResultado)."""
    html = """
    <html>
    <body>
    <div id="divDadosResultado">
    </div>
    </body>
    </html>
    """
    result = cjpg_n_pags(html)
    assert result == 0


def test_cjpg_n_pags_no_results_message():
    """Test cjpg_n_pags with no results message in page."""
    html = """
    <html>
    <body>
    <div>Nenhum resultado encontrado para a busca.</div>
    </body>
    </html>
    """
    result = cjpg_n_pags(html)
    assert result == 0


def test_cjpg_n_pags_error_message():
    """Test cjpg_n_pags with error message."""
    html = """
    <html>
    <body>
    <div class="mensagemRetorno">Erro: parâmetros inválidos</div>
    </body>
    </html>
    """
    try:
        cjpg_n_pags(html)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Erro: parâmetros inválidos" in str(e)


def test_cjpg_n_pags_unknown_structure():
    """Test cjpg_n_pags with unknown page structure."""
    html = """
    <html>
    <body>
    <div>Some random content</div>
    </body>
    </html>
    """
    try:
        cjpg_n_pags(html)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Não foi possível encontrar o seletor" in str(e)


if __name__ == "__main__":
    # Run all tests
    test_cjpg_n_pags_with_results()
    print("✓ test_cjpg_n_pags_with_results passed")
    
    test_cjpg_n_pags_with_small_results()
    print("✓ test_cjpg_n_pags_with_small_results passed")
    
    test_cjpg_n_pags_no_results_empty_div()
    print("✓ test_cjpg_n_pags_no_results_empty_div passed")
    
    test_cjpg_n_pags_no_results_message()
    print("✓ test_cjpg_n_pags_no_results_message passed")
    
    test_cjpg_n_pags_error_message()
    print("✓ test_cjpg_n_pags_error_message passed")
    
    test_cjpg_n_pags_unknown_structure()
    print("✓ test_cjpg_n_pags_unknown_structure passed")
    
    print("\nAll tests passed!")
