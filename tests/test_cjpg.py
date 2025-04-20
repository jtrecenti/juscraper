from juscraper import scraper
import pandas as pd

def get_tjsp_scraper(tmp_path):
    s = scraper("TJSP", download_path=str(tmp_path), verbose=0)
    return s

def test_cjpg_minimal(tmp_path):
    s = get_tjsp_scraper(tmp_path)
    df = s.cjpg(pesquisa="league of legends", paginas=range(0, 1))
    assert isinstance(df, pd.DataFrame)
    assert not df.empty

def test_cjpg_classe(tmp_path):
    s = get_tjsp_scraper(tmp_path)
    df = s.cjpg(classes=["8501"], paginas=range(0, 1))
    assert isinstance(df, pd.DataFrame)
    assert not df.empty

def test_cjpg_assunto(tmp_path):
    s = get_tjsp_scraper(tmp_path)
    df = s.cjpg(assuntos=["10433"], paginas=range(0, 1))
    assert isinstance(df, pd.DataFrame)
    assert not df.empty

def test_cjpg_vara(tmp_path):
    s = get_tjsp_scraper(tmp_path)
    df = s.cjpg(varas=["405-2"], paginas=range(0, 1))
    assert isinstance(df, pd.DataFrame)
    assert not df.empty

def test_cjpg_id_processo(tmp_path):
    s = get_tjsp_scraper(tmp_path)
    # Usar um id_processo real para garantir teste robusto
    df = s.cjpg(id_processo="10081975020248260562", paginas=range(0, 1))
    assert isinstance(df, pd.DataFrame)
    assert not df.empty

def test_cjpg_data_inicio_fim(tmp_path):
    s = get_tjsp_scraper(tmp_path)
    df = s.cjpg(data_inicio="01/01/2024", data_fim="31/12/2024", paginas=range(0, 1))
    assert isinstance(df, pd.DataFrame)
    assert not df.empty

def test_cjpg_varios_parametros(tmp_path):
    s = get_tjsp_scraper(tmp_path)
    df = s.cjpg(
        pesquisa="contrato",
        classes=["8501"],
        assuntos=["10433"],
        varas=["405-2"],
        data_inicio="01/01/2024",
        data_fim="31/12/2024",
        paginas=range(0, 1)
    )
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
