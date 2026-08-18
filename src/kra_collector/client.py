from __future__ import annotations

import hashlib
import json
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, unquote

import requests


BASE_URL = "https://apis.data.go.kr/B551015"
SUCCESS_CODES = {"00", "0000", "NORMAL_CODE", "NORMAL SERVICE."}
RETRYABLE_HTTP = {429, 500, 502, 503, 504}
ENCODED_TOKEN = re.compile(r"%(?:25|2B|2F|3D)", re.IGNORECASE)


class KRAError(RuntimeError):
    """Base exception for transport or application-envelope failures."""


class KRAAuthenticationError(KRAError):
    """The service key is absent, malformed, or not authorized."""


class KRAResponseError(KRAError):
    """The response is not a successful KRA data envelope."""


def normalize_service_key(value: str) -> tuple[str, str]:
    """Return a decoding-form service key and the detected input form.

    data.go.kr exposes the same key in decoding form (with +, / and =) and in
    percent-encoded form. requests(params=...) must receive the decoding form;
    otherwise each '%' becomes '%25'. Exactly one unquote is therefore applied
    only when encoded reserved characters are detected.
    """

    key = value.strip()
    if not key:
        raise KRAAuthenticationError("KRA service key is empty")

    input_form = "encoding" if ENCODED_TOKEN.search(key) else "decoding"
    normalized = unquote(key) if input_form == "encoding" else key

    if ENCODED_TOKEN.search(normalized):
        raise KRAAuthenticationError(
            "service key remains percent-encoded after one normalization pass"
        )
    if any(ch.isspace() for ch in normalized):
        raise KRAAuthenticationError("service key contains whitespace")
    return normalized, input_form


def secret_fingerprints(key: str) -> tuple[bytes, ...]:
    variants = {key, quote(key, safe=""), quote(key, safe="").lower()}
    return tuple(v.encode("utf-8") for v in variants if v)


@dataclass(frozen=True)
class ParsedEnvelope:
    rows: list[dict[str, Any]]
    total_count: int
    result_code: str
    result_message: str
    response_format: str


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _parse_json(payload: Any) -> ParsedEnvelope:
    if not isinstance(payload, dict):
        raise KRAResponseError("JSON response root is not an object")
    root = payload.get("response", payload)
    header = root.get("header", {}) if isinstance(root, dict) else {}
    body = root.get("body", {}) if isinstance(root, dict) else {}
    result_code = str(
        header.get("resultCode", root.get("resultCode", ""))
    ).strip()
    result_message = str(
        header.get("resultMsg", root.get("resultMsg", ""))
    ).strip()
    if result_code and result_code not in SUCCESS_CODES:
        if "SERVICE_KEY" in result_code.upper() or "AUTH" in result_code.upper():
            raise KRAAuthenticationError(f"KRA application error: {result_code}")
        raise KRAResponseError(f"KRA application error: {result_code} {result_message}")

    items = body.get("items", {}) if isinstance(body, dict) else {}
    if isinstance(items, dict):
        items = items.get("item", [])
    rows = [row for row in _as_list(items) if isinstance(row, dict)]
    total_raw = body.get("totalCount", len(rows)) if isinstance(body, dict) else len(rows)
    try:
        total_count = int(total_raw)
    except (TypeError, ValueError) as exc:
        raise KRAResponseError(f"invalid totalCount: {total_raw!r}") from exc
    return ParsedEnvelope(rows, total_count, result_code or "00", result_message, "json")


def _parse_xml(content: bytes) -> ParsedEnvelope:
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise KRAResponseError("response is neither valid JSON nor XML") from exc
    result_code = (root.findtext(".//resultCode") or "").strip()
    result_message = (root.findtext(".//resultMsg") or "").strip()
    if result_code and result_code not in SUCCESS_CODES:
        if "SERVICE_KEY" in result_code.upper() or "AUTH" in result_code.upper():
            raise KRAAuthenticationError(f"KRA application error: {result_code}")
        raise KRAResponseError(f"KRA application error: {result_code} {result_message}")
    rows: list[dict[str, Any]] = []
    for item in root.findall(".//items/item"):
        rows.append({child.tag: child.text for child in list(item)})
    total_raw = root.findtext(".//totalCount") or len(rows)
    try:
        total_count = int(total_raw)
    except (TypeError, ValueError) as exc:
        raise KRAResponseError(f"invalid totalCount: {total_raw!r}") from exc
    return ParsedEnvelope(rows, total_count, result_code or "00", result_message, "xml")


def parse_envelope(content: bytes, content_type: str = "") -> ParsedEnvelope:
    stripped = content.lstrip()
    if "json" in content_type.lower() or stripped.startswith((b"{", b"[")):
        try:
            return _parse_json(json.loads(content.decode("utf-8-sig")))
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
    return _parse_xml(content)


class KRAClient:
    def __init__(
        self,
        service_key: str,
        *,
        timeout_seconds: float = 60.0,
        max_attempts: int = 5,
        minimum_interval_seconds: float = 0.05,
        session: requests.Session | None = None,
    ) -> None:
        self.service_key, self.input_key_form = normalize_service_key(service_key)
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.minimum_interval_seconds = minimum_interval_seconds
        self.session = session or requests.Session()
        self._last_request_at = 0.0
        self._secret_fingerprints = secret_fingerprints(self.service_key)

    def _assert_body_has_no_secret(self, content: bytes) -> None:
        if any(token in content for token in self._secret_fingerprints):
            raise KRAResponseError("response body unexpectedly contains the service key")

    def get(self, path: str, params_without_key: dict[str, Any]) -> tuple[bytes, str, ParsedEnvelope]:
        url = f"{BASE_URL}/{path}"
        params = {"serviceKey": self.service_key, **params_without_key}
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            elapsed = time.monotonic() - self._last_request_at
            if elapsed < self.minimum_interval_seconds:
                time.sleep(self.minimum_interval_seconds - elapsed)
            try:
                response = self.session.get(
                    url,
                    params=params,
                    timeout=self.timeout_seconds,
                    headers={"User-Agent": "korea-horse-racing-data/0.1 (+public research)"},
                )
                self._last_request_at = time.monotonic()
                if response.status_code in RETRYABLE_HTTP:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after and retry_after.isdigit() else 2 ** (attempt - 1)
                    time.sleep(min(delay, 30.0))
                    continue
                response.raise_for_status()
                content = response.content
                self._assert_body_has_no_secret(content)
                envelope = parse_envelope(content, response.headers.get("Content-Type", ""))
                return content, response.headers.get("Content-Type", ""), envelope
            except KRAAuthenticationError:
                raise
            except (requests.RequestException, KRAResponseError) as exc:
                last_error = exc
                if attempt < self.max_attempts:
                    time.sleep(min(2 ** (attempt - 1), 30.0))
                    continue
                break
        raise KRAResponseError(f"request failed after {self.max_attempts} attempts") from last_error


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()

