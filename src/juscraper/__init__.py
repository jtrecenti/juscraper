"""
juscraper
~~~~~~~~~
Public interface: jus.scraper(<sigla>, **kwargs)

The real implementation of each scraper is in:
- juscraper.courts.<sigla_tribunal>.client.TJ<sigla_tribunal>Scraper
- juscraper.aggregators.<sigla_agregador>.client.<Nome>Scraper
"""
from importlib import import_module
from importlib.metadata import version
from typing import Any

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
    "datajud": "juscraper.aggregators.datajud.client:DatajudScraper",
    "jusbr": "juscraper.aggregators.jusbr.client:JusbrScraper",
    "comunica_cnj": "juscraper.aggregators.comunica_cnj.client:ComunicaCNJScraper",
}


def scraper(sigla: str, *args: Any, **kwargs: Any):
    """
    Factory that returns the correct scraper.

    Examples
    --------
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
