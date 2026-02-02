"""Tests for PII masking utilities."""

import pytest
from src.utils.pii import _mask_pii_presidio, _mask_pii_regex, mask_pii


class TestMaskPiiPresidio:
    """Tests for Presidio-based PII masking."""

    def test_masks_person_names(self):
        text = "John Smith made a purchase"
        result = _mask_pii_presidio(text)
        assert "John Smith" not in result
        assert "[REDACTED_PERSON]" in result

    def test_masks_credit_card(self):
        text = "Card number is 4111111111111111"
        result = _mask_pii_presidio(text)
        assert "4111111111111111" not in result
        assert "[REDACTED_CREDIT_CARD]" in result

    def test_masks_email(self):
        text = "Contact me at john.doe@example.com"
        result = _mask_pii_presidio(text)
        assert "john.doe@example.com" not in result
        assert "[REDACTED_EMAIL]" in result

    def test_masks_phone_number(self):
        text = "Call me at 555-123-4567"
        result = _mask_pii_presidio(text)
        assert "555-123-4567" not in result
        assert "[REDACTED_PHONE]" in result

    def test_masks_ssn(self):
        # Note: Presidio may classify SSN-like patterns as phone numbers
        # since they have similar formats. The key is that it gets redacted.
        # The hybrid approach (regex first) handles SSNs correctly.
        text = "My social security number is 078-05-1120"
        result = _mask_pii_presidio(text)
        assert "078-05-1120" not in result
        # Accept either SSN or PHONE redaction (similar patterns)
        assert "[REDACTED_SSN]" in result or "[REDACTED_PHONE]" in result

    def test_masks_location(self):
        text = "Transaction at New York store"
        result = _mask_pii_presidio(text)
        assert "[REDACTED_LOCATION]" in result

    def test_masks_date_time(self):
        text = "Purchase made on January 15th, 2024"
        result = _mask_pii_presidio(text)
        assert "[REDACTED_DATETIME]" in result

    def test_no_pii_returns_unchanged(self):
        text = "This is a simple message with no PII"
        result = _mask_pii_presidio(text)
        assert result == text

    def test_empty_string(self):
        result = _mask_pii_presidio("")
        assert result == ""

    def test_multiple_pii_entities(self):
        text = "John Smith's email is john@test.com and phone is 555-123-4567"
        result = _mask_pii_presidio(text)
        assert "John Smith" not in result
        assert "john@test.com" not in result
        assert "555-123-4567" not in result


class TestMaskPiiRegex:
    """Tests for regex-based PII masking."""

    def test_masks_credit_card_with_dashes(self):
        text = "Card: 4111-1111-1111-1111"
        result = _mask_pii_regex(text)
        assert "[REDACTED_CREDIT_CARD]" in result

    def test_masks_credit_card_with_spaces(self):
        text = "Card: 4111 1111 1111 1111"
        result = _mask_pii_regex(text)
        assert "[REDACTED_CREDIT_CARD]" in result

    def test_masks_ssn(self):
        text = "SSN: 123-45-6789"
        result = _mask_pii_regex(text)
        assert "[REDACTED_SSN]" in result

    def test_masks_email(self):
        text = "Email: test@example.com"
        result = _mask_pii_regex(text)
        assert "[REDACTED_EMAIL]" in result

    def test_masks_phone(self):
        text = "Phone: (555) 123-4567"
        result = _mask_pii_regex(text)
        assert "[REDACTED_PHONE]" in result

    def test_masks_routing_number(self):
        text = "Routing: 021000021"
        result = _mask_pii_regex(text)
        assert "[REDACTED_ROUTING]" in result


class TestMaskPiiHybrid:
    """Tests for the hybrid mask_pii function."""

    def test_hybrid_masks_all_pii(self):
        text = "John Smith (SSN: 123-45-6789) paid $50 with card 4111-1111-1111-1111"
        result = mask_pii(text)
        assert "John Smith" not in result
        assert "123-45-6789" not in result
        assert "4111-1111-1111-1111" not in result

    def test_presidio_disabled(self):
        text = "John Smith paid with card 4111-1111-1111-1111"
        result = mask_pii(text, use_presidio=False)
        # Regex masks the card
        assert "4111-1111-1111-1111" not in result
        # But without Presidio, name is not masked
        assert "John Smith" in result

    def test_empty_returns_empty(self):
        assert mask_pii("") == ""
        assert mask_pii(None) is None
