"""PII masking utilities."""

import re
import hashlib
from decimal import Decimal
from typing import Optional

from presidio_analyzer import AnalyzerEngine, RecognizerResult
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig


# Initialize Presidio engines (lazy loading)
_analyzer: Optional[AnalyzerEngine] = None
_anonymizer: Optional[AnonymizerEngine] = None


def _get_analyzer() -> AnalyzerEngine:
    """Get or create the Presidio analyzer engine."""
    global _analyzer
    if _analyzer is None:
        _analyzer = AnalyzerEngine()
    return _analyzer


def _get_anonymizer() -> AnonymizerEngine:
    """Get or create the Presidio anonymizer engine."""
    global _anonymizer
    if _anonymizer is None:
        _anonymizer = AnonymizerEngine()
    return _anonymizer


# Financial and PII entity types to detect
FINANCIAL_ENTITIES = [
    "CREDIT_CARD",
    "IBAN_CODE",
    "US_BANK_NUMBER",
    "US_SSN",
    "US_ITIN",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "US_PASSPORT",
    "US_DRIVER_LICENSE",
    "IP_ADDRESS",
    "PERSON",
    "LOCATION",
    "DATE_TIME",
]


def mask_card_number(card_number: str) -> str:
    """Mask a card number, showing only last 4 digits."""
    if not card_number:
        return ""
    # If already just last 4, return as-is with asterisks
    if len(card_number) <= 4:
        return f"****{card_number}"
    # Otherwise mask all but last 4
    return f"****{card_number[-4:]}"


def mask_amount(amount: Decimal | float | str) -> str:
    """Mask an amount for logging, showing only decimal places."""
    if isinstance(amount, str):
        try:
            amount = Decimal(amount)
        except Exception:
            return "$**.XX"
    return f"$**.{int(amount * 100) % 100:02d}"


def hash_user_id(user_id: str) -> str:
    """Hash a user ID for audit logging."""
    return hashlib.sha256(user_id.encode()).hexdigest()[:12]


def _mask_pii_regex(text: str) -> str:
    """Apply rule-based regex masking for common PII patterns.

    Masks:
    - Credit card numbers (16 digits with optional spaces/dashes)
    - SSN patterns (XXX-XX-XXXX)
    - Email addresses
    - Phone numbers
    - Bank account numbers (9-17 digits)
    - Routing numbers (9 digits)
    """
    # Credit card patterns (16 digits, optionally grouped)
    text = re.sub(
        r'\b(?:\d{4}[-\s]?){3}\d{4}\b',
        '[REDACTED_CREDIT_CARD]',
        text
    )

    # SSN pattern
    text = re.sub(
        r'\b\d{3}-\d{2}-\d{4}\b',
        '[REDACTED_SSN]',
        text
    )

    # Email addresses
    text = re.sub(
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        '[REDACTED_EMAIL]',
        text
    )

    # Phone numbers (various formats)
    text = re.sub(
        r'\b(?:\+1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b',
        '[REDACTED_PHONE]',
        text
    )

    # Bank routing numbers (9 digits, typically starting with 0-3)
    text = re.sub(
        r'\b[0-3]\d{8}\b',
        '[REDACTED_ROUTING]',
        text
    )

    # Bank account numbers (9-17 digits - common range)
    text = re.sub(
        r'\b\d{9,17}\b',
        '[REDACTED_ACCOUNT]',
        text
    )

    return text


def _mask_pii_presidio(text: str) -> str:
    """Apply Microsoft Presidio-based PII detection and anonymization.

    Uses NLP-based detection for financial and personal information.
    """
    analyzer = _get_analyzer()
    anonymizer = _get_anonymizer()

    # Analyze text for PII entities
    results: list[RecognizerResult] = analyzer.analyze(
        text=text,
        entities=FINANCIAL_ENTITIES,
        language="en",
    )

    if not results:
        return text

    # Define custom operators for each entity type
    operators = {
        "CREDIT_CARD": OperatorConfig("replace", {"new_value": "[REDACTED_CREDIT_CARD]"}),
        "IBAN_CODE": OperatorConfig("replace", {"new_value": "[REDACTED_IBAN]"}),
        "US_BANK_NUMBER": OperatorConfig("replace", {"new_value": "[REDACTED_BANK_ACCOUNT]"}),
        "US_SSN": OperatorConfig("replace", {"new_value": "[REDACTED_SSN]"}),
        "US_ITIN": OperatorConfig("replace", {"new_value": "[REDACTED_ITIN]"}),
        "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "[REDACTED_EMAIL]"}),
        "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "[REDACTED_PHONE]"}),
        "US_PASSPORT": OperatorConfig("replace", {"new_value": "[REDACTED_PASSPORT]"}),
        "US_DRIVER_LICENSE": OperatorConfig("replace", {"new_value": "[REDACTED_LICENSE]"}),
        "IP_ADDRESS": OperatorConfig("replace", {"new_value": "[REDACTED_IP]"}),
        "PERSON": OperatorConfig("replace", {"new_value": "[REDACTED_PERSON]"}),
        "LOCATION": OperatorConfig("replace", {"new_value": "[REDACTED_LOCATION]"}),
        "DATE_TIME": OperatorConfig("replace", {"new_value": "[REDACTED_DATETIME]"}),
        "DEFAULT": OperatorConfig("replace", {"new_value": "[REDACTED]"}),
    }

    # Anonymize the detected entities
    anonymized = anonymizer.anonymize(
        text=text,
        analyzer_results=results,
        operators=operators,
    )

    return anonymized.text


def mask_pii(text: str, use_presidio: bool = True) -> str:
    """Mask PII patterns in text using a hybrid approach.

    First applies rule-based regex masking, then optionally uses
    Microsoft Presidio for NLP-based detection of additional PII.

    Args:
        text: The text to redact PII from.
        use_presidio: Whether to apply Presidio detection after regex.
            Defaults to True. Set to False for faster processing when
            only basic regex patterns are needed.

    Returns:
        Text with PII redacted.
    """
    if not text:
        return text

    # Step 1: Apply rule-based regex masking
    masked_text = _mask_pii_regex(text)

    # Step 2: Apply Presidio-based detection for additional coverage
    if use_presidio:
        masked_text = _mask_pii_presidio(masked_text)

    return masked_text


def detect_all_pii(content: str) -> list[dict[str, str | int]]:
    """Detect all PII and return positions for LangChain's PIIMiddleware.

    Uses the same hybrid regex + Presidio approach as mask_pii, but returns
    position data instead of redacted text.

    Args:
        content: Text to analyze for PII

    Returns:
        List of dicts with 'type', 'text', 'start', 'end' keys
    """
    if not content:
        return []

    matches = []
    matched_ranges = set()

    # Step 1: Regex-based detection (same patterns as _mask_pii_regex)
    regex_patterns = [
        (r'\b(?:\d{4}[-\s]?){3}\d{4}\b', 'credit_card'),
        (r'\b\d{3}-\d{2}-\d{4}\b', 'ssn'),
        (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', 'email'),
        (r'\b(?:\+1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b', 'phone'),
        (r'\b[0-3]\d{8}\b', 'routing_number'),
        (r'\b\d{9,17}\b', 'bank_account'),
    ]

    for pattern, pii_type in regex_patterns:
        for match in re.finditer(pattern, content):
            range_key = (match.start(), match.end())
            if range_key not in matched_ranges:
                matches.append({
                    "type": pii_type,
                    "text": match.group(0),
                    "start": match.start(),
                    "end": match.end(),
                })
                matched_ranges.add(range_key)

    # Step 2: Presidio-based detection (same as _mask_pii_presidio)
    analyzer = _get_analyzer()
    results: list[RecognizerResult] = analyzer.analyze(
        text=content,
        entities=FINANCIAL_ENTITIES,
        language="en",
    )

    for result in results:
        range_key = (result.start, result.end)
        if range_key not in matched_ranges:
            matches.append({
                "type": result.entity_type.lower(),
                "text": content[result.start:result.end],
                "start": result.start,
                "end": result.end,
            })
            matched_ranges.add(range_key)

    return matches


def redact_for_logging(data: dict) -> dict:
    """Redact sensitive fields from a dictionary for logging."""
    sensitive_fields = {
        "card_number", "card_last4", "ssn", "email", "phone",
        "password", "api_key", "token", "secret"
    }

    redacted = {}
    for key, value in data.items():
        if key.lower() in sensitive_fields:
            if key.lower() == "card_last4":
                redacted[key] = f"****{value}" if value else "[REDACTED]"
            else:
                redacted[key] = "[REDACTED]"
        elif isinstance(value, dict):
            redacted[key] = redact_for_logging(value)
        elif isinstance(value, list):
            redacted[key] = [
                redact_for_logging(v) if isinstance(v, dict) else v
                for v in value
            ]
        else:
            redacted[key] = value

    return redacted
