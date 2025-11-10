"""
Text processing utilities for the Tenant Legal Guidance System.
"""

import hashlib
import re
import uuid


def canonicalize_text(text: str) -> str:
    """Normalize text by standardizing whitespace and removing extra spaces.
    
    Args:
        text: Input text to canonicalize
        
    Returns:
        Canonicalized text with normalized whitespace
    """
    if not text:
        return ""
    
    # Normalize whitespace: collapse multiple spaces/newlines to single space
    text = re.sub(r'\s+', ' ', text.strip())
    
    return text


def sha256(text: str) -> str:
    """Compute SHA256 hash of text.
    
    Args:
        text: Input text to hash
        
    Returns:
        SHA256 hash as hexadecimal string
    """
    if not text:
        return hashlib.sha256(b"").hexdigest()
    
    # Encode as UTF-8 bytes before hashing
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def generate_uuid_from_text(text: str) -> str:
    """
    Generate deterministic UUID from text content.
    Same content = same UUID (for deduplication).
    
    Args:
        text: Text content to hash
        
    Returns:
        UUID string (e.g., "550e8400-e29b-41d4-a716-446655440000")
    """
    if not text:
        # Use a fixed UUID for empty text
        return "00000000-0000-0000-0000-000000000000"
    
    content_hash = sha256(canonicalize_text(text))
    # Use first 16 bytes of hash as UUID bytes
    uuid_bytes = bytes.fromhex(content_hash[:32])
    return str(uuid.UUID(bytes=uuid_bytes))
