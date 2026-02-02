"""Merchant model."""

from pydantic import BaseModel, Field


class Merchant(BaseModel):
    """Represents a merchant."""

    id: str = Field(description="Unique merchant identifier")
    name: str = Field(description="Merchant display name")
    category: str = Field(description="Business category")
    description: str = Field(description="Brief description of the merchant")
    address: str | None = Field(default=None, description="Physical address")
    phone: str | None = Field(default=None, description="Contact phone number")
    website: str | None = Field(default=None, description="Website URL")
    common_transaction_types: list[str] = Field(
        default_factory=list, description="Common types of transactions"
    )
    known_aliases: list[str] = Field(
        default_factory=list, description="Known aliases (e.g., 'AMZN', 'Amazon.com')"
    )
    parent_company: str | None = Field(
        default=None, description="Parent company if applicable"
    )
    dispute_rate: float = Field(
        default=0.0, description="Historical dispute percentage"
    )

    def matches_name(self, query: str) -> bool:
        """Check if merchant name or aliases match query."""
        query_lower = query.lower()
        if query_lower in self.name.lower():
            return True
        for alias in self.known_aliases:
            if query_lower in alias.lower():
                return True
        return False

    def to_display_dict(self) -> dict:
        """Return a dictionary suitable for display to users."""
        return {
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "address": self.address or "N/A",
            "phone": self.phone or "N/A",
            "website": self.website or "N/A",
        }
