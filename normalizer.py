"""AIFT normalizer: timestamp normalization, content sanitization, model extraction."""

import re
from datetime import datetime, timezone, timedelta
from typing import Optional

from config import CREDENTIAL_PATTERNS, MODEL_PATTERNS, CONTENT_PREVIEW_MAX

# Epoch offsets
CHROME_EPOCH_OFFSET = 11644473600  # seconds between 1601-01-01 and 1970-01-01
COCOA_EPOCH_OFFSET = 978307200     # seconds between 2001-01-01 and 1970-01-01


def normalize_timestamp(value) -> Optional[str]:
    """
    Normalize various timestamp formats to UTC ISO-8601 string.

    Handles:
    - ISO-8601 strings
    - Unix epoch seconds (10 digits)
    - Unix epoch milliseconds (13 digits)
    - Chrome/WebKit timestamps (microseconds since 1601-01-01)
    - Cocoa timestamps (seconds since 2001-01-01)
    - datetime objects
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()

    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        # Already ISO-8601
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except (ValueError, AttributeError):
            pass
        # Try parsing as number
        try:
            value = float(value)
        except (ValueError, TypeError):
            return None

    if isinstance(value, (int, float)):
        try:
            v = float(value)
            if v < 0:
                return None

            # Chrome/WebKit: microseconds since 1601-01-01 (very large numbers, 17 digits)
            if v > 1e16:
                epoch_seconds = (v / 1_000_000) - CHROME_EPOCH_OFFSET
                dt = datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)
                return dt.isoformat()

            # Epoch milliseconds (13 digits, ~1.7e12 for current dates)
            if v > 1e12:
                dt = datetime.fromtimestamp(v / 1000, tz=timezone.utc)
                return dt.isoformat()

            # Epoch seconds (10 digits, ~1.7e9 for current dates)
            if v > 1e9:
                dt = datetime.fromtimestamp(v, tz=timezone.utc)
                return dt.isoformat()

            # Cocoa epoch (seconds since 2001-01-01, ~7.8e8 for current dates)
            if v > 1e8:
                epoch_seconds = v + COCOA_EPOCH_OFFSET
                dt = datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)
                return dt.isoformat()

            return None
        except (OSError, OverflowError, ValueError):
            return None

    return None


def sanitize_content(text: str) -> str:
    """Redact credential patterns from text content."""
    if not text:
        return text
    result = text
    for pattern in CREDENTIAL_PATTERNS:
        result = pattern.sub("[REDACTED]", result)
    return result


def content_preview(text: str, max_len: int = CONTENT_PREVIEW_MAX) -> str:
    """Truncate text to preview length with sanitization."""
    if not text:
        return ""
    sanitized = sanitize_content(text)
    if len(sanitized) <= max_len:
        return sanitized
    return sanitized[:max_len - 3] + "..."


def estimate_model_from_content(text: str) -> Optional[str]:
    """Extract AI model name from text content using regex patterns."""
    if not text:
        return None
    for pattern in MODEL_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None
