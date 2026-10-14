"""Avisos do juscraper apontam para o código de quem chamou a biblioteca.

``warnings.warn`` atribui o aviso ao quadro da pilha indicado por
``stacklevel``, contado a partir de quem chama ``warn``. Contado à mão, o
número muda sempre que um helper ou um decorador entra no caminho, e o aviso
passa a apontar para uma linha do próprio juscraper. :func:`avisar` procura o
primeiro quadro fora do pacote e entrega esse nível a ``warnings.warn``.
"""
from __future__ import annotations

import inspect
import warnings
from pathlib import Path

_RAIZ_DO_PACOTE = Path(__file__).resolve().parent.parent


def _dentro_do_pacote(arquivo: str) -> bool:
    return Path(arquivo).resolve().is_relative_to(_RAIZ_DO_PACOTE)


def avisar(mensagem: str, categoria: type[Warning] = UserWarning) -> None:
    """Emite ``mensagem`` atribuída ao primeiro quadro fora do pacote ``juscraper``.

    Args:
        mensagem: Texto do aviso.
        categoria: Classe do aviso. Default ``UserWarning``.
    """
    # Nível 2 é quem chamou esta função; cada quadro do pacote acima dele
    # empurra a atribuição um nível para cima.
    nivel = 2
    atual = inspect.currentframe()
    quadro = atual.f_back if atual is not None else None
    while quadro is not None and _dentro_do_pacote(quadro.f_code.co_filename):
        quadro = quadro.f_back
        nivel += 1
    warnings.warn(mensagem, categoria, stacklevel=nivel)
