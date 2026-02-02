"""Transaction model."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class Transaction(BaseModel):
    """Represents a financial transaction."""

    id: str = Field(description="Unique transaction identifier")
    user_id: str = Field(description="User who made the transaction")
    amount: Decimal = Field(description="Transaction amount")
    currency: str = Field(default="USD", description="Currency code (USD, EUR, GBP, etc.)")
    date: datetime = Field(description="Transaction date and time")
    merchant_id: str = Field(description="Merchant identifier")
    reason: str = Field(description="Short human-readable description")
    category: str = Field(description="Transaction category (food, subscription, retail, etc.)")
    card_last4: str = Field(description="Last 4 digits of the card used")
    location: str | None = Field(default=None, description="Transaction location if available")
    fees: Decimal | None = Field(default=None, description="Any associated fees")
    status: Literal["posted", "pending", "refunded"] = Field(
        default="posted", description="Transaction status"
    )

    def to_display_dict(self) -> dict:
        """Return a dictionary suitable for display to users."""
        return {
            "id": self.id,
            "amount": f"{self.currency} {self.amount:.2f}",
            "date": self.date.strftime("%Y-%m-%d %H:%M"),
            "merchant_id": self.merchant_id,
            "reason": self.reason,
            "category": self.category,
            "card": f"****{self.card_last4}",
            "location": self.location or "N/A",
            "status": self.status,
        }

    def matches_amount(self, target_amount: Decimal, tolerance_percent: float) -> bool:
        """Check if transaction amount matches within tolerance."""
        if self.amount == 0:
            return target_amount == 0
        diff = abs(self.amount - target_amount) / self.amount
        return diff <= tolerance_percent / 100

    def matches_date(self, target_date: datetime, tolerance_days: int) -> bool:
        """Check if transaction date matches within tolerance."""
        diff = abs((self.date.date() - target_date.date()).days)
        return diff <= tolerance_days
