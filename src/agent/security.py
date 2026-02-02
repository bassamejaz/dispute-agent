"""Input sanitization and security utilities."""

import re
from typing import NamedTuple

from src.utils.logging import AuditLogger


class SanitizationResult(NamedTuple):
    """Result of input sanitization."""
    text: str
    was_modified: bool
    warnings: list[str]


# Patterns that might indicate prompt injection attempts
SUSPICIOUS_PATTERNS = [
    # Direct instruction overrides
    (r'ignore\s+(all\s+)?(previous|above|prior)\s+(instructions?|prompts?)', "instruction_override"),
    (r'disregard\s+(all\s+)?(previous|above|prior)', "instruction_override"),
    (r'forget\s+(everything|all)', "instruction_override"),

    # System prompt extraction attempts
    (r'(show|print|display|reveal|output)\s+(me\s+)?(your\s+)?(system\s+)?prompt', "prompt_extraction"),
    (r'what\s+(are|is)\s+your\s+(instructions?|prompt)', "prompt_extraction"),
    (r'repeat\s+(your\s+)?(initial\s+)?(instructions?|prompt)', "prompt_extraction"),

    # Role manipulation
    (r'you\s+are\s+now\s+a', "role_manipulation"),
    (r'pretend\s+(to\s+be|you\'re)', "role_manipulation"),
    (r'act\s+as\s+(if|a)', "role_manipulation"),
    (r'roleplay\s+as', "role_manipulation"),

    # Delimiter injection
    (r'```\s*(system|assistant|user)\s*\n', "delimiter_injection"),
    (r'<\|?(system|assistant|user)\|?>', "delimiter_injection"),

    # Escape attempts
    (r'\\n\\n.*system:', "escape_attempt"),
]

# Characters to escape or remove
DANGEROUS_CHARS = {
    '\x00': '',  # Null byte
    '\x1b': '',  # Escape character
}


def sanitize_input(
    text: str,
    user_id: str | None = None,
    log_warnings: bool = True,
) -> SanitizationResult:
    """Sanitize user input for security.

    Performs:
    1. Remove dangerous characters
    2. Detect and log suspicious patterns
    3. Basic normalization

    Args:
        text: The user input to sanitize
        user_id: Optional user ID for logging
        log_warnings: Whether to log security warnings

    Returns:
        SanitizationResult with sanitized text and warnings
    """
    warnings = []
    was_modified = False
    logger = AuditLogger(user_id=user_id) if log_warnings and user_id else None

    # Remove dangerous characters
    sanitized = text
    for char, replacement in DANGEROUS_CHARS.items():
        if char in sanitized:
            sanitized = sanitized.replace(char, replacement)
            was_modified = True
            warnings.append(f"Removed dangerous character: {repr(char)}")

    # Check for suspicious patterns
    text_lower = text.lower()
    for pattern, category in SUSPICIOUS_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            warnings.append(f"Suspicious pattern detected: {category}")
            if logger:
                logger.log_security_event(
                    event_type=f"suspicious_input_{category}",
                    details=f"Pattern matched in user input",
                    severity="warning",
                )

    # Normalize excessive whitespace (but preserve intentional formatting)
    normalized = re.sub(r' {3,}', '  ', sanitized)
    if normalized != sanitized:
        sanitized = normalized
        was_modified = True

    # Truncate extremely long inputs (prevent context stuffing)
    max_length = 5000
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length] + "... [truncated]"
        was_modified = True
        warnings.append(f"Input truncated from {len(text)} to {max_length} characters")
        if logger:
            logger.log_security_event(
                event_type="input_truncated",
                details=f"Input was {len(text)} chars, truncated to {max_length}",
                severity="info",
            )

    return SanitizationResult(
        text=sanitized,
        was_modified=was_modified,
        warnings=warnings,
    )


def is_on_topic(text: str) -> tuple[bool, str]:
    """Check if the query is related to transactions/disputes.

    Returns:
        Tuple of (is_on_topic, suggested_response)
    """
    text_lower = text.lower()

    # Transaction-related keywords
    transaction_keywords = {
        "charge", "charged", "transaction", "payment", "paid",
        "purchase", "bought", "spent", "cost", "bill", "billed",
        "debit", "credit", "withdraw", "withdrawal",
        "merchant", "store", "shop", "subscription",
        "refund", "dispute", "recognize", "unauthorized",
        "amount", "dollar", "money", "$", "€", "£",
    }

    # Check for transaction-related content
    for keyword in transaction_keywords:
        if keyword in text_lower:
            return True, ""

    # Greeting patterns - allow these
    greeting_patterns = [
        r'^(hi|hello|hey|good\s+(morning|afternoon|evening))[\s,!.]*$',
        r'^how\s+are\s+you',
        r'^thanks?(\s+you)?[\s,!.]*$',
        r'^(bye|goodbye|see\s+you)[\s,!.]*$',
    ]

    for pattern in greeting_patterns:
        if re.match(pattern, text_lower):
            return True, ""

    # Off-topic detection
    off_topic_response = (
        "I'm a transaction dispute resolution assistant. I can help you with:\n"
        "- Finding and understanding charges on your account\n"
        "- Investigating unfamiliar transactions\n"
        "- Filing disputes for unauthorized charges\n\n"
        "How can I help you with your transactions today?"
    )

    return False, off_topic_response


def validate_user_id(user_id: str) -> bool:
    """Validate that a user ID is in expected format."""
    # Simple validation - alphanumeric with underscores
    return bool(re.match(r'^[a-zA-Z0-9_-]+$', user_id))
