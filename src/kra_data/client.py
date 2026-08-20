from __future__ import annotations

import json
import random
import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, unquote_plus, urlencode
from urllib.request import Request, urlopen

from .config import BASE_URL, ENDPOINTS
from .errors import PermanentAPIError, SchemaError, TransientAPIError, ValidationError
from .models import RequestUnit


@dataclass(frozen=True)
class Page:
    page_no: int
    total_count: int
    rows: list[dict[str, Any]]
    raw_body: bytes = b""
    response_format: str = "json"


def _check_result_code(code: object, message: object) -> None:
    result_code = str(code or "")
    if result_code not in {"00", "0", "0000"}:
        detail = str(message or "API error")
        if result_code == "99" and ("세션" in detail or "session" in detail.lower()):
            raise TransientAPIError(f"API result {result_code}: {detail}")
        raise PermanentAPIError(f"API result {result_code}: {detail}")


def parse_page(
    payload: Mapping[str, Any],
    page_no: int,
    *,
    raw_body: bytes = b"",
) -> Page:
    try:
        response = payload["response"]
        header = response["header"]
        body = response["body"]
    except (KeyError, TypeError) as exc:
        raise SchemaError("missing response.header or response.body") from exc

    _check_result_code(header.get("resultCode"), header.get("resultMsg"))
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

    return Page(page_no, total_count, rows, raw_body, "json")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(element: ET.Element, name: str) -> ET.Element | None:
    return next((node for node in element if _local_name(node.tag) == name), None)


def _text(element: ET.Element | None, name: str) -> str | None:
    node = _child(element, name) if element is not None else None
    return node.text if node is not None else None


def parse_xml_page(raw_body: bytes, page_no: int) -> Page:
    try:
        root = ET.fromstring(raw_body)
    except ET.ParseError as exc:
        raise SchemaError("response is not valid XML") from exc
    response = root if _local_name(root.tag) == "response" else _child(root, "response")
    header = _child(response, "header") if response is not None else None
    body = _child(response, "body") if response is not None else None
    if header is None or body is None:
        raise SchemaError("missing response.header or response.body")
    _check_result_code(_text(header, "resultCode"), _text(header, "resultMsg"))
    try:
        total_count = int(_text(body, "totalCount") or "")
    except ValueError as exc:
        raise SchemaError("body.totalCount is missing or invalid") from exc

    items = _child(body, "items")
    rows: list[dict[str, Any]] = []
    if items is not None:
        for item in items:
            if _local_name(item.tag) != "item":
                continue
            rows.append({_local_name(field.tag): field.text or "" for field in item})
    return Page(page_no, total_count, rows, raw_body, "xml")


def parse_response(raw_body: bytes, response_format: str, page_no: int) -> Page:
    if response_format == "xml":
        return parse_xml_page(raw_body, page_no)
    if response_format != "json":
        raise ValueError(f"unsupported response format: {response_format}")
    try:
        payload = json.loads(raw_body.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SchemaError("response is not valid JSON") from exc
    if not isinstance(payload, Mapping):
        raise SchemaError("top-level response is not an object")
    return parse_page(payload, page_no, raw_body=raw_body)


def _safe_http_error_body(exc: HTTPError, service_key: str) -> str:
    """Return a bounded HTTP error body without exposing the service key."""
    try:
        raw_body = exc.read(8_192)
    except Exception:
        return ""
    if not raw_body:
        return ""

    detail = " ".join(raw_body.decode("utf-8-sig", errors="replace").split())
    decoded_key = unquote_plus(service_key)
    candidates = {
        service_key,
        decoded_key,
        quote_plus(service_key),
        quote_plus(decoded_key),
    }
    for candidate in sorted((value for value in candidates if value), key=len, reverse=True):
        detail = detail.replace(candidate, "[REDACTED]")
    detail = re.sub(
        r"(?i)(serviceKey(?:=|%3D))[^&\s<\"']+",
        r"\1[REDACTED]",
        detail,
    )
    return detail[:2_000]


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

    def fetch_page(
        self,
        unit: RequestUnit,
        page_no: int,
        num_rows: int,
        *,
        query_overrides: Mapping[str, str | int | None] | None = None,
    ) -> Page:
        endpoint = ENDPOINTS[unit.endpoint]
        params = unit.params(page_no=page_no, num_rows=num_rows)
        if query_overrides is not None:
            for name, value in query_overrides.items():
                if value is None:
                    params.pop(name, None)
                else:
                    params[name] = value
        params["serviceKey"] = self._service_key
        url = f"{BASE_URL}/{endpoint.path}?{urlencode(params)}"
        accept = "application/json" if endpoint.response_format == "json" else "application/xml"
        request = Request(url, headers={"Accept": accept, "User-Agent": "kra-data/0.2"})

        for attempt in range(1, self.max_attempts + 1):
            try:
                with self._opener(request, timeout=self.timeout) as response:
                    raw_body = response.read()
                return parse_response(raw_body, endpoint.response_format, page_no)
            except HTTPError as exc:
                if exc.code == 429 or 500 <= exc.code < 600:
                    error: Exception = TransientAPIError(f"transient HTTP {exc.code}")
                else:
                    detail = _safe_http_error_body(exc, self._service_key)
                    suffix = f"; response body: {detail}" if detail else "; empty response body"
                    raise PermanentAPIError(f"permanent HTTP {exc.code}{suffix}") from exc
            except URLError as exc:
                reason = exc.reason
                detail = f"{type(reason).__name__}: {reason}" if reason is not None else "unknown reason"
                error = TransientAPIError(
                    f"temporary transport failure: {type(exc).__name__} ({detail})"
                )
            except TimeoutError as exc:
                error = TransientAPIError(
                    f"temporary transport failure: {type(exc).__name__} ({exc})"
                )
            except TransientAPIError as exc:
                error = exc

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
