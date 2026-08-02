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


class Currency(StrEnum):
    USD = "USD"
    GHS = "GHS"
    EUR = "EUR"
    GBP = "GBP"
