"""Integração do ``cjpg``, de ``baixar_sentencas`` e das árvores de 1º grau do TJMS contra o portal (#487).

O ``esaj.tjms.jus.br`` não responde a IP de datacenter: rodar de IP
residencial, com ``uv run pytest tests/tjms/test_cjpg_integration.py -m integration``.
"""
from pathlib import Path

import pytest

import juscraper as jus


@pytest.mark.integration
def test_cjpg_pagina_e_conta(tmp_path):
    scraper = jus.scraper("tjms", download_path=str(tmp_path))

    df = scraper.cjpg("dano moral", paginas=range(1, 3))
    n = scraper.cjpg("dano moral", count_only=True)

    assert len(df) > 10
    assert set(df.columns) >= {"id_processo", "decisao", "nm_alias"}
    assert df[["cd_processo", "cd_foro", "cd_documento"]].notna().all().all()
    assert n >= len(df)


@pytest.mark.integration
def test_baixar_sentencas_da_primeira_linha_do_cjpg(tmp_path):
    """Os quatro códigos do cjpg levam ao PDF da sentença, sem login nem captcha."""
    scraper = jus.scraper("tjms", download_path=str(tmp_path))
    df = scraper.cjpg("dano moral", paginas=1).head(1)

    resultado = scraper.baixar_sentencas(df)

    assert resultado["motivo_falha"].tolist() == [None]
    assert Path(resultado["caminho_sentenca"].iloc[0]).read_bytes().startswith(b"%PDF")


@pytest.mark.integration
def test_arvores_de_primeiro_grau():
    """As árvores do formulário do cjpg respondem no TJMS, no formato das do TJSP."""
    scraper = jus.scraper("tjms")
    colunas = {"id", "nome", "id_pai", "nivel", "selecionavel", "caminho"}

    classes = scraper.listar_classes(grau="1")
    varas = scraper.listar_varas()

    for arvore in (classes, varas):
        assert set(arvore.columns) == colunas
        assert arvore["selecionavel"].sum() > 0
    assert len(classes) > 50
    assert varas["caminho"].str.contains("Campo Grande").any()
