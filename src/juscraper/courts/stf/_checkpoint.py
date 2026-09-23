"""Checkpoint de páginas STF: dados duráveis antes do avanço do manifesto."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, TextIO
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> str:
    """Carimba observações em UTC com precisão de milissegundos."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Record(BaseModel):
    """Recusa campos desconhecidos e coerções no manifesto."""

    model_config = ConfigDict(extra="forbid", strict=True)


class Page(Record):
    """Identifica a página imutável pelo arquivo e pelo checksum."""

    file: str = Field(pattern=r"^[a-f0-9]{32}\.json$")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    number: int = Field(ge=1)
    count: int = Field(ge=0)


class Attempt(Record):
    """Separa páginas de tentativas que não podem ser unidas."""

    started_at: str
    total_before: int = Field(ge=0)
    pages: list[Page] = Field(default_factory=list)
    total_after: int | None = Field(default=None, ge=0)
    completed_at: str | None = None


class Window(Record):
    """Registra cobertura e tentativas de um intervalo ou residual sem data."""

    lower: str | None = None
    upper: str | None = None
    missing: bool = False
    total_before: int | None = Field(default=None, ge=0)
    total_after: int | None = Field(default=None, ge=0)
    observed_at: str | None = None
    completed_at: str | None = None
    children: list[Window] = Field(default_factory=list)
    attempts: list[Attempt] = Field(default_factory=list)


class Manifest(Record):
    """Vincula páginas à consulta e à referência temporal da ordenação."""

    version: Literal[1]
    identity: dict
    reference_time: str
    root: Window


def document_ids(rows: list[dict], base: str) -> list[tuple[str, str]]:
    """Exige identidade por decisão, sem substituir ID pelo processo."""
    ids = []
    for row in rows:
        if row.get("base") != base or not isinstance(row.get("id"), str) or not row["id"].strip():
            raise ValueError("Documento STF sem identidade válida (base, id).")
        ids.append((row["base"], row["id"]))
    if len(set(ids)) != len(ids):
        raise ValueError("IDs de documentos STF duplicados na página.")
    return ids


def _sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class Checkpoint:
    """Persiste páginas antes do manifesto, com uma única escrita por diretório."""

    def __init__(self, directory, resume: bool, identity: dict):
        if resume and directory is None:
            raise ValueError("resume=True exige checkpoint_dir.")
        self.directory = Path(directory) if directory is not None else None
        self.memory: dict[str, list[dict]] = {}
        self.manifest = Manifest(version=1, identity=identity, reference_time=utc_now(), root=Window())
        self._lock: TextIO | None = None
        if self.directory is None:
            return
        try:
            self._open(self.directory, resume, identity)
        except BaseException:
            self.close()
            raise

    def _open(self, directory: Path, resume: bool, identity: dict) -> None:
        import fcntl  # O bloqueio termina também quando o processo morre.

        if resume and not directory.is_dir():
            raise ValueError("Checkpoint inexistente para retomada.")
        directory.mkdir(parents=True, exist_ok=True)
        _sync_directory(directory.parent)
        if not resume and any(directory.iterdir()):
            raise ValueError("checkpoint_dir ocupado; use resume=True ou outro diretório.")
        self._lock = (directory / ".lock").open("a", encoding="utf-8")
        try:
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Checkpoint já está em uso.") from exc
        path = directory / "manifest.json"
        if resume:
            try:
                self.manifest = Manifest.model_validate_json(path.read_text(encoding="utf-8"))
                if self.manifest.identity != identity:
                    raise ValueError("Checkpoint incompatível com a consulta ou contrato atual.")
                datetime.fromisoformat(self.manifest.reference_time)
                self._validate(self.manifest.root)
                self.validate_completed_ids(self.manifest.root)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise ValueError(f"Checkpoint incompatível ou corrompido: {exc}") from exc
        else:
            if any(p.name != ".lock" for p in directory.iterdir()):
                raise ValueError("checkpoint_dir ocupado.")
            self.save()

    def _validate(self, window: Window) -> None:
        for bound in (window.lower, window.upper):
            if bound is not None:
                date.fromisoformat(bound)
        if window.lower and window.upper and window.lower > window.upper:
            raise ValueError("Intervalo de checkpoint invertido.")
        if window.missing and (window.lower or window.upper or window.children):
            raise ValueError("Residual de checkpoint com intervalo ou filhos.")
        if window.children:
            self._validate_partition(window)
        for attempt in window.attempts:
            seen: set[tuple[str, str]] = set()
            numbers = set()
            for page in attempt.pages:
                rows = self.read(page)
                ids = document_ids(rows, self.manifest.identity["base"])
                if seen.intersection(ids) or page.number in numbers:
                    raise ValueError("Páginas duplicadas no checkpoint.")
                seen.update(ids)
                numbers.add(page.number)
            if attempt.completed_at:
                self._validate_attempt(attempt)
                if self.manifest.identity["pages"] is None and len(seen) != attempt.total_before:
                    raise ValueError("Tentativa concluída com páginas faltantes.")
        for child in window.children:
            self._validate(child)
        if window.completed_at:
            if window.total_before is None or window.total_before != window.total_after:
                raise ValueError("Janela concluída com contagens diferentes.")
            if window.children:
                if not all(child.completed_at for child in window.children):
                    raise ValueError("Janela concluída com filhos incompletos.")
                if sum(child.total_after or 0 for child in window.children) != window.total_after:
                    raise ValueError("Partição com contagens inconsistentes.")
            elif not window.attempts or not window.attempts[-1].completed_at:
                raise ValueError("Janela concluída sem tentativa concluída.")
            elif window.attempts[-1].total_after != window.total_after:
                raise ValueError("Janela e tentativa com contagens diferentes.")

    def _completed_rows(self, window: Window):
        if window.children:
            for child in window.children:
                yield from self._completed_rows(child)
        elif window.completed_at:
            yield from self.rows(window)

    def validate_completed_ids(self, window: Window) -> None:
        """Impede concluir ou retomar janelas com identidades repetidas."""
        seen: set[tuple[str, str]] = set()
        for row in self._completed_rows(window):
            identity = (row["base"], row["id"])
            if identity in seen:
                raise ValueError("IDs de documentos STF duplicados entre janelas concluídas.")
            seen.add(identity)

    def _validate_partition(self, window: Window) -> None:
        if window.total_before is None or any(attempt.completed_at for attempt in window.attempts):
            raise ValueError("Partição sem contagem ou com tentativa concluída.")
        if len(window.children) != 2:
            raise ValueError("Partição de checkpoint inválida.")
        left, right = window.children
        if not left.lower or not left.upper:
            raise ValueError("Partição sem limites.")
        if right.missing:
            return
        if not right.lower or not right.upper or left.missing:
            raise ValueError("Partição sem limites.")
        if date.fromisoformat(left.upper) + timedelta(days=1) != date.fromisoformat(right.lower):
            raise ValueError("Partição com lacuna ou sobreposição.")
        if (window.lower and window.lower != left.lower) or (window.upper and window.upper != right.upper):
            raise ValueError("Partição não cobre os limites da janela.")

    def _validate_attempt(self, attempt: Attempt) -> None:
        from .download import MAX_REGISTROS

        size = self.manifest.identity["page_size"]
        requested = self.manifest.identity["pages"]
        numbers = list(range(1, (attempt.total_before + size - 1) // size + 1)) if requested is None else requested
        if attempt.total_after != attempt.total_before or [page.number for page in attempt.pages] != numbers:
            raise ValueError("Tentativa concluída com contagens ou páginas inconsistentes.")
        for page in attempt.pages:
            offset = (page.number - 1) * size
            expected = max(0, min(size, MAX_REGISTROS - offset, attempt.total_before - offset))
            if page.count != expected:
                raise ValueError("Página de checkpoint incompleta.")

    def _write(self, path: Path, data: bytes) -> None:
        with path.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        _sync_directory(path.parent)

    def save(self) -> None:
        """Persiste e substitui o manifesto atomicamente."""
        if self.directory is None:
            return
        temporary = self.directory / f"manifest-{uuid4().hex}.tmp"
        self._write(temporary, self.manifest.model_dump_json(indent=2).encode("utf-8"))
        temporary.replace(self.directory / "manifest.json")
        _sync_directory(self.directory)

    def page(self, rows: list[dict], number: int) -> Page:
        """Persiste uma página imutável antes de incorporá-la ao progresso."""
        name = f"{uuid4().hex}.json"
        data = json.dumps(rows, ensure_ascii=False, allow_nan=False).encode("utf-8")
        if self.directory is None:
            self.memory[name] = rows
        else:
            self._write(self.directory / name, data)
        return Page(file=name, sha256=hashlib.sha256(data).hexdigest(), number=number, count=len(rows))

    def read(self, page: Page) -> list[dict]:
        """Confere o checksum antes de consumir uma página persistida."""
        if self.directory is None:
            return self.memory[page.file]
        path = self.directory / page.file
        if path.is_symlink():
            raise ValueError("Página de checkpoint não pode ser link simbólico.")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != page.sha256:
            raise ValueError("Checksum de página inválido.")
        rows = json.loads(data)
        if not isinstance(rows, list) or len(rows) != page.count or any(not isinstance(row, dict) for row in rows):
            raise ValueError("Conteúdo de página inválido.")
        return rows

    def rows(self, window: Window):
        """Lê apenas a tentativa concluída de cada folha."""
        if not window.completed_at:
            raise ValueError("Coleta incompleta.")
        if window.children:
            for child in window.children:
                yield from self.rows(child)
        else:
            for page in window.attempts[-1].pages:
                yield from self.read(page)

    def close(self) -> None:
        """Libera o bloqueio do diretório sem apagar o checkpoint."""
        if self._lock is not None:
            self._lock.close()
            self._lock = None
