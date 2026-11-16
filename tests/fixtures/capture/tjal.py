"""Capture cjsg samples for TJAL.

Run from repo root::

    python -m tests.fixtures.capture.tjal
"""
from ._util import capture_cjsg_monocratica_sample, capture_cjsg_samples


def main() -> None:
    """Capture cjsg samples for TJAL."""
    capture_cjsg_samples(
        tribunal="tjal",
        base_url="https://www2.tjal.jus.br/",
    )
    # O formulário do TJAL só mostra a caixa de acórdãos, mas a busca com
    # ``tipoDecisaoSelecionados=D`` responde com a aba de monocráticas.
    capture_cjsg_monocratica_sample("tjal", "https://www2.tjal.jus.br/", "usucapiao predio rural")


if __name__ == "__main__":
    main()
