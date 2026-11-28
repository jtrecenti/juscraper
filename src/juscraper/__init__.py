"""Interface pública do juscraper: ``jus.scraper(<sigla>, **kwargs)``.

A implementação de cada raspador fica em:

- ``juscraper.courts.<sigla_tribunal>.client.<SIGLA>Scraper``
- ``juscraper.aggregators.<sigla_agregador>.client.<Nome>Scraper``
"""
from __future__ import annotations

from importlib import import_module
from importlib.metadata import version
from typing import TYPE_CHECKING, Any, Literal, overload

if TYPE_CHECKING:
    from juscraper.aggregators.comunica_cnj.client import ComunicaCNJScraper
    from juscraper.aggregators.datajud.client import DatajudScraper
    from juscraper.aggregators.falcao.client import FalcaoScraper
    from juscraper.aggregators.jusbr.client import JusbrScraper
    from juscraper.aggregators.pdpj.client import PdpjScraper
    from juscraper.courts.stf.client import STFScraper
    from juscraper.courts.stm.client import STMScraper
    from juscraper.courts.tjac.client import TJACScraper
    from juscraper.courts.tjal.client import TJALScraper
    from juscraper.courts.tjam.client import TJAMScraper
    from juscraper.courts.tjap.client import TJAPScraper
    from juscraper.courts.tjba.client import TJBAScraper
    from juscraper.courts.tjce.client import TJCEScraper
    from juscraper.courts.tjdft.client import TJDFTScraper
    from juscraper.courts.tjes.client import TJESScraper
    from juscraper.courts.tjgo.client import TJGOScraper
    from juscraper.courts.tjmg.client import TJMGScraper
    from juscraper.courts.tjms.client import TJMSScraper
    from juscraper.courts.tjmt.client import TJMTScraper
    from juscraper.courts.tjpa.client import TJPAScraper
    from juscraper.courts.tjpb.client import TJPBScraper
    from juscraper.courts.tjpe.client import TJPEScraper
    from juscraper.courts.tjpi.client import TJPIScraper
    from juscraper.courts.tjpr.client import TJPRScraper
    from juscraper.courts.tjrj.client import TJRJScraper
    from juscraper.courts.tjrn.client import TJRNScraper
    from juscraper.courts.tjro.client import TJROScraper
    from juscraper.courts.tjrr.client import TJRRScraper
    from juscraper.courts.tjrs.client import TJRSScraper
    from juscraper.courts.tjsc.client import TJSCScraper
    from juscraper.courts.tjsp.client import TJSPScraper
    from juscraper.courts.tjto.client import TJTOScraper
    from juscraper.courts.trf1.client import TRF1Scraper
    from juscraper.courts.trf3.client import TRF3Scraper
    from juscraper.courts.trf5.client import TRF5Scraper
    from juscraper.courts.trf6.client import TRF6Scraper
    from juscraper.courts.tse.client import TSEScraper

_SCRAPERS: dict[str, str] = {
    "tjac":  "juscraper.courts.tjac.client:TJACScraper",
    "tjal":  "juscraper.courts.tjal.client:TJALScraper",
    "tjam":  "juscraper.courts.tjam.client:TJAMScraper",
    "tjap":  "juscraper.courts.tjap.client:TJAPScraper",
    "tjce":  "juscraper.courts.tjce.client:TJCEScraper",
    "tjms":  "juscraper.courts.tjms.client:TJMSScraper",
    "tjsp":  "juscraper.courts.tjsp.client:TJSPScraper",
    "tjdft": "juscraper.courts.tjdft.client:TJDFTScraper",
    "tjrs":  "juscraper.courts.tjrs.client:TJRSScraper",
    "tjba":  "juscraper.courts.tjba.client:TJBAScraper",
    "tjpr":  "juscraper.courts.tjpr.client:TJPRScraper",
    "tjpa":  "juscraper.courts.tjpa.client:TJPAScraper",
    "tjpe":  "juscraper.courts.tjpe.client:TJPEScraper",
    "tjmt":  "juscraper.courts.tjmt.client:TJMTScraper",
    "tjes":  "juscraper.courts.tjes.client:TJESScraper",
    "tjto":  "juscraper.courts.tjto.client:TJTOScraper",
    "tjpb":  "juscraper.courts.tjpb.client:TJPBScraper",
    "tjpi":  "juscraper.courts.tjpi.client:TJPIScraper",
    "tjrn":  "juscraper.courts.tjrn.client:TJRNScraper",
    "tjro":  "juscraper.courts.tjro.client:TJROScraper",
    "tjrr":  "juscraper.courts.tjrr.client:TJRRScraper",
    "tjsc":  "juscraper.courts.tjsc.client:TJSCScraper",
    "tjrj":  "juscraper.courts.tjrj.client:TJRJScraper",
    "tjgo":  "juscraper.courts.tjgo.client:TJGOScraper",
    "tjmg":  "juscraper.courts.tjmg.client:TJMGScraper",
    "trf1":  "juscraper.courts.trf1.client:TRF1Scraper",
    "trf3":  "juscraper.courts.trf3.client:TRF3Scraper",
    "trf5":  "juscraper.courts.trf5.client:TRF5Scraper",
    "trf6":  "juscraper.courts.trf6.client:TRF6Scraper",
    "stf":   "juscraper.courts.stf.client:STFScraper",
    "tse":   "juscraper.courts.tse.client:TSEScraper",
    "stm":   "juscraper.courts.stm.client:STMScraper",
    "datajud": "juscraper.aggregators.datajud.client:DatajudScraper",
    "jusbr": "juscraper.aggregators.jusbr.client:JusbrScraper",
    "pdpj": "juscraper.aggregators.pdpj.client:PdpjScraper",
    "comunica_cnj": "juscraper.aggregators.comunica_cnj.client:ComunicaCNJScraper",
    "falcao": "juscraper.aggregators.falcao.client:FalcaoScraper",
}


# Uma overload por sigla de `_SCRAPERS`, para o verificador de tipos de quem usa a
# biblioteca inferir a classe em `jus.scraper("tjrn")`. O teste
# `tests/test_juscraper.py` confere que as overloads cobrem exatamente o mapa.
@overload
def scraper(sigla: Literal["tjac"], *args: Any, **kwargs: Any) -> TJACScraper: ...


@overload
def scraper(sigla: Literal["tjal"], *args: Any, **kwargs: Any) -> TJALScraper: ...


@overload
def scraper(sigla: Literal["tjam"], *args: Any, **kwargs: Any) -> TJAMScraper: ...


@overload
def scraper(sigla: Literal["tjap"], *args: Any, **kwargs: Any) -> TJAPScraper: ...


@overload
def scraper(sigla: Literal["tjce"], *args: Any, **kwargs: Any) -> TJCEScraper: ...


@overload
def scraper(sigla: Literal["tjms"], *args: Any, **kwargs: Any) -> TJMSScraper: ...


@overload
def scraper(sigla: Literal["tjsp"], *args: Any, **kwargs: Any) -> TJSPScraper: ...


@overload
def scraper(sigla: Literal["tjdft"], *args: Any, **kwargs: Any) -> TJDFTScraper: ...


@overload
def scraper(sigla: Literal["tjrs"], *args: Any, **kwargs: Any) -> TJRSScraper: ...


@overload
def scraper(sigla: Literal["tjba"], *args: Any, **kwargs: Any) -> TJBAScraper: ...


@overload
def scraper(sigla: Literal["tjpr"], *args: Any, **kwargs: Any) -> TJPRScraper: ...


@overload
def scraper(sigla: Literal["tjpa"], *args: Any, **kwargs: Any) -> TJPAScraper: ...


@overload
def scraper(sigla: Literal["tjpe"], *args: Any, **kwargs: Any) -> TJPEScraper: ...


@overload
def scraper(sigla: Literal["tjmt"], *args: Any, **kwargs: Any) -> TJMTScraper: ...


@overload
def scraper(sigla: Literal["tjes"], *args: Any, **kwargs: Any) -> TJESScraper: ...


@overload
def scraper(sigla: Literal["tjto"], *args: Any, **kwargs: Any) -> TJTOScraper: ...


@overload
def scraper(sigla: Literal["tjpb"], *args: Any, **kwargs: Any) -> TJPBScraper: ...


@overload
def scraper(sigla: Literal["tjpi"], *args: Any, **kwargs: Any) -> TJPIScraper: ...


@overload
def scraper(sigla: Literal["tjrn"], *args: Any, **kwargs: Any) -> TJRNScraper: ...


@overload
def scraper(sigla: Literal["tjro"], *args: Any, **kwargs: Any) -> TJROScraper: ...


@overload
def scraper(sigla: Literal["tjrr"], *args: Any, **kwargs: Any) -> TJRRScraper: ...


@overload
def scraper(sigla: Literal["tjsc"], *args: Any, **kwargs: Any) -> TJSCScraper: ...


@overload
def scraper(sigla: Literal["tjrj"], *args: Any, **kwargs: Any) -> TJRJScraper: ...


@overload
def scraper(sigla: Literal["tjgo"], *args: Any, **kwargs: Any) -> TJGOScraper: ...


@overload
def scraper(sigla: Literal["tjmg"], *args: Any, **kwargs: Any) -> TJMGScraper: ...


@overload
def scraper(sigla: Literal["trf1"], *args: Any, **kwargs: Any) -> TRF1Scraper: ...


@overload
def scraper(sigla: Literal["trf3"], *args: Any, **kwargs: Any) -> TRF3Scraper: ...


@overload
def scraper(sigla: Literal["trf5"], *args: Any, **kwargs: Any) -> TRF5Scraper: ...


@overload
def scraper(sigla: Literal["trf6"], *args: Any, **kwargs: Any) -> TRF6Scraper: ...


@overload
def scraper(sigla: Literal["stf"], *args: Any, **kwargs: Any) -> STFScraper: ...


@overload
def scraper(sigla: Literal["tse"], *args: Any, **kwargs: Any) -> TSEScraper: ...


@overload
def scraper(sigla: Literal["stm"], *args: Any, **kwargs: Any) -> STMScraper: ...


@overload
def scraper(sigla: Literal["datajud"], *args: Any, **kwargs: Any) -> DatajudScraper: ...


@overload
def scraper(sigla: Literal["jusbr"], *args: Any, **kwargs: Any) -> JusbrScraper: ...


@overload
def scraper(sigla: Literal["pdpj"], *args: Any, **kwargs: Any) -> PdpjScraper: ...


@overload
def scraper(sigla: Literal["comunica_cnj"], *args: Any, **kwargs: Any) -> ComunicaCNJScraper: ...


@overload
def scraper(sigla: Literal["falcao"], *args: Any, **kwargs: Any) -> FalcaoScraper: ...


# Fallback para qualquer `str` (sigla em variável, maiúsculas), deliberadamente `Any`:
# `BaseScraper` não declara `cjsg`/`cpopg`, e tipá-lo como retorno faria o mypy recusar
# `jus.scraper(sigla).cjsg(...)` com sigla em variável.
@overload
def scraper(sigla: str, *args: Any, **kwargs: Any) -> Any: ...  # noqa: ANN401


def scraper(sigla: str, *args: Any, **kwargs: Any) -> Any:
    """
    Factory that returns the correct scraper.

    Examples: Exemplo
        >>> import juscraper as jus
        >>> tjsp = jus.scraper("tjsp")
        >>> jusbr = jus.scraper("jusbr")
    """
    sigla = sigla.lower()
    if sigla not in _SCRAPERS:
        raise ValueError(
            f"Scraper '{sigla}' not supported. Available: {', '.join(_SCRAPERS)}"
        )
    path, cls_name = _SCRAPERS[sigla].split(":")
    mod = import_module(path)
    cls = getattr(mod, cls_name)
    return cls(*args, **kwargs)


__version__ = version("juscraper")
__all__ = ["scraper"]
