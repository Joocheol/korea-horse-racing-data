from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def write_immutable_bytes(path: Path, data: bytes) -> str:
    digest = sha256_bytes(data)
    if path.exists():
        if sha256_bytes(path.read_bytes()) != digest:
            raise FileExistsError(f"immutable raw file already exists with different content: {path}")
        return digest
    atomic_write_bytes(path, data)
    return digest


def write_immutable_json(path: Path, value: Any) -> str:
    return write_immutable_bytes(path, canonical_json(value) + b"\n")
