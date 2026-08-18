"""KRA OpenAPI collector for reproducible public-data releases."""

from .client import KRAClient, normalize_service_key
from .registry import ENDPOINTS, EndpointSpec

__all__ = ["ENDPOINTS", "EndpointSpec", "KRAClient", "normalize_service_key"]

