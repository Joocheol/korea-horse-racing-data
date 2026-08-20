from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .config import ENDPOINTS


@dataclass(frozen=True)
class RequestUnit:
    endpoint: str
    meet: int
    month: str
    pool: str | None = None
    race_date: str | None = None

    def __post_init__(self) -> None:
        if self.endpoint not in ENDPOINTS:
            raise ValueError(f"unknown endpoint: {self.endpoint}")
        if self.meet not in (1, 2, 3):
            raise ValueError(f"unsupported meet: {self.meet}")
        if len(self.month) != 6 or not self.month.isdigit():
            raise ValueError(f"month must be YYYYMM: {self.month}")
        if self.pool not in ENDPOINTS[self.endpoint].pools:
            raise ValueError(f"invalid pool {self.pool!r} for {self.endpoint}")
        if self.race_date is not None:
            if len(self.race_date) != 8 or not self.race_date.isdigit():
                raise ValueError(f"race_date must be YYYYMMDD: {self.race_date}")
            if not self.race_date.startswith(self.month):
                raise ValueError("race_date must belong to month")
            try:
                date.fromisoformat(
                    f"{self.race_date[:4]}-{self.race_date[4:6]}-{self.race_date[6:]}"
                )
            except ValueError as exc:
                raise ValueError(f"race_date is not a calendar date: {self.race_date}") from exc
            if self.endpoint != "results":
                raise ValueError("race_date is currently supported only for results")

    @property
    def key(self) -> str:
        period = self.race_date or self.month
        return f"{period}:m{self.meet}:{self.endpoint}:{self.pool or '-'}"

    @property
    def raw_relative_dir(self) -> str:
        pool = (self.pool or "all").lower()
        result = f"{self.month[:4]}/{self.month}/meet-{self.meet}/{self.endpoint}-{pool}"
        if self.race_date is not None:
            result = f"{result}/date-{self.race_date}"
        return result

    @property
    def staged_relative_path(self) -> str:
        return f"{self.raw_relative_dir}.jsonl"

    def raw_page_relative_path(self, page_no: int) -> str:
        extension = ENDPOINTS[self.endpoint].response_format
        return f"{self.raw_relative_dir}/page-{page_no:05d}.{extension}"

    def params(self, *, page_no: int, num_rows: int) -> dict[str, str | int]:
        endpoint = ENDPOINTS[self.endpoint]
        values: dict[str, str | int] = {
            "pageNo": page_no,
            "numOfRows": num_rows,
            "_type": endpoint.response_format,
            "meet": self.meet,
        }
        if self.race_date is None:
            values["rc_month"] = self.month
        else:
            values["rc_date"] = self.race_date
        if self.pool is not None:
            values["pool"] = self.pool
        return values
