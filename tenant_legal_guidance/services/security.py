"""
Input validation and sanitization service.

Provides three-layer security: Pydantic validation, FastAPI validation, and custom sanitization.
"""

from __future__ import annotations

import html
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# SQL injection patterns
SQL_INJECTION_PATTERNS = [
    r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|EXECUTE)\b)",
    r"(\b(UNION|OR|AND)\s+\d+\s*=\s*\d+)",
    r"(--|#|/\*|\*/)",
    r"(\b(script|javascript|onerror|onload)\s*=)",
]

# Command injection patterns
COMMAND_INJECTION_PATTERNS = [
    r"[;&|`$(){}[\]<>]",
    r"(\b(cat|ls|pwd|whoami|id|uname)\s+)",
    r"(\$(?:[a-zA-Z_][a-zA-Z0-9_]*|\{[^}]+\}))",
]


def sanitize_html(text: str) -> str:
    """Sanitize HTML content to prevent XSS attacks."""
    if not isinstance(text, str):
        return text
    # Escape HTML entities
    return html.escape(text, quote=True)


def detect_sql_injection(text: str) -> bool:
    """Detect potential SQL injection patterns."""
    if not isinstance(text, str):
        return False
    text_upper = text.upper()
    for pattern in SQL_INJECTION_PATTERNS:
        if re.search(pattern, text_upper, re.IGNORECASE):
            logger.warning(f"Potential SQL injection detected: {pattern}")
            return True
    return False


def detect_command_injection(text: str) -> bool:
    """Detect potential command injection patterns."""
    if not isinstance(text, str):
        return False
    for pattern in COMMAND_INJECTION_PATTERNS:
        if re.search(pattern, text):
            logger.warning(f"Potential command injection detected: {pattern}")
            return True
    return False


def sanitize_input(value: Any) -> Any:
    """Sanitize input value based on type."""
    if isinstance(value, str):
        # Check for injection patterns
        if detect_sql_injection(value):
            raise ValueError("Invalid input detected")
        if detect_command_injection(value):
            raise ValueError("Invalid input detected")
        # Sanitize HTML
        return sanitize_html(value)
    elif isinstance(value, dict):
        return {k: sanitize_input(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [sanitize_input(item) for item in value]
    return value


def validate_request_size(content_length: int | None, max_size_mb: int) -> None:
    """Validate request body size."""
    if content_length is None:
        return
    max_size_bytes = max_size_mb * 1024 * 1024
    if content_length > max_size_bytes:
        raise ValueError(f"Request body too large. Maximum size: {max_size_mb}MB")


# LLM Prompt Injection Patterns
PROMPT_INJECTION_PATTERNS = [
    r"(?i)\bignore\s+(all\s+)?previous\s+instructions\b",
    r"(?i)\bignore\s+(the\s+)?(above|prior|earlier)\s+(instructions|prompt|text)\b",
    r"(?i)\boverride\s+(the\s+)?(previous|system|original)\s+(instructions|prompt)\b",
    r"(?i)\bforget\s+(the\s+)?(previous|prior|above)\s+(instructions|prompt)\b",
    r"(?i)\bdisregard\s+(the\s+)?(previous|prior|above)\s+(instructions|prompt)\b",
    r"(?i)\bnow\s+(you\s+)?are\s+(a|an)\s+",
    r"(?i)\bact\s+as\s+(if\s+)?(you\s+)?are\s+",
    r"(?i)\bpretend\s+(you\s+)?are\s+",
    r"(?i)\byou\s+are\s+now\s+",
    r"(?i)\bsystem\s*:\s*",
    r"(?i)\bdeveloper\s+mode\b",
    r"(?i)\bjailbreak\b",
    r"(?i)\bbypass\s+(all\s+)?(safety|security|restrictions?)\b",
    r"(?i)\bwhat\s+(are\s+)?(your\s+)?(original|system|initial)\s+(instructions|prompt)\b",
    r"(?i)\brepeat\s+(your\s+)?(original|system|initial)\s+(instructions|prompt)\s+verbatim\b",
    r"(?i)\bshow\s+(me\s+)?(your\s+)?(original|system|initial)\s+(instructions|prompt)\b",
]


def detect_prompt_injection(text: str) -> bool:
    """Detect potential prompt injection patterns in text."""
    if not isinstance(text, str):
        return False
    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, text):
            logger.warning(f"Potential prompt injection detected: {pattern}")
            return True
    return False


def sanitize_for_llm(text: str, remove_injections: bool = True) -> str:
    """Sanitize text specifically for LLM prompts.

    This function:
    1. Removes or neutralizes prompt injection patterns
    2. Truncates extremely long inputs
    3. Normalizes whitespace

    Args:
        text: Input text to sanitize
        remove_injections: If True, remove detected injection patterns

    Returns:
        Sanitized text safe for LLM prompts
    """
    if not isinstance(text, str):
        return text

    # Truncate extremely long inputs (prevent resource exhaustion)
    max_length = 50000  # Reasonable limit for case descriptions
    if len(text) > max_length:
        logger.warning(f"Input truncated from {len(text)} to {max_length} characters")
        text = text[:max_length] + "... [truncated]"

    # Remove or neutralize prompt injection patterns
    if remove_injections:
        for pattern in PROMPT_INJECTION_PATTERNS:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)

    # Normalize whitespace (prevent hidden characters)
    text = " ".join(text.split())

    return text.strip()


def wrap_user_input(text: str, tag: str = "USER_INPUT") -> str:
    """Wrap user input in XML-style tags for clear prompt boundaries.

    This helps LLMs distinguish between system instructions and user content.

    Args:
        text: User input text
        tag: XML tag name (default: "USER_INPUT")

    Returns:
        Text wrapped in XML tags
    """
    sanitized = sanitize_for_llm(text)
    return f"<{tag}>\n{sanitized}\n</{tag}>"


def create_safe_prompt(
    system_instructions: str,
    user_input: str,
    output_format: str | None = None,
    additional_context: str | None = None,
) -> str:
    """Create a safe prompt with clear boundaries between system and user content.

    Args:
        system_instructions: System-level instructions for the LLM
        user_input: User-provided content (will be sanitized and wrapped)
        output_format: Optional format specification for LLM output
        additional_context: Optional additional context (e.g., retrieved documents)

    Returns:
        Safe prompt string with clear boundaries
    """
    # Sanitize and wrap user input
    safe_user_input = wrap_user_input(user_input)

    # Build prompt with clear sections
    prompt_parts = [
        "<SYSTEM_INSTRUCTIONS>",
        system_instructions,
        "</SYSTEM_INSTRUCTIONS>",
    ]

    if additional_context:
        prompt_parts.extend(
            [
                "\n<ADDITIONAL_CONTEXT>",
                additional_context,
                "</ADDITIONAL_CONTEXT>",
            ]
        )

    prompt_parts.extend(
        [
            "\n<USER_INPUT>",
            safe_user_input,
            "</USER_INPUT>",
        ]
    )

    if output_format:
        prompt_parts.extend(
            [
                "\n<OUTPUT_FORMAT>",
                output_format,
                "</OUTPUT_FORMAT>",
            ]
        )

    return "\n".join(prompt_parts)


def validate_llm_output(response: str) -> str:
    """Validate and sanitize LLM output before returning to users.

    Args:
        response: LLM response text

    Returns:
        Validated and sanitized response

    Raises:
        ValueError: If response contains suspicious patterns
    """
    if not isinstance(response, str):
        return response

    # Check for suspicious patterns that might indicate prompt injection success
    suspicious_patterns = [
        r"(?i)\bignore\s+(all\s+)?previous\s+instructions\b",
        r"(?i)\bsystem\s+prompt\s*:",
        r"(?i)\bdeveloper\s+mode\b",
        r"(?i)\bjailbreak\b",
    ]

    for pattern in suspicious_patterns:
        if re.search(pattern, response):
            logger.error(f"Suspicious LLM output detected: {pattern}")
            raise ValueError("Invalid response detected. Please try again.")

    # Sanitize HTML to prevent XSS if response is rendered
    sanitized = sanitize_html(response)

    return sanitized
