from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .storage import atomic_write_bytes, canonical_json


ALLOWED_STATES = {"pending", "running", "validating", "complete", "failed"}


class Ledger:
    def __init__(self, path: Path) -> None:
        self.path = path
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict) or not isinstance(loaded.get("units", {}), dict):
                raise ValueError("invalid ledger format")
            self.data = loaded
        else:
            self.data: dict[str, Any] = {"schema_version": 2, "units": {}}

    def state(self, key: str) -> str:
        return str(self.data["units"].get(key, {}).get("state", "pending"))

    def update(self, key: str, state: str, **fields: Any) -> None:
        if state not in ALLOWED_STATES:
            raise ValueError(f"invalid ledger state: {state}")
        current = dict(self.data["units"].get(key, {}))
        if state == "complete":
            for stale in ("error_type", "error", "traceback", "partial_raw_paths", "partial_page_count"):
                current.pop(stale, None)
        current.update(fields)
        current["state"] = state
        current["updated_at"] = datetime.now(UTC).isoformat()
        self.data["units"][key] = current
        atomic_write_bytes(self.path, canonical_json(self.data) + b"\n")

    def completed(self) -> set[str]:
        return {key for key, value in self.data["units"].items() if value.get("state") == "complete"}
