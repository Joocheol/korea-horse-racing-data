"""KRA OpenAPI collector for reproducible public-data releases."""

from .client import KRAClient, service_key_candidates
from .registry import ENDPOINTS, EndpointSpec

__all__ = ["ENDPOINTS", "EndpointSpec", "KRAClient", "service_key_candidates"]
