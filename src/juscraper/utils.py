def clean_cnj(numero: str) -> str:
    """Formata o número do processo para o padrão esperado."""
    return numero.replace(".", "").replace("-", "")

def format_cnj(numero: str) -> str:
    """Formata o número do processo para o padrão brasileiro."""
    p = split_cnj(numero)
    return f"{p['num']}-{p['dv']}.{p['ano']}.{p['justica']}.{p['tribunal']}.{p['orgao']}"

def split_cnj(numero: str) -> str:
    """Formata o número do processo para o padrão brasileiro."""
    dicionario = {
      "num": numero[:7],
      "dv": numero[7:9],
      "ano": numero[9:13],
      "justica": numero[13:14],
      "tribunal": numero[14:16],
      "orgao": numero[16:]
    }
    return dicionario