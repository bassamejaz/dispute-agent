"""Merchant lookup tool for the agent."""

from typing import Any

from langchain_core.tools import tool

from src.data.storage import Storage


@tool
def get_merchant_info(merchant_id: str) -> dict[str, Any]:
    """Get detailed information about a merchant.

    Args:
        merchant_id: The merchant's ID

    Returns:
        Dictionary with merchant details or error message
    """
    storage = Storage()
    merchant = storage.get_merchant_by_id(merchant_id)

    if merchant is None:
        return {
            "found": False,
            "message": f"Merchant {merchant_id} not found.",
        }

    return {
        "found": True,
        "merchant": {
            "id": merchant.id,
            "name": merchant.name,
            "category": merchant.category,
            "description": merchant.description,
            "address": merchant.address,
            "phone": merchant.phone,
            "website": merchant.website,
            "common_transaction_types": merchant.common_transaction_types,
            "known_aliases": merchant.known_aliases,
            "parent_company": merchant.parent_company,
        },
    }


@tool
def search_merchant_by_name(name: str) -> dict[str, Any]:
    """Search for a merchant by name or alias.

    Args:
        name: The merchant name or alias to search for

    Returns:
        Dictionary with matching merchant(s) or error message
    """
    storage = Storage()
    merchants = storage.get_merchants()

    matches = []
    for merchant in merchants:
        if merchant.matches_name(name):
            matches.append({
                "id": merchant.id,
                "name": merchant.name,
                "category": merchant.category,
                "description": merchant.description,
                "known_aliases": merchant.known_aliases,
            })

    if not matches:
        return {
            "found": False,
            "message": f"No merchant found matching '{name}'.",
            "suggestion": "Try a different spelling or check if the merchant name appears differently on your statement.",
        }

    return {
        "found": True,
        "count": len(matches),
        "merchants": matches,
    }
