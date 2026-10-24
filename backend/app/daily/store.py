"""Filesystem layout plus crash-safe, deterministic artifact writers."""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Paths:
    data: Path          # data/daily  : snapshots, dataset, http cache, logs
    models: Path        # models/daily: versions/, champion.json, climatology.npz, static_cells.csv

    @classmethod
    def default(cls) -> "Paths":
        return cls(Path(os.getenv("BADIA_DAILY_DATA_DIR", ROOT / "data" / "daily")),
                   Path(os.getenv("BADIA_DAILY_MODEL_DIR", ROOT / "models" / "daily")))

    @property
    def snapshots(self) -> Path: return self.data / "snapshots"
    @property
    def dataset(self) -> Path: return self.data / "dataset"
    @property
    def dataset_parts(self) -> Path: return self.dataset / "parts"
    @property
    def observation_parts(self) -> Path: return self.dataset_parts / "observations"
    @property
    def forecast_parts(self) -> Path: return self.dataset_parts / "forecasts"
    @property
    def climatology_parts(self) -> Path: return self.dataset_parts / "climatology"
    @property
    def cache(self) -> Path: return self.data / "http_cache"
    @property
    def versions(self) -> Path: return self.models / "versions"
    @property
    def champion_file(self) -> Path: return self.models / "champion.json"
    @property
    def climatology(self) -> Path: return self.models / "climatology.npz"
    @property
    def climatology_mapping(self) -> Path: return self.models / "climatology_mapping.csv"
    @property
    def climatology_metadata(self) -> Path: return self.models / "climatology_metadata.json"
    @property
    def static_cells(self) -> Path: return self.models / "static_cells.csv"
    @property
    def operation_lock(self) -> Path: return self.data / "operation.lock"

    def ensure(self) -> "Paths":
        for p in (self.snapshots, self.dataset, self.observation_parts, self.forecast_parts,
                  self.climatology_parts, self.cache, self.versions):
            p.mkdir(parents=True, exist_ok=True)
        return self


def _atomic_replace(path: Path, writer) -> None:
    """Write in the destination directory and replace only after a complete flush."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as raw:
            writer(raw)
            raw.flush()
            os.fsync(raw.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def write_bytes_atomic(path: Path, data: bytes) -> None:
    _atomic_replace(Path(path), lambda raw: raw.write(data))


def write_text_atomic(path: Path, text: str, encoding: str = "utf-8") -> None:
    write_bytes_atomic(Path(path), text.encode(encoding))


def write_json_atomic(path: Path, obj) -> None:
    payload = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=float)
    write_text_atomic(Path(path), payload)


def write_csv_atomic(frame, path: Path, *, index: bool = False) -> None:
    """Atomically write a CSV; ``.gz`` output has a stable header/mtime and checksum."""
    path = Path(path)

    def writer(raw) -> None:
        if path.suffix == ".gz":
            compressed = gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0)
            text = io.TextIOWrapper(compressed, encoding="utf-8", newline="")
            try:
                frame.to_csv(text, index=index, lineterminator="\n")
                text.flush()
            finally:
                text.close()
        else:
            text = io.TextIOWrapper(raw, encoding="utf-8", newline="", write_through=True)
            try:
                frame.to_csv(text, index=index, lineterminator="\n")
                text.flush()
            finally:
                text.detach()

    _atomic_replace(path, writer)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path):
    return json.loads(Path(path).read_text("utf-8"))
