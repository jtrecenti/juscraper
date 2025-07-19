"""
Maps (id_justica, id_tribunal) from CNJ to Datajud API alias.
"""

ID_JUSTICA_TRIBUNAL_TO_ALIAS = {
    # Justiça Estadual (id_justica="8")
    ("8", "01"): "api_publica_tjac",  # TJAC
    ("8", "02"): "api_publica_tjal",  # TJAL
    ("8", "03"): "api_publica_tjap",  # TJAP
    ("8", "04"): "api_publica_tjam",  # TJAM
    ("8", "05"): "api_publica_tjba",  # TJBA
    ("8", "06"): "api_publica_tjce",  # TJCE
    ("8", "07"): "api_publica_tjdft", # TJDFT
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
    # Add TRT aliases as needed, e.g., ("5", "01"): "api_publica_trt1"
    # Justiça Eleitoral (id_justica="6")
    # Add TRE aliases as needed
    # Justiça Militar da União (id_justica="7")
    ("7", "00"): "api_publica_stm",   # STM
    # Justiça Militar Estadual (id_justica="9")
    ("9", "11"): "api_publica_tjmmg", # TJMMG (MG)
    ("9", "21"): "api_publica_tjmrs", # TJMRS (RS)
    ("9", "25"): "api_publica_tjmsp", # TJMSP (SP)
    # Conselhos (id_justica="3")
    ("3", "00"): "api_publica_cnj",   # CNJ
    # Tribunais Superiores (id_justica="1", "2")
    ("1", "00"): "api_publica_stf",   # STF
    ("2", "00"): "api_publica_stj",   # STJ
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
    # Justiça do Trabalho (Example, expand as needed)
    "TST": "api_publica_tst",
    "TRT1": "api_publica_trt1",
    "TRT2": "api_publica_trt2",
    # ... add all TRTs
    # Justiça Eleitoral (Example, expand as needed)
    "TSE": "api_publica_tse",
    "TRE-AC": "api_publica_tre-ac",
    "TRE-AL": "api_publica_tre-al",
    # ... add all TREs
    # Justiça Militar da União
    "STM": "api_publica_stm",
    # Justiça Militar Estadual
    "TJMMG": "api_publica_tjmmg",
    "TJMRS": "api_publica_tjmrs",
    "TJMSP": "api_publica_tjmsp",
}
