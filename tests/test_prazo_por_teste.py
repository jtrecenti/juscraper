"""Guarda do prazo por teste configurado no ``pyproject.toml`` (pytest-timeout).

Sem ele, um teste de integração preso numa conexão lenta, ou numa coleta sem
limite de páginas, segurava a suíte por horas (#441).
"""


def test_prazo_por_teste_ativo(pytestconfig):
    """O plugin está carregado e o prazo default é finito.

    ``getini`` levanta ``ValueError`` para chave desconhecida, o que pega
    também o ``pytest-timeout`` ausente do extra ``dev``.
    """
    assert pytestconfig.pluginmanager.hasplugin("timeout")
    assert 0 < float(pytestconfig.getini("timeout")) <= 600
