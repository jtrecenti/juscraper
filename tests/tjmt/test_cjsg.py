import pandas as pd
import pytest

from juscraper.courts.tjmt.client import TJMTScraper


@pytest.mark.integration
def test_cjsg_basic_dataframe():
    scraper = TJMTScraper()
    df = scraper.cjsg("direito", paginas=1)
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert {"ementa", "processo", "relator"}.issubset(set(df.columns))
    assert df["ementa"].notnull().all()


@pytest.mark.integration
def test_cjsg_colunas_esperadas():
    scraper = TJMTScraper()
    df = scraper.cjsg("direito", paginas=1)
    colunas_minimas = {
        "id", "tipo", "ementa", "processo", "classe",
        "assunto", "relator", "orgao_julgador",
        "data_julgamento", "data_publicacao", "uuid",
    }
    assert colunas_minimas.issubset(set(df.columns))
    assert df["uuid"].notna().all()


@pytest.mark.integration
def test_cjsg_paginacao():
    scraper = TJMTScraper()
    df_1 = scraper.cjsg("dano moral", paginas=1)
    df_2 = scraper.cjsg("dano moral", paginas=range(1, 3))
    assert len(df_2) > len(df_1)


@pytest.mark.integration
def test_cjsg_paginas_int():
    scraper = TJMTScraper()
    df_int = scraper.cjsg("direito", paginas=2)
    df_range = scraper.cjsg("direito", paginas=range(1, 3))
    assert len(df_int) == len(df_range)


@pytest.mark.integration
def test_cjsg_download_e_parse():
    scraper = TJMTScraper()
    brutos = scraper.cjsg_download("direito", paginas=1)
    assert isinstance(brutos, list)
    assert len(brutos) > 0
    dados = scraper.cjsg_parse(brutos)
    assert isinstance(dados, list)
    assert len(dados) > 0
    df = pd.DataFrame(dados)
    assert "ementa" in df.columns


@pytest.mark.integration
@pytest.mark.parametrize(
    ("tipo_consulta", "total"),
    [("Acordao", "countAcordaoDocumento"), ("DecisaoMonocratica", "countDecisaoMonocratica")],
)
def test_cjsg_filtro_classe(tipo_consulta, total):
    """``classe`` restringe a busca à classe pedida e reduz o total (#493)."""
    scraper = TJMTScraper()
    busca = {"pesquisa": "dano moral", "paginas": 1, "tipo_consulta": tipo_consulta}
    com_filtro = scraper.cjsg_download(classe="Agravo de Instrumento", **busca)
    classes = {linha["classe"].upper() for linha in scraper.cjsg_parse(com_filtro)}
    assert classes == {"AGRAVO DE INSTRUMENTO"}
    sem_filtro = scraper.cjsg_download(tamanho_pagina=1, **busca)
    assert 0 < com_filtro[0]["value"][total] < sem_filtro[0]["value"][total]


@pytest.mark.integration
def test_cjsg_orgao_julgador_com_ordinal():
    """O "ª" do nome do órgão chega à API como está."""
    df = TJMTScraper().cjsg(
        "recurso",
        paginas=1,
        orgao_julgador="Regime de Cooperação da 2ª Câmara de Direito Público",
    )
    assert not df.empty


if __name__ == "__main__":
    pytest.main([__file__])
