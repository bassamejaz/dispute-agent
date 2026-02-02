"""Tests for the tools module."""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
import tempfile
import shutil

from src.data.storage import Storage
from src.data.seed import seed_data
from src.models.transaction import Transaction
from src.models.merchant import Merchant
from src.tools.transactions import get_transactions, get_transaction_by_id
from src.tools.merchants import get_merchant_info, search_merchant_by_name
from src.tools.disputes import flag_for_review, get_dispute_status
from src.utils.session import set_current_user_id


@pytest.fixture
def temp_data_dir():
    """Create a temporary data directory for tests."""
    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def seeded_storage(temp_data_dir):
    """Create a storage instance with seeded data."""
    seed_data(temp_data_dir)
    return Storage(temp_data_dir)


@pytest.fixture
def set_user_001():
    """Set the current user to user_001 for tests."""
    token = set_current_user_id("user_001")
    yield
    # Reset is optional since tests run in isolation


@pytest.fixture
def set_user_999():
    """Set the current user to user_999 (nonexistent) for tests."""
    token = set_current_user_id("user_999")
    yield


class TestGetTransactions:
    """Tests for the get_transactions tool."""

    def test_get_all_user_transactions(self, seeded_storage, monkeypatch, set_user_001):
        """Test retrieving all transactions for a user."""
        monkeypatch.setattr("src.tools.transactions.Storage", lambda: seeded_storage)

        result = get_transactions.invoke({})

        assert result["count"] > 0
        assert len(result["transactions"]) > 0
        assert "message" in result

    def test_filter_by_amount(self, seeded_storage, monkeypatch, set_user_001):
        """Test filtering transactions by amount."""
        monkeypatch.setattr("src.tools.transactions.Storage", lambda: seeded_storage)

        result = get_transactions.invoke({
            "amount": 50.0,
        })

        # Should find transactions close to $50
        assert result["count"] > 0
        for txn in result["transactions"]:
            # Parse amount from string like "USD 50.00"
            amount_str = txn["amount"].split()[1]
            amount = Decimal(amount_str)
            # Within 10% tolerance
            assert abs(amount - Decimal("50")) <= Decimal("5")

    def test_filter_by_merchant_name(self, seeded_storage, monkeypatch, set_user_001):
        """Test filtering transactions by merchant name."""
        monkeypatch.setattr("src.tools.transactions.Storage", lambda: seeded_storage)

        result = get_transactions.invoke({
            "merchant_name": "Coffee Palace",
        })

        assert result["count"] > 0
        for txn in result["transactions"]:
            assert "coffee palace" in txn["merchant"].lower()

    def test_filter_by_category(self, seeded_storage, monkeypatch, set_user_001):
        """Test filtering transactions by category."""
        monkeypatch.setattr("src.tools.transactions.Storage", lambda: seeded_storage)

        result = get_transactions.invoke({
            "category": "subscription",
        })

        assert result["count"] > 0
        for txn in result["transactions"]:
            assert txn["category"] == "subscription"

    def test_nonexistent_user(self, seeded_storage, monkeypatch, set_user_999):
        """Test with a user that has no transactions."""
        monkeypatch.setattr("src.tools.transactions.Storage", lambda: seeded_storage)

        result = get_transactions.invoke({})

        assert result["count"] == 0
        assert len(result["transactions"]) == 0

    def test_limit_results(self, seeded_storage, monkeypatch, set_user_001):
        """Test limiting the number of results."""
        monkeypatch.setattr("src.tools.transactions.Storage", lambda: seeded_storage)

        result = get_transactions.invoke({
            "limit": 3,
        })

        assert len(result["transactions"]) <= 3


class TestGetTransactionById:
    """Tests for the get_transaction_by_id tool."""

    def test_found_transaction(self, seeded_storage, monkeypatch, set_user_001):
        """Test retrieving an existing transaction."""
        monkeypatch.setattr("src.tools.transactions.Storage", lambda: seeded_storage)

        result = get_transaction_by_id.invoke({
            "transaction_id": "txn_001",
        })

        assert result["found"] is True
        assert result["transaction"]["id"] == "txn_001"
        assert "merchant" in result["transaction"]

    def test_not_found_transaction(self, seeded_storage, monkeypatch, set_user_001):
        """Test with a nonexistent transaction ID."""
        monkeypatch.setattr("src.tools.transactions.Storage", lambda: seeded_storage)

        result = get_transaction_by_id.invoke({
            "transaction_id": "txn_999",
        })

        assert result["found"] is False

    def test_wrong_user_transaction(self, seeded_storage, monkeypatch, set_user_001):
        """Test accessing another user's transaction."""
        monkeypatch.setattr("src.tools.transactions.Storage", lambda: seeded_storage)

        # txn_021 belongs to user_002
        result = get_transaction_by_id.invoke({
            "transaction_id": "txn_021",
        })

        assert result["found"] is False


class TestGetMerchantInfo:
    """Tests for the get_merchant_info tool."""

    def test_found_merchant(self, seeded_storage, monkeypatch):
        """Test retrieving an existing merchant."""
        monkeypatch.setattr("src.tools.merchants.Storage", lambda: seeded_storage)

        result = get_merchant_info.invoke({"merchant_id": "merch_001"})

        assert result["found"] is True
        assert result["merchant"]["name"] == "Coffee Palace"

    def test_not_found_merchant(self, seeded_storage, monkeypatch):
        """Test with a nonexistent merchant ID."""
        monkeypatch.setattr("src.tools.merchants.Storage", lambda: seeded_storage)

        result = get_merchant_info.invoke({"merchant_id": "merch_999"})

        assert result["found"] is False


class TestSearchMerchantByName:
    """Tests for the search_merchant_by_name tool."""

    def test_exact_name_match(self, seeded_storage, monkeypatch):
        """Test searching by exact merchant name."""
        monkeypatch.setattr("src.tools.merchants.Storage", lambda: seeded_storage)

        result = search_merchant_by_name.invoke({"name": "Amazon"})

        assert result["found"] is True
        assert result["count"] > 0
        assert any("Amazon" in m["name"] for m in result["merchants"])

    def test_alias_match(self, seeded_storage, monkeypatch):
        """Test searching by merchant alias."""
        monkeypatch.setattr("src.tools.merchants.Storage", lambda: seeded_storage)

        result = search_merchant_by_name.invoke({"name": "AMZN"})

        assert result["found"] is True
        # Should find Amazon via its AMZN alias

    def test_no_match(self, seeded_storage, monkeypatch):
        """Test with a name that doesn't match any merchant."""
        monkeypatch.setattr("src.tools.merchants.Storage", lambda: seeded_storage)

        result = search_merchant_by_name.invoke({"name": "NonexistentStore123"})

        assert result["found"] is False


class TestFlagForReview:
    """Tests for the flag_for_review tool."""

    def test_successful_dispute(self, seeded_storage, monkeypatch, set_user_001):
        """Test successfully flagging a transaction for review."""
        monkeypatch.setattr("src.tools.disputes.Storage", lambda: seeded_storage)
        monkeypatch.setattr("src.tools.disputes.AuditLogger", lambda user_id: type("MockLogger", (), {
            "log_dispute_flagged": lambda self, **kwargs: None
        })())

        result = flag_for_review.invoke({
            "transaction_id": "txn_001",
            "complaint": "I don't recognize this charge",
        })

        assert result["success"] is True
        assert "dispute_id" in result
        assert "summary" in result

    def test_nonexistent_transaction(self, seeded_storage, monkeypatch, set_user_001):
        """Test flagging a nonexistent transaction."""
        monkeypatch.setattr("src.tools.disputes.Storage", lambda: seeded_storage)
        monkeypatch.setattr("src.tools.disputes.AuditLogger", lambda user_id: type("MockLogger", (), {})())

        result = flag_for_review.invoke({
            "transaction_id": "txn_999",
            "complaint": "I don't recognize this charge",
        })

        assert result["success"] is False

    def test_wrong_user_transaction(self, seeded_storage, monkeypatch, set_user_001):
        """Test flagging another user's transaction."""
        monkeypatch.setattr("src.tools.disputes.Storage", lambda: seeded_storage)
        monkeypatch.setattr("src.tools.disputes.AuditLogger", lambda user_id: type("MockLogger", (), {})())

        result = flag_for_review.invoke({
            "transaction_id": "txn_021",  # Belongs to user_002
            "complaint": "I don't recognize this charge",
        })

        assert result["success"] is False
