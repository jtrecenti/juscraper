"""Maps (id_justica, id_tribunal) from CNJ to Datajud API alias.

Fonte de verdade dos aliases: http://datajud-wiki.cnj.jus.br/api-publica/endpoints/.
Ao adicionar/alterar um alias, conferir contra a wiki — em particular notar que
o DF nao segue o padrao "tre-df": o alias oficial e `api_publica_tre-dft`.
"""

ID_JUSTICA_TRIBUNAL_TO_ALIAS = {
    # Justiça Estadual (id_justica="8")
    ("8", "01"): "api_publica_tjac",  # TJAC
    ("8", "02"): "api_publica_tjal",  # TJAL
    ("8", "03"): "api_publica_tjap",  # TJAP
    ("8", "04"): "api_publica_tjam",  # TJAM
    ("8", "05"): "api_publica_tjba",  # TJBA
    ("8", "06"): "api_publica_tjce",  # TJCE
    ("8", "07"): "api_publica_tjdft",  # TJDFT
    ("8", "08"): "api_publica_tjes",  # TJES
    ("8", "09"): "api_publica_tjgo",  # TJGO
    ("8", "10"): "api_publica_tjma",  # TJMA
    ("8", "11"): "api_publica_tjmg",  # TJMG
    ("8", "12"): "api_publica_tjms",  # TJMS
    ("8", "13"): "api_publica_tjmt",  # TJMT
    ("8", "14"): "api_publica_tjpa",  # TJPA
    ("8", "15"): "api_publica_tjpb",  # TJPB
    ("8", "16"): "api_publica_tjpr",  # TJPR
    ("8", "17"): "api_publica_tjpe",  # TJPE
    ("8", "18"): "api_publica_tjpi",  # TJPI
    ("8", "19"): "api_publica_tjrj",  # TJRJ
    ("8", "20"): "api_publica_tjrn",  # TJRN
    ("8", "21"): "api_publica_tjrs",  # TJRS
    ("8", "22"): "api_publica_tjro",  # TJRO
    ("8", "23"): "api_publica_tjrr",  # TJRR
    ("8", "24"): "api_publica_tjsc",  # TJSC
    ("8", "25"): "api_publica_tjse",  # TJSE
    ("8", "26"): "api_publica_tjsp",  # TJSP
    ("8", "27"): "api_publica_tjto",  # TJTO
    # Justiça Federal (id_justica="4")
    ("4", "01"): "api_publica_trf1",  # TRF1
    ("4", "02"): "api_publica_trf2",  # TRF2
    ("4", "03"): "api_publica_trf3",  # TRF3
    ("4", "04"): "api_publica_trf4",  # TRF4
    ("4", "05"): "api_publica_trf5",  # TRF5
    ("4", "06"): "api_publica_trf6",  # TRF6
    # Justiça do Trabalho (id_justica="5")
    ("5", "00"): "api_publica_tst",  # TST
    ("5", "01"): "api_publica_trt1",  # TRT1 (RJ)
    ("5", "02"): "api_publica_trt2",  # TRT2 (SP capital + Grande SP)
    ("5", "03"): "api_publica_trt3",  # TRT3 (MG)
    ("5", "04"): "api_publica_trt4",  # TRT4 (RS)
    ("5", "05"): "api_publica_trt5",  # TRT5 (BA)
    ("5", "06"): "api_publica_trt6",  # TRT6 (PE)
    ("5", "07"): "api_publica_trt7",  # TRT7 (CE)
    ("5", "08"): "api_publica_trt8",  # TRT8 (PA/AP)
    ("5", "09"): "api_publica_trt9",  # TRT9 (PR)
    ("5", "10"): "api_publica_trt10",  # TRT10 (DF/TO)
    ("5", "11"): "api_publica_trt11",  # TRT11 (AM/RR)
    ("5", "12"): "api_publica_trt12",  # TRT12 (SC)
    ("5", "13"): "api_publica_trt13",  # TRT13 (PB)
    ("5", "14"): "api_publica_trt14",  # TRT14 (RO/AC)
    ("5", "15"): "api_publica_trt15",  # TRT15 (Campinas/SP interior)
    ("5", "16"): "api_publica_trt16",  # TRT16 (MA)
    ("5", "17"): "api_publica_trt17",  # TRT17 (ES)
    ("5", "18"): "api_publica_trt18",  # TRT18 (GO)
    ("5", "19"): "api_publica_trt19",  # TRT19 (AL)
    ("5", "20"): "api_publica_trt20",  # TRT20 (SE)
    ("5", "21"): "api_publica_trt21",  # TRT21 (RN)
    ("5", "22"): "api_publica_trt22",  # TRT22 (PI)
    ("5", "23"): "api_publica_trt23",  # TRT23 (MT)
    ("5", "24"): "api_publica_trt24",  # TRT24 (MS)
    # Justiça Eleitoral (id_justica="6")
    # Os IDs CNJ 01..27 seguem a mesma ordem alfabética usada na Justiça
    # Estadual (id_justica="8"), conforme Resolução CNJ 65/2008.
    ("6", "00"): "api_publica_tse",  # TSE
    ("6", "01"): "api_publica_tre-ac",  # TRE-AC
    ("6", "02"): "api_publica_tre-al",  # TRE-AL
    ("6", "03"): "api_publica_tre-ap",  # TRE-AP
    ("6", "04"): "api_publica_tre-am",  # TRE-AM
    ("6", "05"): "api_publica_tre-ba",  # TRE-BA
    ("6", "06"): "api_publica_tre-ce",  # TRE-CE
    ("6", "07"): "api_publica_tre-dft",  # TRE-DFT (alias oficial DataJud)
    ("6", "08"): "api_publica_tre-es",  # TRE-ES
    ("6", "09"): "api_publica_tre-go",  # TRE-GO
    ("6", "10"): "api_publica_tre-ma",  # TRE-MA
    ("6", "11"): "api_publica_tre-mg",  # TRE-MG
    ("6", "12"): "api_publica_tre-ms",  # TRE-MS
    ("6", "13"): "api_publica_tre-mt",  # TRE-MT
    ("6", "14"): "api_publica_tre-pa",  # TRE-PA
    ("6", "15"): "api_publica_tre-pb",  # TRE-PB
    ("6", "16"): "api_publica_tre-pr",  # TRE-PR
    ("6", "17"): "api_publica_tre-pe",  # TRE-PE
    ("6", "18"): "api_publica_tre-pi",  # TRE-PI
    ("6", "19"): "api_publica_tre-rj",  # TRE-RJ
    ("6", "20"): "api_publica_tre-rn",  # TRE-RN
    ("6", "21"): "api_publica_tre-rs",  # TRE-RS
    ("6", "22"): "api_publica_tre-ro",  # TRE-RO
    ("6", "23"): "api_publica_tre-rr",  # TRE-RR
    ("6", "24"): "api_publica_tre-sc",  # TRE-SC
    ("6", "25"): "api_publica_tre-se",  # TRE-SE
    ("6", "26"): "api_publica_tre-sp",  # TRE-SP
    ("6", "27"): "api_publica_tre-to",  # TRE-TO
    # Justiça Militar da União (id_justica="7")
    ("7", "00"): "api_publica_stm",  # STM
    # Justiça Militar Estadual (id_justica="9")
    ("9", "11"): "api_publica_tjmmg",  # TJMMG (MG)
    ("9", "21"): "api_publica_tjmrs",  # TJMRS (RS)
    ("9", "25"): "api_publica_tjmsp",  # TJMSP (SP)
    # Conselhos (id_justica="3")
    ("3", "00"): "api_publica_cnj",  # CNJ
    # Tribunais Superiores (id_justica="1", "2")
    ("1", "00"): "api_publica_stf",  # STF
    ("2", "00"): "api_publica_stj",  # STJ
}

# Maps Tribunal Acronym to Datajud API alias
TRIBUNAL_TO_ALIAS = {
    # Supremo Tribunal Federal
    "STF": "api_publica_stf",
    # Conselho Nacional de Justiça
    "CNJ": "api_publica_cnj",
    # Superior Tribunal de Justiça
    "STJ": "api_publica_stj",
    # Justiça Federal
    "TRF1": "api_publica_trf1",
    "TRF2": "api_publica_trf2",
    "TRF3": "api_publica_trf3",
    "TRF4": "api_publica_trf4",
    "TRF5": "api_publica_trf5",
    "TRF6": "api_publica_trf6",
    # Justiça Estadual
    "TJAC": "api_publica_tjac",
    "TJAL": "api_publica_tjal",
    "TJAP": "api_publica_tjap",
    "TJAM": "api_publica_tjam",
    "TJBA": "api_publica_tjba",
    "TJCE": "api_publica_tjce",
    "TJDFT": "api_publica_tjdft",
    "TJES": "api_publica_tjes",
    "TJGO": "api_publica_tjgo",
    "TJMA": "api_publica_tjma",
    "TJMG": "api_publica_tjmg",
    "TJMS": "api_publica_tjms",
    "TJMT": "api_publica_tjmt",
    "TJPA": "api_publica_tjpa",
    "TJPB": "api_publica_tjpb",
    "TJPR": "api_publica_tjpr",
    "TJPE": "api_publica_tjpe",
    "TJPI": "api_publica_tjpi",
    "TJRJ": "api_publica_tjrj",
    "TJRN": "api_publica_tjrn",
    "TJRS": "api_publica_tjrs",
    "TJRO": "api_publica_tjro",
    "TJRR": "api_publica_tjrr",
    "TJSC": "api_publica_tjsc",
    "TJSP": "api_publica_tjsp",
    "TJSE": "api_publica_tjse",
    "TJTO": "api_publica_tjto",
    # Justiça do Trabalho
    "TST": "api_publica_tst",
    "TRT1": "api_publica_trt1",
    "TRT2": "api_publica_trt2",
    "TRT3": "api_publica_trt3",
    "TRT4": "api_publica_trt4",
    "TRT5": "api_publica_trt5",
    "TRT6": "api_publica_trt6",
    "TRT7": "api_publica_trt7",
    "TRT8": "api_publica_trt8",
    "TRT9": "api_publica_trt9",
    "TRT10": "api_publica_trt10",
    "TRT11": "api_publica_trt11",
    "TRT12": "api_publica_trt12",
    "TRT13": "api_publica_trt13",
    "TRT14": "api_publica_trt14",
    "TRT15": "api_publica_trt15",
    "TRT16": "api_publica_trt16",
    "TRT17": "api_publica_trt17",
    "TRT18": "api_publica_trt18",
    "TRT19": "api_publica_trt19",
    "TRT20": "api_publica_trt20",
    "TRT21": "api_publica_trt21",
    "TRT22": "api_publica_trt22",
    "TRT23": "api_publica_trt23",
    "TRT24": "api_publica_trt24",
    # Justiça Eleitoral
    "TSE": "api_publica_tse",
    "TRE-AC": "api_publica_tre-ac",
    "TRE-AL": "api_publica_tre-al",
    "TRE-AP": "api_publica_tre-ap",
    "TRE-AM": "api_publica_tre-am",
    "TRE-BA": "api_publica_tre-ba",
    "TRE-CE": "api_publica_tre-ce",
    "TRE-DFT": "api_publica_tre-dft",
    # Alias de conveniência: usuários tipicamente escrevem "TRE-DF"
    # mesmo a sigla oficial DataJud sendo "tre-dft".
    "TRE-DF": "api_publica_tre-dft",
    "TRE-ES": "api_publica_tre-es",
    "TRE-GO": "api_publica_tre-go",
    "TRE-MA": "api_publica_tre-ma",
    "TRE-MG": "api_publica_tre-mg",
    "TRE-MS": "api_publica_tre-ms",
    "TRE-MT": "api_publica_tre-mt",
    "TRE-PA": "api_publica_tre-pa",
    "TRE-PB": "api_publica_tre-pb",
    "TRE-PR": "api_publica_tre-pr",
    "TRE-PE": "api_publica_tre-pe",
    "TRE-PI": "api_publica_tre-pi",
    "TRE-RJ": "api_publica_tre-rj",
    "TRE-RN": "api_publica_tre-rn",
    "TRE-RS": "api_publica_tre-rs",
    "TRE-RO": "api_publica_tre-ro",
    "TRE-RR": "api_publica_tre-rr",
    "TRE-SC": "api_publica_tre-sc",
    "TRE-SE": "api_publica_tre-se",
    "TRE-SP": "api_publica_tre-sp",
    "TRE-TO": "api_publica_tre-to",
    # Justiça Militar da União
    "STM": "api_publica_stm",
    # Justiça Militar Estadual
    "TJMMG": "api_publica_tjmmg",
    "TJMRS": "api_publica_tjmrs",
    "TJMSP": "api_publica_tjmsp",
}
