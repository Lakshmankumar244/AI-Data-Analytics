from collections.abc import Iterable


_FORBIDDEN_SCOPE_OPERATIONS = frozenset(
    {"ALL", "CREATE", "WRITE", "UPDATE", "DELETE", "SHARE"}
)


def validate_explicit_read_scopes(scopes: Iterable[str]) -> tuple[str, ...]:
    """Enforce D14-POLICY's current explicit-read-scope boundary."""
    normalized = tuple(scope.strip() for scope in scopes)
    if not normalized or any(not scope for scope in normalized):
        raise ValueError("At least one non-empty scope is required")
    for scope in normalized:
        operation = scope.rsplit(".", 1)[-1].upper()
        if operation in _FORBIDDEN_SCOPE_OPERATIONS or operation != "READ":
            raise ValueError(f"Non-read OAuth scope is not authorized: {scope}")
    return normalized

