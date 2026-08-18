from __future__ import annotations

from dataclasses import dataclass

from .config import ENDPOINTS


@dataclass(frozen=True, order=True)
class RequestUnit:
    endpoint: str
    meet: int
    month: str
    pool: str | None = None

    def __post_init__(self) -> None:
        if self.endpoint not in ENDPOINTS:
            raise ValueError(f"unknown endpoint: {self.endpoint}")
        if self.meet not in (1, 2, 3):
            raise ValueError(f"unsupported meet: {self.meet}")
        if len(self.month) != 6 or not self.month.isdigit():
            raise ValueError(f"month must be YYYYMM: {self.month}")
        if self.pool not in ENDPOINTS[self.endpoint].pools:
            raise ValueError(f"invalid pool {self.pool!r} for {self.endpoint}")

    @property
    def key(self) -> str:
        return f"{self.month}:m{self.meet}:{self.endpoint}:{self.pool or '-'}"

    @property
    def relative_path(self) -> str:
        pool = (self.pool or "all").lower()
        return f"{self.month[:4]}/{self.month}/meet-{self.meet}/{self.endpoint}-{pool}.json"

    def params(self, *, page_no: int, num_rows: int) -> dict[str, str | int]:
        values: dict[str, str | int] = {
            "pageNo": page_no,
            "numOfRows": num_rows,
            "_type": "json",
            "meet": self.meet,
            "rc_month": self.month,
        }
        if self.pool is not None:
            values["pool"] = self.pool
        return values
