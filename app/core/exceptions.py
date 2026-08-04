from fastapi import HTTPException, status


class InsufficientFundsError(HTTPException):
    def __init__(self, detail: str = "Insufficient funds"):
        super().__init__(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=detail)


class WalletNotFoundError(HTTPException):
    def __init__(self):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found")


class ConcurrentModificationError(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="Wallet was modified concurrently. Please retry.",
        )


class IdempotencyConflictError(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency key already used with different parameters",
        )


class UnbalancedTransactionError(Exception):
    """Internal – should never reach the client."""
    pass


class InvalidStateTransitionError(Exception):
    def __init__(self, current: str, target: str):
        super().__init__(f"Cannot transition from '{current}' to '{target}'")