"""Transaction lookup tool for the agent."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from langchain_core.tools import tool

from src.config import settings
from src.data.storage import Storage, TransactionFilter
from src.utils.session import get_current_user_id


@tool
def get_transactions(
    amount: float | None = None,
    date: date | None = None,
    merchant_name: str | None = None,
    category: str | None = None,
    status: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Search for user transactions with flexible filters.

    Args:
        amount: Optional amount to search for (with tolerance)
        date: Optional date in ISO format (YYYY-MM-DD) to search around (with tolerance)
        merchant_name: Optional merchant name to search for (fuzzy match)
        category: Optional category filter (food, retail, subscription, etc.)
        status: Optional status filter (posted, pending, refunded)
        limit: Maximum number of results to return (default 10)

    Returns:
        Dictionary with:
        - transactions: List of matching transactions
        - count: Number of matches found
        - message: Human-readable summary
    """
    storage = Storage()
    user_id = get_current_user_id()

    # Resolve merchant name to IDs (like a SQL join)
    merchant_ids = None
    if merchant_name is not None:
        matching_merchants = storage.find_merchants_by_name(merchant_name)
        if not matching_merchants:
            return {
                "transactions": [],
                "count": 0,
                "message": f"No merchant found matching '{merchant_name}'.",
            }
        merchant_ids = [m.id for m in matching_merchants]

    # Build filter for storage query
    # Convert date to datetime for filter (if provided)
    filter_date = datetime.combine(date, datetime.min.time()) if date else None

    filters = TransactionFilter(
        user_id=user_id,
        amount=Decimal(str(amount)) if amount is not None else None,
        amount_tolerance=settings.tolerance_config.amount_tolerance_percent,
        date=filter_date,
        date_tolerance=settings.tolerance_config.date_tolerance_days,
        merchant_ids=merchant_ids,
        category=category,
        status=status,
    )

    # Query with filters at storage level
    transactions = storage.get_transactions(filters=filters)

    if not transactions:
        return {
            "transactions": [],
            "count": 0,
            "message": "No matching transactions found.",
        }

    total_count = len(transactions)

    # Apply limit
    transactions = transactions[:limit]

    # Build response
    txn_dicts = []
    for txn in transactions:
        merchant = storage.get_merchant_by_id(txn.merchant_id)
        merchant_display = merchant.name if merchant else txn.merchant_id

        txn_dicts.append({
            "id": txn.id,
            "amount": f"{txn.currency} {txn.amount:.2f}",
            "date": txn.date.strftime("%Y-%m-%d %H:%M"),
            "merchant": merchant_display,
            "reason": txn.reason,
            "category": txn.category,
            "status": txn.status,
            "card": f"****{txn.card_last4}",
            "location": txn.location or "Online",
        })

    # Generate message
    if total_count == 0:
        message = "No matching transactions found."
    elif total_count == 1:
        message = "Found 1 matching transaction."
    elif total_count > limit:
        message = f"Found {total_count} matching transactions. Showing top {limit}."
    else:
        message = f"Found {total_count} matching transactions."

    return {
        "transactions": txn_dicts,
        "count": total_count,
        "total_shown": len(txn_dicts),
        "message": message,
    }


@tool
def get_transaction_by_id(transaction_id: str) -> dict[str, Any]:
    """Get a specific transaction by ID.

    Args:
        transaction_id: The transaction ID

    Returns:
        Transaction details or error message
    """
    storage = Storage()
    user_id = get_current_user_id()

    # Get user's transactions (filtered at storage level)
    transactions = storage.get_transactions(user_id=user_id)

    for txn in transactions:
        if txn.id == transaction_id:
            merchant = storage.get_merchant_by_id(txn.merchant_id)

            return {
                "found": True,
                "transaction": {
                    "id": txn.id,
                    "amount": f"{txn.currency} {txn.amount:.2f}",
                    "raw_amount": float(txn.amount),
                    "currency": txn.currency,
                    "date": txn.date.strftime("%Y-%m-%d %H:%M"),
                    "merchant": merchant.name if merchant else txn.merchant_id,
                    "merchant_id": txn.merchant_id,
                    "reason": txn.reason,
                    "category": txn.category,
                    "status": txn.status,
                    "card": f"****{txn.card_last4}",
                    "location": txn.location or "Online",
                    "fees": float(txn.fees) if txn.fees else None,
                },
                "merchant_info": merchant.to_display_dict() if merchant else None,
            }

    return {
        "found": False,
        "message": f"Transaction {transaction_id} not found for this user.",
    }
