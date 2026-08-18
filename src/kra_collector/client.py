from __future__ import annotations

import hashlib
import json
import os
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

import requests

BASE_URL = "https://apis.data.go.kr/B551015"
SUCCESS_CODES = {"00", "0000", "NORMAL_CODE", "NORMAL SERVICE."}
RETRYABLE_HTTP = {429, 500, 502, 503, 504}
DAILY_QUOTA_RESULT_CODES = {"22"}
RETRYABLE_RESULT_CODES = {"01", "05", "23"}
DEFAULT_OPERATING_CAP = 2_500
PROBE_PATH = "API5/quinellaOddsInfo"
PROBE_PARAMS = {
    "meet": 1,
    "rc_date": "20250308",
    "rc_no": 1,
    "pageNo": 1,
    "numOfRows": 1,
    "_type": "xml",
}


class KRAError(RuntimeError):
    """Base exception for transport or application-envelope failures."""


class KRAAuthenticationError(KRAError):
    """The service key is absent, malformed, or not authorized."""


class KRAResponseError(KRAError):
    """The response is not a successful KRA data envelope."""


class KRARetryableResponseError(KRAError):
    """A temporary KRA application-envelope failure that may be retried."""


class KRAQuotaExceededError(KRAError):
    """The daily quota is exhausted and cannot recover during this run."""


def retry_after_seconds(
    value: str | None, *, now: datetime | None = None
) -> float | None:
    """Parse Retry-After delta-seconds or an RFC HTTP-date."""
    if value is None:
        return None
    stripped = value.strip()
    if stripped.isdigit():
        return float(stripped)
    try:
        target = parsedate_to_datetime(stripped)
    except (TypeError, ValueError, OverflowError):
        return None
    if target.tzinfo is None:
        target = target.replace(tzinfo=UTC)
    current = now or datetime.now(UTC)
    return max(0.0, (target - current).total_seconds())


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


def _raise_application_error(code: str, message: str) -> None:
    error_text = f"{code} {message}".upper()
    if any(
        token in error_text
        for token in ("SERVICE_KEY", "SERVICE KEY", "AUTH", "REGISTERED", "인증")
    ):
        raise KRAAuthenticationError(f"KRA application error: {code or 'unknown'}")
    if code in DAILY_QUOTA_RESULT_CODES:
        raise KRAQuotaExceededError(f"KRA daily quota exhausted: {code or 'unknown'}")
    if code in RETRYABLE_RESULT_CODES:
        raise KRARetryableResponseError(
            f"KRA temporary application error: {code or 'unknown'}"
        )
    if any(
        token in error_text for token in ("DAILY", "QUOTA", "LIMITED_NUMBER", "초과")
    ):
        raise KRAQuotaExceededError(f"KRA daily quota exhausted: {code or 'unknown'}")
    if any(
        token in error_text for token in ("TEMPOR", "UNAVAILABLE", "TOO MANY REQUESTS")
    ):
        raise KRARetryableResponseError(
            f"KRA temporary application error: {code or 'unknown'}"
        )
    raise KRAResponseError(f"KRA application error: {code or 'unknown'} {message}")


def _parse_json(payload: Any) -> ParsedEnvelope:
    if not isinstance(payload, dict):
        raise KRAResponseError("JSON response root is not an object")
    service_error = payload.get("OpenAPI_ServiceResponse", payload)
    if isinstance(service_error, dict):
        common = service_error.get("cmmMsgHeader", service_error)
        if isinstance(common, dict) and any(
            key in common for key in ("returnReasonCode", "returnAuthMsg", "errMsg")
        ):
            code = str(common.get("returnReasonCode", "")).strip()
            message = " ".join(
                str(common.get(key, "")).strip()
                for key in ("returnAuthMsg", "errMsg")
                if common.get(key)
            )
            _raise_application_error(code, message)
    root = payload.get("response", payload)
    if not isinstance(root, dict) or not isinstance(root.get("header"), dict):
        raise KRAResponseError("JSON response is missing the success header")
    if not isinstance(root.get("body"), dict):
        raise KRAResponseError("JSON response is missing the success body")
    header = root["header"]
    body = root["body"]
    result_code = str(header.get("resultCode", root.get("resultCode", ""))).strip()
    result_message = str(header.get("resultMsg", root.get("resultMsg", ""))).strip()
    if not result_code:
        raise KRAResponseError("JSON response is missing resultCode")
    if result_code not in SUCCESS_CODES:
        _raise_application_error(result_code, result_message)

    items = body.get("items", {}) if isinstance(body, dict) else {}
    if isinstance(items, dict):
        items = items.get("item", [])
    rows = [row for row in _as_list(items) if isinstance(row, dict)]
    if "totalCount" not in body:
        raise KRAResponseError("JSON response is missing totalCount")
    total_raw = body["totalCount"]
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
    reason_code = (root.findtext(".//returnReasonCode") or "").strip()
    reason_message = " ".join(
        value.strip()
        for value in (
            root.findtext(".//returnAuthMsg") or "",
            root.findtext(".//errMsg") or "",
        )
        if value.strip()
    )
    if reason_code or reason_message or root.tag.endswith("OpenAPI_ServiceResponse"):
        _raise_application_error(reason_code, reason_message)
    result_code = (root.findtext(".//resultCode") or "").strip()
    result_message = (root.findtext(".//resultMsg") or "").strip()
    if not result_code:
        raise KRAResponseError("XML response is missing resultCode")
    if result_code not in SUCCESS_CODES:
        _raise_application_error(result_code, result_message)
    rows: list[dict[str, Any]] = []
    for item in root.findall(".//items/item"):
        rows.append({child.tag: child.text for child in list(item)})
    total_raw = root.findtext(".//totalCount")
    if total_raw is None:
        raise KRAResponseError("XML response is missing totalCount")
    try:
        total_count = int(total_raw)
    except (TypeError, ValueError) as exc:
        raise KRAResponseError(f"invalid totalCount: {total_raw!r}") from exc
    return ParsedEnvelope(rows, total_count, result_code or "00", result_message, "xml")


def parse_envelope(
    content: bytes, content_type: str = "", expected_format: str | None = None
) -> ParsedEnvelope:
    stripped = content.lstrip()
    if "json" in content_type.lower() or stripped.startswith((b"{", b"[")):
        try:
            parsed = _parse_json(json.loads(content.decode("utf-8-sig")))
            if expected_format and parsed.response_format != expected_format:
                raise KRAResponseError("response format differs from endpoint registry")
            return parsed
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
    parsed = _parse_xml(content)
    if expected_format and parsed.response_format != expected_format:
        raise KRAResponseError("response format differs from endpoint registry")
    return parsed


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
        ledger = os.environ.get("KRA_QUOTA_LEDGER")
        self._quota_ledger = Path(ledger) if ledger else None
        self.service_key, self.key_candidate = self._probe_service_key(service_key)
        self._secret_fingerprints = tuple(
            set(
                secret_fingerprints(service_key) + secret_fingerprints(self.service_key)
            )
        )

    @staticmethod
    def _endpoint_id(path: str) -> str:
        service = path.split("/", 1)[0].lower()
        return service.removesuffix("_1")

    def _calls_today(self, endpoint_id: str) -> int:
        if self._quota_ledger is None or not self._quota_ledger.exists():
            return 0
        today = datetime.now(UTC).date().isoformat()
        count = 0
        for line in self._quota_ledger.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if (
                record.get("utc_date") == today
                and record.get("endpoint_id") == endpoint_id
            ):
                count += 1
        return count

    def _record_call(self, path: str, phase: str) -> None:
        if self._quota_ledger is None:
            return
        endpoint_id = self._endpoint_id(path)
        cap = int(
            os.environ.get(
                f"DATA_GO_KR_OPERATING_CAP_{endpoint_id.upper()}",
                DEFAULT_OPERATING_CAP,
            )
        )
        used = self._calls_today(endpoint_id)
        if used >= cap:
            raise KRAQuotaExceededError(
                f"local operating cap reached for {endpoint_id}: {used}/{cap}"
            )
        now = datetime.now(UTC)
        record = {
            "schema_version": "1",
            "occurred_at_utc": now.isoformat(),
            "utc_date": now.date().isoformat(),
            "endpoint_id": endpoint_id,
            "phase": phase,
        }
        self._quota_ledger.parent.mkdir(parents=True, exist_ok=True)
        with self._quota_ledger.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
            )

    def _probe_service_key(self, raw_service_key: str) -> tuple[str, str]:
        """Select the working key candidate by calling an approved API.

        API5 is used because access to it was independently verified. This keeps
        a credential-format failure distinct from a core endpoint subscription
        failure. No candidate value is included in logs or exceptions.
        """

        failures: list[str] = []
        for label, candidate in service_key_candidates(raw_service_key):
            for attempt in range(1, self.max_attempts + 1):
                try:
                    self._record_call(PROBE_PATH, "credential_probe")
                    response = self.session.get(
                        f"{BASE_URL}/{PROBE_PATH}",
                        params={"serviceKey": candidate, **PROBE_PARAMS},
                        timeout=self.timeout_seconds,
                        headers={
                            "User-Agent": "korea-horse-racing-data/0.1 (+public research)"
                        },
                    )
                except (requests.Timeout, requests.ConnectionError):
                    if attempt < self.max_attempts:
                        time.sleep(min(2 ** (attempt - 1), 30.0))
                        continue
                    failures.append(f"{label}:transport_exhausted")
                    break
                except requests.RequestException:
                    failures.append(f"{label}:transport_fatal")
                    break

                # An encoded key passed through requests(params=...) is
                # double-encoded. Reject that candidate but still try the
                # URL-decoded candidate after a non-retryable HTTP response.
                if response.status_code in RETRYABLE_HTTP:
                    if attempt < self.max_attempts:
                        delay = retry_after_seconds(response.headers.get("Retry-After"))
                        time.sleep(
                            delay
                            if delay is not None
                            else min(2 ** (attempt - 1), 30.0)
                        )
                        continue
                    failures.append(f"{label}:http_{response.status_code}_exhausted")
                    break
                if response.status_code >= 400:
                    failures.append(f"{label}:http_{response.status_code}")
                    break

                try:
                    parse_envelope(
                        response.content,
                        response.headers.get("Content-Type", ""),
                        "xml",
                    )
                except KRAAuthenticationError:
                    failures.append(f"{label}:authentication_rejected")
                    break
                except KRARetryableResponseError:
                    if attempt < self.max_attempts:
                        time.sleep(min(2 ** (attempt - 1), 30.0))
                        continue
                    failures.append(f"{label}:application_retry_exhausted")
                    break
                except KRAResponseError:
                    failures.append(f"{label}:invalid_response")
                    break
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
                self._record_call(path, "data_request")
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
                    delay = retry_after_seconds(response.headers.get("Retry-After"))
                    if attempt < self.max_attempts:
                        time.sleep(
                            delay
                            if delay is not None
                            else min(2 ** (attempt - 1), 30.0)
                        )
                    continue
                if response.status_code >= 400:
                    raise KRAResponseError(f"KRA HTTP error: {response.status_code}")
                content = response.content
                self._assert_body_has_no_secret(content)
                envelope = parse_envelope(
                    content, response.headers.get("Content-Type", ""), "json"
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
