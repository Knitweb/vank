"""Shared validation helpers for knitweb_vbank modules.

All values on the knitweb_vbank record path are integer-only (canonical-CBOR
safe; no floats). These helpers enforce that invariant at construction time and
are the single source of truth for the error messages users see.
"""

from __future__ import annotations

__all__ = ["require_int", "require_text"]


def require_int(
    name: str,
    value: object,
    *,
    minimum: int,
    maximum: int | None = None,
) -> int:
    """Validate that *value* is a plain int within [minimum, maximum].

    Booleans are rejected (``bool`` is a subclass of ``int`` in Python but
    carries semantic meaning that makes it wrong as a ledger quantity).
    """
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be int, not {type(value).__name__}")
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum} (got {value})")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be <= {maximum} (got {value})")
    return value  # type: ignore[return-value]


def require_text(name: str, value: object) -> str:
    """Validate that *value* is a non-empty string."""
    if not isinstance(value, str) or not value:
        raise TypeError(f"{name} must be a non-empty str")
    return value  # type: ignore[return-value]
