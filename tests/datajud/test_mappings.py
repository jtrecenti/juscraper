"""Testes de cobertura dos mapeamentos do DataJud (refs #56)."""
from juscraper.aggregators.datajud.mappings import (
    ID_JUSTICA_TRIBUNAL_TO_ALIAS,
    TRIBUNAL_TO_ALIAS,
)


class TestIdJusticaTribunalToAlias:
    def test_estaduais_completos(self):
        # 27 TJs (UFs) + DFT já existiam antes da issue #56
        for i in range(1, 28):
            assert ("8", f"{i:02d}") in ID_JUSTICA_TRIBUNAL_TO_ALIAS

    def test_federais_completos(self):
        for i in range(1, 7):
            assert ("4", f"{i:02d}") in ID_JUSTICA_TRIBUNAL_TO_ALIAS

    def test_trts_completos(self):
        # TST + TRT1..TRT24
        assert ID_JUSTICA_TRIBUNAL_TO_ALIAS[("5", "00")] == "api_publica_tst"
        for i in range(1, 25):
            alias = ID_JUSTICA_TRIBUNAL_TO_ALIAS[("5", f"{i:02d}")]
            assert alias == f"api_publica_trt{i}"

    def test_tres_completos(self):
        # TSE + 27 TREs
        assert ID_JUSTICA_TRIBUNAL_TO_ALIAS[("6", "00")] == "api_publica_tse"
        for i in range(1, 28):
            assert ("6", f"{i:02d}") in ID_JUSTICA_TRIBUNAL_TO_ALIAS
            alias = ID_JUSTICA_TRIBUNAL_TO_ALIAS[("6", f"{i:02d}")]
            assert alias.startswith("api_publica_tre-")

    def test_tre_dft_alias_oficial(self):
        # A wiki oficial do DataJud usa "tre-dft" (não "tre-df")
        assert ID_JUSTICA_TRIBUNAL_TO_ALIAS[("6", "07")] == "api_publica_tre-dft"


class TestTreDfAliasConveniencia:
    def test_tre_df_resolve_para_dft(self):
        # Sigla popular TRE-DF deve resolver para o alias oficial tre-dft
        assert TRIBUNAL_TO_ALIAS["TRE-DF"] == "api_publica_tre-dft"

    def test_tre_df_e_tre_dft_apontam_pro_mesmo_alias(self):
        assert TRIBUNAL_TO_ALIAS["TRE-DF"] == TRIBUNAL_TO_ALIAS["TRE-DFT"]


class TestTribunalToAlias:
    def test_todos_trts(self):
        assert "TST" in TRIBUNAL_TO_ALIAS
        for i in range(1, 25):
            assert f"TRT{i}" in TRIBUNAL_TO_ALIAS

    def test_todos_tres(self):
        assert "TSE" in TRIBUNAL_TO_ALIAS
        # 27 TREs (DFT é alias especial)
        ufs = [
            "AC", "AL", "AM", "AP", "BA", "CE", "DFT", "ES", "GO",
            "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR",
            "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
        ]
        assert len(ufs) == 27
        for uf in ufs:
            assert f"TRE-{uf}" in TRIBUNAL_TO_ALIAS

    def test_aliases_consistentes_com_id_justica(self):
        # Roundtrip: aliases via TRIBUNAL_TO_ALIAS aparecem em ID_JUSTICA_TRIBUNAL_TO_ALIAS
        aliases_por_id = set(ID_JUSTICA_TRIBUNAL_TO_ALIAS.values())
        for sigla, alias in TRIBUNAL_TO_ALIAS.items():
            assert alias in aliases_por_id, (
                f"Alias {alias!r} de {sigla!r} não aparece em ID_JUSTICA_TRIBUNAL_TO_ALIAS"
            )

    def test_aliases_id_justica_tem_sigla(self):
        # Roundtrip inverso: todo alias em ID_JUSTICA_TRIBUNAL_TO_ALIAS tem
        # ao menos uma sigla apontando para ele em TRIBUNAL_TO_ALIAS.
        # Protege contra esquecer de adicionar a sigla quando um novo
        # (id_justica, id_tribunal) for inserido.
        siglas_por_alias = set(TRIBUNAL_TO_ALIAS.values())
        for chave, alias in ID_JUSTICA_TRIBUNAL_TO_ALIAS.items():
            assert alias in siglas_por_alias, (
                f"Alias {alias!r} (chave {chave}) nao tem sigla correspondente em TRIBUNAL_TO_ALIAS"
            )
