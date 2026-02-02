"""Structured audit logging with PII redaction."""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from src.utils.pii import mask_pii, hash_user_id, redact_for_logging


def get_logger(name: str, level: str = "INFO") -> logging.Logger:
    """Get a configured logger instance."""
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    logger.setLevel(getattr(logging, level.upper()))
    return logger


class AuditLogger:
    """Audit logger for tracking LLM interactions with PII protection."""

    def __init__(self, log_dir: Path | None = None, user_id: str | None = None):
        self.log_dir = log_dir or Path("logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.user_id = user_id
        self.user_hash = hash_user_id(user_id) if user_id else "anonymous"
        self._logger = get_logger(f"audit.{self.user_hash}")

    def _get_log_file(self) -> Path:
        """Get the current audit log file path."""
        date_str = datetime.now().strftime("%Y-%m-%d")
        return self.log_dir / f"audit_{date_str}.jsonl"

    def _write_entry(self, entry: dict):
        """Write an audit entry to the log file."""
        entry["timestamp"] = datetime.now().isoformat()
        entry["user_hash"] = self.user_hash

        with open(self._get_log_file(), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def log_user_input(self, message: str, metadata: dict | None = None):
        """Log a user input with PII redaction."""
        entry = {
            "event": "user_input",
            "message": mask_pii(message),
            "metadata": redact_for_logging(metadata) if metadata else None,
        }
        self._write_entry(entry)
        self._logger.info(f"User input received (length: {len(message)})")

    def log_llm_request(self, prompt: str, model: str, metadata: dict | None = None):
        """Log an LLM request."""
        entry = {
            "event": "llm_request",
            "model": model,
            "prompt_length": len(prompt),
            "prompt_preview": mask_pii(prompt[:200]) + "..." if len(prompt) > 200 else mask_pii(prompt),
            "metadata": redact_for_logging(metadata) if metadata else None,
        }
        self._write_entry(entry)
        self._logger.debug(f"LLM request to {model}")

    def log_llm_response(
        self,
        response: str,
        model: str,
        tokens_used: int | None = None,
        metadata: dict | None = None,
    ):
        """Log an LLM response."""
        entry = {
            "event": "llm_response",
            "model": model,
            "response_length": len(response),
            "response_preview": mask_pii(response[:200]) + "..." if len(response) > 200 else mask_pii(response),
            "tokens_used": tokens_used,
            "metadata": redact_for_logging(metadata) if metadata else None,
        }
        self._write_entry(entry)
        self._logger.debug(f"LLM response from {model} (tokens: {tokens_used})")

    def log_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: Any = None,
        error: str | None = None,
    ):
        """Log a tool call."""
        entry = {
            "event": "tool_call",
            "tool": tool_name,
            "arguments": redact_for_logging(arguments),
            "result_type": type(result).__name__ if result is not None else None,
            "error": error,
        }
        self._write_entry(entry)
        if error:
            self._logger.warning(f"Tool {tool_name} failed: {error}")
        else:
            self._logger.debug(f"Tool {tool_name} called successfully")

    def log_dispute_flagged(
        self,
        transaction_id: str,
        dispute_id: str,
        reason: str,
    ):
        """Log when a dispute is flagged for review."""
        entry = {
            "event": "dispute_flagged",
            "transaction_id": transaction_id,
            "dispute_id": dispute_id,
            "reason": mask_pii(reason),
        }
        self._write_entry(entry)
        self._logger.info(f"Dispute flagged: {dispute_id} for transaction {transaction_id}")

    def log_security_event(
        self,
        event_type: str,
        details: str,
        severity: str = "warning",
    ):
        """Log a security-related event."""
        entry = {
            "event": "security",
            "event_type": event_type,
            "details": mask_pii(details),
            "severity": severity,
        }
        self._write_entry(entry)
        log_method = getattr(self._logger, severity.lower(), self._logger.warning)
        log_method(f"Security event: {event_type}")
