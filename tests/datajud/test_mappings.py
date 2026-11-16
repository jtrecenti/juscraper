"""Testes de cobertura dos mapeamentos do DataJud (refs #56)."""
import pytest

from juscraper.aggregators.datajud.client import _resolve_cnj_alias
from juscraper.aggregators.datajud.mappings import ID_JUSTICA_TRIBUNAL_TO_ALIAS, TRIBUNAL_TO_ALIAS


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


class TestJusticaMilitarDaUniao:
    def test_cjms_de_primeiro_grau_usam_o_indice_do_stm(self):
        """Conferido ao vivo em 16/11/2026: ``api_publica_stm`` traz CNJs ``.7.01.`` a ``.7.12.``.

        São os processos das Auditorias das 12 Circunscrições Judiciárias
        Militares (grau ``G1``), com ``tribunal`` ``STM`` na fonte.
        """
        assert ID_JUSTICA_TRIBUNAL_TO_ALIAS[("7", "00")] == "api_publica_stm"
        for i in range(1, 13):
            assert ID_JUSTICA_TRIBUNAL_TO_ALIAS[("7", f"{i:02d}")] == "api_publica_stm"
        assert ("7", "13") not in ID_JUSTICA_TRIBUNAL_TO_ALIAS


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


class TestCodigoDaUf:
    """O código do tribunal no CNJ segue a ordem do nome da UF (Resolução CNJ 65/2008).

    Antes, o mapa trocava MG (13) e MT (11) na Justiça Estadual e na
    Eleitoral, punha o TJMMG em 9.11 e o TJMSP em 9.25: um CNJ do TJMG era
    consultado no índice do TJMT. Os códigos de MG, MT e SP foram conferidos
    ao vivo nos números que cada índice devolve.
    """

    def test_mato_grosso_e_minas_gerais(self):
        assert ID_JUSTICA_TRIBUNAL_TO_ALIAS[("8", "11")] == "api_publica_tjmt"
        assert ID_JUSTICA_TRIBUNAL_TO_ALIAS[("8", "12")] == "api_publica_tjms"
        assert ID_JUSTICA_TRIBUNAL_TO_ALIAS[("8", "13")] == "api_publica_tjmg"
        assert ID_JUSTICA_TRIBUNAL_TO_ALIAS[("6", "11")] == "api_publica_tre-mt"
        assert ID_JUSTICA_TRIBUNAL_TO_ALIAS[("6", "13")] == "api_publica_tre-mg"

    def test_justica_militar_estadual(self):
        assert ID_JUSTICA_TRIBUNAL_TO_ALIAS[("9", "13")] == "api_publica_tjmmg"
        assert ID_JUSTICA_TRIBUNAL_TO_ALIAS[("9", "21")] == "api_publica_tjmrs"
        assert ID_JUSTICA_TRIBUNAL_TO_ALIAS[("9", "26")] == "api_publica_tjmsp"
        assert ("9", "11") not in ID_JUSTICA_TRIBUNAL_TO_ALIAS
        assert ("9", "25") not in ID_JUSTICA_TRIBUNAL_TO_ALIAS

    @pytest.mark.parametrize(("id_justica", "prefixo"), [("6", "api_publica_tre-"), ("9", "api_publica_tjm")])
    def test_mesmo_codigo_da_justica_estadual(self, id_justica, prefixo):
        # O código de cada UF é o mesmo em todos os ramos.
        for (justica, codigo), alias in ID_JUSTICA_TRIBUNAL_TO_ALIAS.items():
            if justica != id_justica or codigo == "00":
                continue
            uf = alias.removeprefix(prefixo)
            assert ID_JUSTICA_TRIBUNAL_TO_ALIAS[("8", codigo)] == f"api_publica_tj{uf}", (justica, codigo)

    def test_cnj_do_tjmg_consulta_o_indice_do_tjmg(self):
        assert _resolve_cnj_alias("5000001-23.2024.8.13.0024") == ("api_publica_tjmg", "50000012320248130024")
        assert _resolve_cnj_alias("1000001-23.2024.8.11.0041") == ("api_publica_tjmt", "10000012320248110041")
