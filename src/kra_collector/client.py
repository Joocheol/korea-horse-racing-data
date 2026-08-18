from __future__ import annotations

import hashlib
import json
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, unquote

import requests

BASE_URL = "https://apis.data.go.kr/B551015"
SUCCESS_CODES = {"00", "0000", "NORMAL_CODE", "NORMAL SERVICE."}
RETRYABLE_HTTP = {429, 500, 502, 503, 504}
RETRYABLE_RESULT_CODES = {"22"}
PROBE_PATH = "API5/quinellaOddsInfo"
PROBE_PARAMS = {
    "meet": 1,
    "rc_date": "20250308",
    "rc_no": 1,
    "pageNo": 1,
    "numOfRows": 1,
    "_type": "json",
}


class KRAError(RuntimeError):
    """Base exception for transport or application-envelope failures."""


class KRAAuthenticationError(KRAError):
    """The service key is absent, malformed, or not authorized."""


class KRAResponseError(KRAError):
    """The response is not a successful KRA data envelope."""


class KRARetryableResponseError(KRAError):
    """A temporary KRA application-envelope failure that may be retried."""


def service_key_candidates(value: str) -> list[tuple[str, str]]:
    """Return candidates without guessing the key format from its appearance."""
    key = value.strip()
    if not key:
        raise KRAAuthenticationError("KRA service key is empty")
    if any(ch.isspace() for ch in key):
        raise KRAAuthenticationError("service key contains whitespace")
    candidates = [("as_provided", key)]
    decoded = unquote(key)
    if decoded != key:
        candidates.append(("url_decoded_once", decoded))
    return candidates


def secret_fingerprints(key: str) -> tuple[bytes, ...]:
    decoded = unquote(key)
    variants = {
        key,
        decoded,
        quote(key, safe=""),
        quote(key, safe="").lower(),
        quote(decoded, safe=""),
        quote(decoded, safe="").lower(),
    }
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
    result_code = str(header.get("resultCode", root.get("resultCode", ""))).strip()
    result_message = str(header.get("resultMsg", root.get("resultMsg", ""))).strip()
    if result_code and result_code not in SUCCESS_CODES:
        error_text = f"{result_code} {result_message}".upper()
        if "SERVICE_KEY" in error_text or "AUTH" in error_text:
            raise KRAAuthenticationError(f"KRA application error: {result_code}")
        if result_code in RETRYABLE_RESULT_CODES or any(
            token in error_text for token in ("LIMIT", "QUOTA", "TEMPOR", "UNAVAILABLE")
        ):
            raise KRARetryableResponseError(
                f"KRA temporary application error: {result_code}"
            )
        raise KRAResponseError(f"KRA application error: {result_code} {result_message}")

    items = body.get("items", {}) if isinstance(body, dict) else {}
    if isinstance(items, dict):
        items = items.get("item", [])
    rows = [row for row in _as_list(items) if isinstance(row, dict)]
    total_raw = (
        body.get("totalCount", len(rows)) if isinstance(body, dict) else len(rows)
    )
    try:
        total_count = int(total_raw)
    except (TypeError, ValueError) as exc:
        raise KRAResponseError(f"invalid totalCount: {total_raw!r}") from exc
    return ParsedEnvelope(
        rows, total_count, result_code or "00", result_message, "json"
    )


def _parse_xml(content: bytes) -> ParsedEnvelope:
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise KRAResponseError("response is neither valid JSON nor XML") from exc
    result_code = (root.findtext(".//resultCode") or "").strip()
    result_message = (root.findtext(".//resultMsg") or "").strip()
    if result_code and result_code not in SUCCESS_CODES:
        error_text = f"{result_code} {result_message}".upper()
        if "SERVICE_KEY" in error_text or "AUTH" in error_text:
            raise KRAAuthenticationError(f"KRA application error: {result_code}")
        if result_code in RETRYABLE_RESULT_CODES or any(
            token in error_text for token in ("LIMIT", "QUOTA", "TEMPOR", "UNAVAILABLE")
        ):
            raise KRARetryableResponseError(
                f"KRA temporary application error: {result_code}"
            )
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
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.minimum_interval_seconds = minimum_interval_seconds
        self.session = session or requests.Session()
        self._last_request_at = 0.0
        self.service_key, self.key_candidate = self._probe_service_key(service_key)
        self._secret_fingerprints = tuple(
            set(
                secret_fingerprints(service_key) + secret_fingerprints(self.service_key)
            )
        )

    def _probe_service_key(self, raw_service_key: str) -> tuple[str, str]:
        """Select the working key candidate by calling an approved API.

        API5 is used because access to it was independently verified. This keeps
        a credential-format failure distinct from a core endpoint subscription
        failure. No candidate value is included in logs or exceptions.
        """

        failures: list[str] = []
        for label, candidate in service_key_candidates(raw_service_key):
            try:
                response = self.session.get(
                    f"{BASE_URL}/{PROBE_PATH}",
                    params={"serviceKey": candidate, **PROBE_PARAMS},
                    timeout=self.timeout_seconds,
                    headers={
                        "User-Agent": "korea-horse-racing-data/0.1 (+public research)"
                    },
                )
            except requests.RequestException as exc:
                raise KRAResponseError(
                    "API5 credential probe could not complete because of a transport error"
                ) from exc

            # An already encoded key passed through requests(params=...) is
            # double-encoded and data.go.kr commonly answers HTTP 400. That is
            # a candidate rejection, not a reason to skip the decoded candidate.
            if response.status_code in RETRYABLE_HTTP or response.status_code >= 500:
                raise KRAResponseError(
                    f"API5 credential probe received retryable HTTP {response.status_code}"
                )
            if response.status_code >= 400:
                failures.append(f"{label}:http_{response.status_code}")
                continue

            try:
                parse_envelope(
                    response.content, response.headers.get("Content-Type", "")
                )
            except KRAAuthenticationError:
                failures.append(f"{label}:authentication_rejected")
            except KRAResponseError:
                failures.append(f"{label}:invalid_response")
            else:
                return candidate, label
        tried = ", ".join(failures) or "no valid candidate"
        raise KRAAuthenticationError(
            "API5 rejected every service-key candidate "
            f"({tried}); the secret is invalid or API5 is not approved"
        )

    def _assert_body_has_no_secret(self, content: bytes) -> None:
        if any(token in content for token in self._secret_fingerprints):
            raise KRAResponseError(
                "response body unexpectedly contains the service key"
            )

    def get(
        self, path: str, params_without_key: dict[str, Any]
    ) -> tuple[bytes, str, ParsedEnvelope]:
        url = f"{BASE_URL}/{path}"
        params = {"serviceKey": self.service_key, **params_without_key}
        last_status: int | None = None
        for attempt in range(1, self.max_attempts + 1):
            elapsed = time.monotonic() - self._last_request_at
            if elapsed < self.minimum_interval_seconds:
                time.sleep(self.minimum_interval_seconds - elapsed)
            try:
                response = self.session.get(
                    url,
                    params=params,
                    timeout=self.timeout_seconds,
                    headers={
                        "User-Agent": "korea-horse-racing-data/0.1 (+public research)"
                    },
                )
                self._last_request_at = time.monotonic()
                if response.status_code in RETRYABLE_HTTP:
                    last_status = response.status_code
                    retry_after = response.headers.get("Retry-After")
                    delay = (
                        float(retry_after)
                        if retry_after and retry_after.isdigit()
                        else 2 ** (attempt - 1)
                    )
                    if attempt < self.max_attempts:
                        time.sleep(min(delay, 30.0))
                    continue
                if response.status_code >= 400:
                    raise KRAResponseError(f"KRA HTTP error: {response.status_code}")
                content = response.content
                self._assert_body_has_no_secret(content)
                envelope = parse_envelope(
                    content, response.headers.get("Content-Type", "")
                )
                return content, response.headers.get("Content-Type", ""), envelope
            except KRAAuthenticationError:
                raise
            except KRAResponseError:
                raise
            except KRARetryableResponseError:
                if attempt < self.max_attempts:
                    time.sleep(min(2 ** (attempt - 1), 30.0))
                    continue
                break
            except (requests.Timeout, requests.ConnectionError):
                if attempt < self.max_attempts:
                    time.sleep(min(2 ** (attempt - 1), 30.0))
                    continue
                break
            except requests.RequestException:
                raise KRAResponseError("KRA transport error") from None
        suffix = f"; last_http_status={last_status}" if last_status is not None else ""
        raise KRARetryableResponseError(
            f"request failed after {self.max_attempts} attempts{suffix}"
        ) from None


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
