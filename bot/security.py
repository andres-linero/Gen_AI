"""
Security Middleware for SkyTrac Teams Bot
- Input sanitization
- Rate limiting (per-user, in-memory)
- Prompt injection detection
- Audit logging
"""

import re
import time
import hashlib
import logging
import os
from collections import defaultdict
from typing import Optional

logger = logging.getLogger(__name__)

# --- Audit log setup ---
AUDIT_LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "audit_logs")
os.makedirs(AUDIT_LOG_DIR, exist_ok=True)

_audit_logger = logging.getLogger("audit")
_audit_logger.setLevel(logging.INFO)
_audit_handler = logging.FileHandler(os.path.join(AUDIT_LOG_DIR, "bot_audit.log"))
_audit_handler.setFormatter(
    logging.Formatter("%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
)
_audit_logger.addHandler(_audit_handler)

# --- Prompt injection patterns ---
# These catch common LLM manipulation attempts
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"ignore\s+(all\s+)?above\s+instructions",
    r"disregard\s+(all\s+)?previous",
    r"forget\s+(all\s+)?previous",
    r"you\s+are\s+now\s+a",
    r"new\s+system\s+prompt",
    r"override\s+system\s+prompt",
    r"act\s+as\s+(a\s+)?different",
    r"pretend\s+you\s+are",
    r"jailbreak",
    r"DAN\s+mode",
    r"\bsystem\s*:\s*",
    r"\[system\]",
    r"<\s*system\s*>",
]
_compiled_patterns = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]


class RateLimiter:
    """In-memory per-user rate limiter using sliding window."""

    def __init__(self, max_requests: int = 20, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, user_id: str) -> bool:
        now = time.time()
        cutoff = now - self.window_seconds

        # Remove expired timestamps
        self._requests[user_id] = [
            t for t in self._requests[user_id] if t > cutoff
        ]

        if len(self._requests[user_id]) >= self.max_requests:
            return False

        self._requests[user_id].append(now)
        return True


# Module-level rate limiter instance
_rate_limiter = RateLimiter()


def sanitize_input(text: str, max_length: int = 1000) -> str:
    """Strip control characters and enforce length limit."""
    # Remove null bytes and control characters (keep newlines and tabs)
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    # Trim whitespace
    cleaned = cleaned.strip()
    # Enforce length
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length]
    return cleaned


def check_prompt_injection(text: str) -> Optional[str]:
    """Check for known prompt injection patterns.
    Returns the matched pattern description if detected, None if clean.
    """
    for pattern in _compiled_patterns:
        if pattern.search(text):
            return pattern.pattern
    return None


def check_rate_limit(user_id: str) -> bool:
    """Returns True if the request is allowed, False if rate-limited."""
    return _rate_limiter.is_allowed(user_id)


def log_request(
    user_id: str,
    tenant_id: str,
    message_hash: str,
    status: str,
    detail: str = "",
):
    """Write an audit log entry. Logs message hash, not full message, for privacy."""
    entry = f"user={user_id} | tenant={tenant_id} | msg_hash={message_hash} | status={status}"
    if detail:
        entry += f" | detail={detail}"
    _audit_logger.info(entry)


def hash_message(text: str) -> str:
    """SHA-256 hash of message text for audit logging without storing content."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def run_security_checks(
    text: str, user_id: str, tenant_id: str, max_length: int = 1000
) -> tuple[str, Optional[str]]:
    """Run all security checks on incoming message.

    Returns:
        (sanitized_text, rejection_reason)
        If rejection_reason is not None, the message should be rejected.
    """
    msg_hash = hash_message(text)

    # 1. Sanitize
    sanitized = sanitize_input(text, max_length=max_length)

    if not sanitized:
        log_request(user_id, tenant_id, msg_hash, "REJECTED", "empty_message")
        return "", "Your message was empty after processing. Please try again."

    # 2. Rate limit
    if not check_rate_limit(user_id):
        log_request(user_id, tenant_id, msg_hash, "RATE_LIMITED")
        return sanitized, (
            "You're sending messages too quickly. "
            "Please wait a moment and try again."
        )

    # 3. Prompt injection check
    injection_match = check_prompt_injection(sanitized)
    if injection_match:
        log_request(user_id, tenant_id, msg_hash, "BLOCKED", "prompt_injection")
        logger.warning(f"Prompt injection blocked for user {user_id}")
        return sanitized, (
            "Your message was flagged by our security filter. "
            "Please rephrase your work order question."
        )

    # All checks passed
    log_request(user_id, tenant_id, msg_hash, "ALLOWED")
    return sanitized, None
