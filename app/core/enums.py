from enum import StrEnum


class KYCStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    UNDER_REVIEW = "under_review"


class LedgerEntryType(StrEnum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRANSFER = "transfer"
    FEE = "fee"
    REFUND = "refund"
    ADJUSTMENT = "adjustment"
    SYSTEM = "system"


class Currency(StrEnum):
    USD = "USD"
    GHS = "GHS"
    EUR = "EUR"
    GBP = "GBP"


class SystemAccountType(StrEnum):
    CLEARING = "clearing"          # External money in/out
    FEES = "fees"                  # Platform revenue
    OPERATIONAL = "operational"    # Company float / operating capital


class PaymentIntentStatus(StrEnum):
    REQUIRES_PAYMENT_METHOD = "requires_payment_method"
    REQUIRES_CONFIRMATION = "requires_confirmation"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"
    REQUIRES_ACTION = "requires_action"


class PaymentIntentPurpose(StrEnum):
    DEPOSIT = "deposit"          # User funding their own wallet
    WITHDRAWAL = "withdrawal"        # Withdrawing money from own wallet
    TRANSFER = "transfer"        # Internal P2P (can also use direct transfer API)
    REFUND = "refund"            # Skeleton for later
