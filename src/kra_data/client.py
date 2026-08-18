from __future__ import annotations

import json
import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import BASE_URL, ENDPOINTS
from .errors import PermanentAPIError, SchemaError, TransientAPIError, ValidationError
from .models import RequestUnit


@dataclass(frozen=True)
class Page:
    page_no: int
    total_count: int
    rows: list[dict[str, Any]]


def parse_page(payload: Mapping[str, Any], page_no: int) -> Page:
    try:
        response = payload["response"]
        header = response["header"]
        body = response["body"]
    except (KeyError, TypeError) as exc:
        raise SchemaError("missing response.header or response.body") from exc

    result_code = str(header.get("resultCode", ""))
    if result_code not in {"00", "0"}:
        message = str(header.get("resultMsg", "API error"))
        raise PermanentAPIError(f"API result {result_code}: {message}")

    try:
        total_count = int(body["totalCount"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SchemaError("body.totalCount is missing or invalid") from exc

    items = body.get("items")
    if items in (None, ""):
        rows: list[dict[str, Any]] = []
    elif isinstance(items, Mapping):
        item = items.get("item", [])
        if isinstance(item, Mapping):
            rows = [dict(item)]
        elif isinstance(item, list) and all(isinstance(row, Mapping) for row in item):
            rows = [dict(row) for row in item]
        else:
            raise SchemaError("body.items.item is not a row or row list")
    else:
        raise SchemaError("body.items is not an object")

    return Page(page_no=page_no, total_count=total_count, rows=rows)


class KRAClient:
    def __init__(
        self,
        service_key: str,
        *,
        timeout: float = 60.0,
        max_attempts: int = 5,
        sleep: Callable[[float], None] = time.sleep,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        if not service_key:
            raise ValueError("service_key is required")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self._service_key = service_key
        self.timeout = timeout
        self.max_attempts = max_attempts
        self._sleep = sleep
        self._opener = opener

    def fetch_page(self, unit: RequestUnit, page_no: int, num_rows: int) -> Page:
        endpoint = ENDPOINTS[unit.endpoint]
        params = unit.params(page_no=page_no, num_rows=num_rows)
        params["serviceKey"] = self._service_key
        url = f"{BASE_URL}/{endpoint.path}?{urlencode(params)}"
        request = Request(url, headers={"Accept": "application/json", "User-Agent": "kra-data/0.1"})

        for attempt in range(1, self.max_attempts + 1):
            try:
                with self._opener(request, timeout=self.timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, Mapping):
                    raise SchemaError("top-level response is not an object")
                return parse_page(payload, page_no)
            except HTTPError as exc:
                if exc.code == 429 or 500 <= exc.code < 600:
                    error: Exception = TransientAPIError(f"transient HTTP {exc.code}")
                else:
                    raise PermanentAPIError(f"permanent HTTP {exc.code}") from exc
            except (URLError, TimeoutError) as exc:
                error = TransientAPIError(f"temporary transport failure: {type(exc).__name__}")
            except json.JSONDecodeError as exc:
                raise SchemaError("response is not valid JSON") from exc

            if attempt == self.max_attempts:
                raise error
            delay = min(60.0, 2 ** (attempt - 1)) + random.uniform(0.0, 0.5)
            self._sleep(delay)

        raise AssertionError("unreachable")

    def collect_unit(
        self,
        unit: RequestUnit,
        num_rows: int = 100_000,
        on_page: Callable[[Page], None] | None = None,
    ) -> list[Page]:
        first = self.fetch_page(unit, 1, num_rows)
        pages = [first]
        if on_page is not None:
            on_page(first)
        expected_pages = max(1, (first.total_count + num_rows - 1) // num_rows)
        for page_no in range(2, expected_pages + 1):
            page = self.fetch_page(unit, page_no, num_rows)
            if page.total_count != first.total_count:
                raise ValidationError("totalCount changed between pages")
            if not page.rows and sum(len(p.rows) for p in pages) < first.total_count:
                raise ValidationError("empty page before totalCount was reached")
            pages.append(page)
            if on_page is not None:
                on_page(page)
        return pages
