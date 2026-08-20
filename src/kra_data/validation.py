from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .client import Page
from .errors import ValidationError


@dataclass(frozen=True)
class ValidationSummary:
    total_count: int
    raw_rows: int
    unique_rows: int
    duplicate_rows: int
    page_count: int


def _row_identity(row: dict[str, Any]) -> str:
    return json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def validate_pages(pages: list[Page]) -> ValidationSummary:
    if not pages:
        raise ValidationError("no pages collected")
    total_count = pages[0].total_count
    if any(page.total_count != total_count for page in pages):
        raise ValidationError("inconsistent totalCount")
    rows = [row for page in pages for row in page.rows]
    identities = [_row_identity(row) for row in rows]
    unique_rows = len(set(identities))
    duplicate_rows = len(rows) - unique_rows
    if len(rows) != total_count:
        raise ValidationError(
            f"row count mismatch: totalCount={total_count}, received={len(rows)}"
        )
    if duplicate_rows:
        raise ValidationError(f"unexplained duplicate rows: {duplicate_rows}")
    return ValidationSummary(total_count, len(rows), unique_rows, duplicate_rows, len(pages))
