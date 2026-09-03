class AuthorizationBoundaryError(RuntimeError):
    """Raised instead of selecting behavior outside the authorization matrix."""


class ProductApprovalRequired(AuthorizationBoundaryError):
    """The product contract does not specify the requested behavior."""


class TechnicalVerificationRequired(AuthorizationBoundaryError):
    """The behavior is approved but its platform mechanism is not verified."""

