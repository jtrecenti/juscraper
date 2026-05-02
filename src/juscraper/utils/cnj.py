"""Funções utilitárias para manipulação de números CNJ (Conselho Nacional de Justiça)."""
import re

_NON_DIGIT_RE = re.compile(r"\D")


def clean_cnj(numero: str) -> str:
    """Limpa o número do processo, mantendo apenas dígitos.

    Remove pontos, traços, espaços, quebras de linha e qualquer outro
    caractere não-numérico — útil para entradas vindas de CSV/Excel onde
    sobra whitespace.

    Exemplo: ``"0000000-00.0000.0.00.0000 "`` -> ``"00000000000000000000"``
    """
    return _NON_DIGIT_RE.sub("", numero)


def split_cnj(numero: str) -> dict:
    """Divide um número de processo CNJ (limpo ou formatado) em suas partes.

    Espera um número com 20 dígitos (após limpeza) ou no formato NNNNNNN-DD.AAAA.J.TR.OOOO.
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


def format_cnj(numero, strict: bool = True):
    """Formata um número de processo CNJ para o padrão NNNNNNN-DD.AAAA.J.TR.OOOO.

    Args:
        numero: Número CNJ bruto (com ou sem máscara). Aceita ``None`` ou
            string vazia apenas quando ``strict=False``.
        strict: Se ``True`` (default), levanta ``ValueError`` quando ``numero``
            não tem 20 dígitos após limpeza — comportamento histórico. Se
            ``False``, retorna o input sem alterar quando ele não pode ser
            formatado — útil para parsers cujos resultados misturam números
            formatados, brutos e ocasionalmente vazios (TJRN/TJRO/TJRR;
            refs #201, #194).

    Returns:
        String no formato canônico, ou o input original quando ``strict=False``
        e o número não puder ser formatado.
    """
    if not strict:
        if not numero or not isinstance(numero, str):
            return numero
        if len(clean_cnj(numero)) != 20:
            return numero
    partes = split_cnj(numero)  # split_cnj lida com a limpeza interna
    return f"{partes['num']}-{partes['dv']}.{partes['ano']}.{partes['justica']}.{partes['tribunal']}.{partes['orgao']}"
