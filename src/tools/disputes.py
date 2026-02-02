"""Dispute flagging tool for the agent."""

from datetime import datetime
from typing import Any

from langchain_core.tools import tool

from src.data.storage import Storage
from src.models.dispute import DisputeRecord
from src.utils.logging import AuditLogger
from src.utils.session import get_current_user_id


@tool
def flag_for_review(
    transaction_id: str,
    complaint: str,
    conversation_context: list[dict] | None = None,
) -> dict[str, Any]:
    """Flag a transaction for human review as a dispute.

    This creates a formal dispute record that will be reviewed by a human agent.

    Args:
        transaction_id: The ID of the disputed transaction
        complaint: The user's complaint/reason for dispute
        conversation_context: Optional conversation history for context

    Returns:
        Dictionary with dispute confirmation or error
    """
    storage = Storage()
    user_id = get_current_user_id()
    logger = AuditLogger(user_id=user_id)

    # Verify the transaction exists and belongs to user
    transactions = storage.get_transactions(user_id)
    transaction = None
    for txn in transactions:
        if txn.id == transaction_id:
            transaction = txn
            break

    if transaction is None:
        return {
            "success": False,
            "message": f"Transaction {transaction_id} not found or does not belong to this user.",
        }

    # Check if already disputed
    existing_disputes = storage.get_disputes(user_id)
    for dispute in existing_disputes:
        if dispute.transaction_id == transaction_id and dispute.status != "resolved":
            return {
                "success": False,
                "message": f"Transaction {transaction_id} already has an open dispute (ID: {dispute.id}).",
                "dispute_id": dispute.id,
                "status": dispute.status,
            }

    # Create dispute record
    dispute = DisputeRecord(
        transaction_id=transaction_id,
        user_id=user_id,
        created_at=datetime.now(),
        user_complaint=complaint,
        conversation_context=conversation_context or [],
        status="flagged",
    )

    # Save dispute
    storage.save_dispute(dispute)

    # Log the dispute
    logger.log_dispute_flagged(
        transaction_id=transaction_id,
        dispute_id=dispute.id,
        reason=complaint,
    )

    # Get merchant info for response
    merchant = storage.get_merchant_by_id(transaction.merchant_id)
    merchant_name = merchant.name if merchant else transaction.merchant_id

    return {
        "success": True,
        "dispute_id": dispute.id,
        "message": f"Your dispute has been successfully filed and flagged for review.",
        "summary": {
            "transaction_id": transaction_id,
            "amount": f"{transaction.currency} {transaction.amount:.2f}",
            "merchant": merchant_name,
            "date": transaction.date.strftime("%Y-%m-%d"),
            "complaint": complaint,
        },
        "next_steps": [
            "A human agent will review your dispute within 1-2 business days.",
            "You will receive a notification when the review is complete.",
            f"Your dispute reference number is: {dispute.id}",
        ],
    }


@tool
def get_dispute_status(dispute_id: str) -> dict[str, Any]:
    """Check the status of an existing dispute.

    Args:
        dispute_id: The dispute ID to check

    Returns:
        Dictionary with dispute status or error
    """
    storage = Storage()
    user_id = get_current_user_id()

    dispute = storage.get_dispute_by_id(dispute_id)

    if dispute is None:
        return {
            "found": False,
            "message": f"Dispute {dispute_id} not found.",
        }

    # Security check - ensure dispute belongs to user
    if dispute.user_id != user_id:
        return {
            "found": False,
            "message": "Dispute not found or access denied.",
        }

    # Get transaction info
    transactions = storage.get_transactions(user_id)
    transaction = None
    for txn in transactions:
        if txn.id == dispute.transaction_id:
            transaction = txn
            break

    transaction_summary = None
    if transaction:
        merchant = storage.get_merchant_by_id(transaction.merchant_id)
        transaction_summary = {
            "id": transaction.id,
            "amount": f"{transaction.currency} {transaction.amount:.2f}",
            "merchant": merchant.name if merchant else transaction.merchant_id,
            "date": transaction.date.strftime("%Y-%m-%d"),
        }

    return {
        "found": True,
        "dispute": {
            "id": dispute.id,
            "status": dispute.status,
            "created_at": dispute.created_at.strftime("%Y-%m-%d %H:%M"),
            "complaint": dispute.user_complaint,
            "resolution_notes": dispute.resolution_notes,
        },
        "transaction": transaction_summary,
    }


@tool
def list_user_disputes() -> dict[str, Any]:
    """List all disputes for the current user.

    Returns:
        Dictionary with list of disputes
    """
    storage = Storage()
    user_id = get_current_user_id()

    disputes = storage.get_disputes(user_id)

    if not disputes:
        return {
            "count": 0,
            "disputes": [],
            "message": "You have no disputes on file.",
        }

    dispute_list = []
    for dispute in disputes:
        # Get transaction info
        transactions = storage.get_transactions(user_id)
        transaction = None
        for txn in transactions:
            if txn.id == dispute.transaction_id:
                transaction = txn
                break

        merchant_name = "Unknown"
        amount = "Unknown"
        if transaction:
            merchant = storage.get_merchant_by_id(transaction.merchant_id)
            merchant_name = merchant.name if merchant else transaction.merchant_id
            amount = f"{transaction.currency} {transaction.amount:.2f}"

        dispute_list.append({
            "id": dispute.id,
            "status": dispute.status,
            "created_at": dispute.created_at.strftime("%Y-%m-%d"),
            "transaction_id": dispute.transaction_id,
            "amount": amount,
            "merchant": merchant_name,
        })

    # Sort by creation date (most recent first)
    dispute_list.sort(key=lambda d: d["created_at"], reverse=True)

    return {
        "count": len(dispute_list),
        "disputes": dispute_list,
        "message": f"Found {len(dispute_list)} dispute(s) on file.",
    }
