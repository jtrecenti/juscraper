"""
Funções utilitárias para manipulação de números CNJ (Conselho Nacional de Justiça).
"""

def clean_cnj(numero: str) -> str:
    """Limpa o número do processo, removendo pontos e traços.
    Exemplo: 0000000-00.0000.0.00.0000 -> 00000000000000000000
    """
    return numero.replace(".", "").replace("-", "")

def split_cnj(numero: str) -> dict:
    """Divide um número de processo CNJ (limpo ou formatado) em suas partes.
    Espera um número com 20 dígitos (após limpeza) ou no formato NNNNNNN-DD.AAAA.J.TR.OOOO
    Retorna um dicionário com as partes: num, dv, ano, justica, tribunal, orgao.
    """
    numero_limpo = clean_cnj(numero)
    if len(numero_limpo) != 20:
        raise ValueError(
            f"Número CNJ '{numero}' inválido. Após limpeza, deve ter 20 dígitos, mas tem {len(numero_limpo)}."
        )
    
    return {
        "num": numero_limpo[:7],
        "dv": numero_limpo[7:9],
        "ano": numero_limpo[9:13],
        "justica": numero_limpo[13:14],
        "tribunal": numero_limpo[14:16],
        "orgao": numero_limpo[16:]
    }

def format_cnj(numero: str) -> str:
    """Formata um número de processo CNJ (limpo ou já formatado) para o padrão NNNNNNN-DD.AAAA.J.TR.OOOO.
    """
    partes = split_cnj(numero) # split_cnj lida com a limpeza interna
    return f"{partes['num']}-{partes['dv']}.{partes['ano']}.{partes['justica']}.{partes['tribunal']}.{partes['orgao']}"
