"""Coleta integral STF em janelas disjuntas, sem pressupor snapshot do índice."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from ._checkpoint import Attempt, Checkpoint, Window, document_ids, utc_now
from .download import MAX_REGISTROS, build_payload
from .parse import parse_decisoes

FILTERS = {
    "base",
    "classe",
    "inteiro_teor",
    "data_julgamento_inicio",
    "data_julgamento_fim",
    "data_publicacao_inicio",
    "data_publicacao_fim",
}


def exact_total(response: dict) -> int:
    """Recusa totais aproximados ou que não representem contagens inteiras."""
    try:
        result = response["result"]
        total = result["hits"]["total"]
        valor = total["value"]
        if total["relation"] != "eq" or not isinstance(valor, int) or isinstance(valor, bool) or valor < 0:
            raise ValueError("A coleta STF exige total exato, com relation='eq'.")
        return valor
    except (KeyError, TypeError) as exc:
        raise ValueError("Resposta STF sem contagem exata válida.") from exc


def bounds_payload(payload: dict, field: str) -> dict:
    """Preserva base e classe, pois agregações ignoram post_filter."""
    payload["aggs"] = {
        "collection_bounds": {
            "filter": payload["post_filter"],
            "aggs": {
                "lower": {"min": {"field": field, "format": "yyyy-MM-dd"}},
                "upper": {"max": {"field": field, "format": "yyyy-MM-dd"}},
                "missing": {"missing": {"field": field}},
            },
        },
    }
    return payload


def _bound(value: dict) -> date:
    try:
        if "value_as_string" in value:
            return date.fromisoformat(value["value_as_string"])
        return datetime.fromtimestamp(value["value"] / 1000, tz=timezone.utc).date()
    except (KeyError, TypeError, ValueError, OverflowError, OSError) as exc:
        raise ValueError("Limite de data inválido na agregação STF.") from exc


class Collection:
    """Exige integridade por janela antes de devolver a coleta completa."""

    def __init__(self, buscar: Callable[[dict], dict], intervalo: float, entrada):
        self.buscar = buscar
        self.intervalo = intervalo
        self.inp = entrada
        self.filters = entrada.model_dump(include=FILTERS)
        if self.filters["classe"]:
            classes = self.filters["classe"]
            self.filters["classe"] = sorted(set([classes] if isinstance(classes, str) else classes))
        tem_publicacao = any(self.filters[f"data_publicacao_{limite}"] for limite in ("inicio", "fim"))
        self.axis = "publicacao" if tem_publicacao else "julgamento"
        if isinstance(entrada.paginas, range):
            build_payload(pagina=entrada.paginas[-1], tamanho_pagina=entrada.tamanho_pagina)
        self.pages = None if entrada.paginas is None else list(entrada.paginas)
        if self.pages is not None:
            if len(set(self.pages)) != len(self.pages):
                raise ValueError("Páginas explícitas não podem se repetir.")
            for pagina in self.pages:
                build_payload(pagina=pagina, tamanho_pagina=entrada.tamanho_pagina)
        identidade = {
            "base": entrada.base,
            "pages": self.pages,
            "page_size": entrada.tamanho_pagina,
            "payload": build_payload(entrada.pesquisa, tamanho_pagina=0, **self.filters),
            "contract": "exact-counts-disjoint-days-score-id-v1",
        }
        self.store = Checkpoint(entrada.checkpoint_dir, entrada.resume, identidade)
        self.requested = False

    def payload(self, window: Window, page: int = 1, size: int = 0) -> dict:
        """Mantém os filtros de origem ao ajustar a janela e a referência temporal."""
        filters = dict(self.filters)
        for end, value in (("inicio", window.lower), ("fim", window.upper)):
            if value is not None:
                filters[f"data_{self.axis}_{end}"] = date.fromisoformat(value).strftime("%d%m%Y")
        payload = build_payload(
            self.inp.pesquisa,
            pagina=page,
            tamanho_pagina=size,
            **filters,
            reference_time=self.store.manifest.reference_time if self.pages is None else None,
        )
        payload["track_total_hits"] = True
        payload["aggs"] = {}
        if window.missing:
            payload["query"]["function_score"]["query"]["bool"]["must_not"] = [
                {"exists": {"field": f"{self.axis}_data"}},
            ]
        return payload

    def request(self, payload: dict) -> dict:
        """Espaça buscas e exige contagem exata em cada resposta."""
        if self.requested:
            time.sleep(self.intervalo)
        self.requested = True
        resposta = self.buscar(payload)
        exact_total(resposta)
        return resposta

    def count(self, window: Window) -> int:
        """Consulta a contagem da janela sem requisitar documentos."""
        return exact_total(self.request(self.payload(window)))

    def run(self) -> pd.DataFrame:
        """Devolve o DataFrame só depois de conferir todas as identidades."""
        try:
            self.collect(self.store.manifest.root)
            rows = list(self.store.rows(self.store.manifest.root))
            document_ids(rows, self.inp.base)
            return pd.DataFrame(rows)
        finally:
            self.store.close()

    def collect(self, window: Window) -> None:
        """Reutiliza janelas concluídas ou inicia tentativa da janela aberta."""
        if window.completed_at:
            return
        if window.children:
            self.collect_children(window)
            return
        before = self.count(window)
        window.total_before = before
        window.observed_at = utc_now()
        if self.pages is None and before > MAX_REGISTROS:
            window.children = self.split(window, before)
            self.store.save()
            self.collect_children(window)
        else:
            self.collect_pages(window, before)

    def collect_children(self, window: Window) -> None:
        """Confere partições e duplicatas antes de concluir o conjunto."""
        for child in window.children:
            self.collect(child)
        self.store.validate_completed_ids(window)
        after = self.count(window)
        if after != window.total_before or sum(child.total_after or 0 for child in window.children) != after:
            raise ValueError("Contagem STF mudou durante a coleta das janelas; resultado não é integral.")
        window.total_after = after
        window.completed_at = utc_now()
        self.store.save()

    def split(self, window: Window, total: int) -> list[Window]:
        """Separa dias sem sobreposição e recusa o residual acima do teto."""
        if window.missing:
            raise ValueError("Residual STF sem data excede o limite de registros; não pode ser fatiado.")
        lower = window.lower or self._input_date("inicio")
        upper = window.upper or self._input_date("fim")
        if lower is None or upper is None:
            return self.discover(window, total)
        start, end = date.fromisoformat(lower), date.fromisoformat(upper)
        if start >= end:
            raise ValueError(f"Dia STF saturado ({lower}): mais de {MAX_REGISTROS} documentos.")
        middle = start + (end - start) // 2
        return [
            Window(lower=start.isoformat(), upper=middle.isoformat()),
            Window(lower=(middle + timedelta(days=1)).isoformat(), upper=end.isoformat()),
        ]

    def _input_date(self, end: str) -> str | None:
        value = self.filters[f"data_{self.axis}_{end}"]
        return datetime.strptime(value, "%d%m%Y").date().isoformat() if value else None

    def discover(self, window: Window, total: int) -> list[Window]:
        """Descobre limites na fonte sem omitir o residual sem data."""
        response = self.request(bounds_payload(self.payload(window), f"{self.axis}_data"))
        if exact_total(response) != total:
            raise ValueError("Contagem STF mudou durante a descoberta dos limites.")
        try:
            bounds = response["result"]["aggregations"]["collection_bounds"]
            missing = bounds["missing"]["doc_count"]
            if (
                not isinstance(missing, int) or isinstance(missing, bool)
                or not 0 <= missing <= total or bounds["doc_count"] != total
            ):
                raise ValueError("Contagem da agregação STF incompatível com os resultados.")
            if missing > MAX_REGISTROS:
                raise ValueError("Residual STF sem data excede o limite de registros.")
            children = []
            if total > missing:
                lower, upper = _bound(bounds["lower"]), _bound(bounds["upper"])
                if lower > upper:
                    raise ValueError("Limites STF invertidos.")
                children.append(Window(lower=lower.isoformat(), upper=upper.isoformat()))
            # Também observa o residual vazio: mudanças posteriores não ficam ocultas.
            children.append(Window(missing=True))
            return children
        except (KeyError, TypeError) as exc:
            raise ValueError("Resposta STF sem agregação de limites/missing válida.") from exc

    def collect_pages(self, window: Window, total: int) -> None:
        """Persiste páginas e confirma a janela após reconciliar contagens."""
        attempt = Attempt(started_at=utc_now(), total_before=total)
        window.attempts.append(attempt)
        self.store.save()
        pages = self.pages if self.pages is not None else range(1, math.ceil(total / self.inp.tamanho_pagina) + 1)
        seen: set[tuple[str, str]] = set()
        for page in pages:
            payload = self.payload(window, page, self.inp.tamanho_pagina)
            response = self.request(payload)
            if exact_total(response) != total:
                raise ValueError("Contagem STF mudou durante a janela.")
            rows = parse_decisoes([response])
            ids = document_ids(rows, self.inp.base)
            expected = max(0, min(payload["size"], total - payload["from"]))
            if len(rows) != expected or seen.intersection(ids):
                raise ValueError("Página STF incompleta ou com IDs duplicados entre páginas.")
            seen.update(ids)
            # Se o processo cair antes de save(), o arquivo órfão fica preservado.
            attempt.pages.append(self.store.page(rows, page))
            self.store.save()
        after = self.count(window)
        if total != after or (self.pages is None and len(seen) != total):
            raise ValueError("Contagem STF mudou ao concluir a janela.")
        attempt.total_after = after
        attempt.completed_at = utc_now()
        window.total_after = after
        window.completed_at = attempt.completed_at
        self.store.save()
