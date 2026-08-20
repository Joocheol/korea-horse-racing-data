class CollectionError(RuntimeError):
    """Base class for collection failures."""


class PermanentAPIError(CollectionError):
    """An error that must not be retried."""


class TransientAPIError(CollectionError):
    """An error that may be retried."""


class SchemaError(PermanentAPIError):
    """The response no longer matches the supported schema."""


class ValidationError(CollectionError):
    """Downloaded rows failed completeness checks."""
