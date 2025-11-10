import re


def naive_token_estimate(text: str) -> int:
    """Rough token estimator (~4 chars per token)."""
    if not text:
        return 0
    return max(1, int(len(text) / 4))


def split_headings(text: str) -> list[dict[str, str | None]]:
    """Split text into sections by common heading patterns, returning list of {title, body}."""
    if not text:
        return []
    # Headings: lines in ALL CAPS or numbered sections
    pattern = re.compile(r"^(?P<h>\s*(?:[A-Z][A-Z\s\-]{3,}|\d+\.[\d\.]*\s+.+))$", re.M)
    parts: list[dict[str, str | None]] = []
    last = 0
    current_title: str | None = None
    for m in pattern.finditer(text):
        start = m.start()
        if start > last:
            body = text[last:start].strip("\n")
            if body:
                parts.append({"title": current_title, "body": body})
        current_title = m.group("h").strip()
        last = m.end()
    # Tail
    tail = text[last:].strip("\n")
    if tail:
        parts.append({"title": current_title, "body": tail})
    # If we found no headings, return as single body
    if not parts:
        return [{"title": None, "body": text}]
    return parts


def make_super_chunks(text: str, target_chars: int) -> list[dict[str, str | None]]:
    """Aggregate heading sections into ~target-sized super-chunks."""
    sections = split_headings(text)
    supers: list[dict[str, str | None]] = []
    cur_title: str | None = None
    cur_body: list[str] = []
    cur_len = 0
    for sec in sections:
        title = sec.get("title")
        body = sec.get("body") or ""
        blen = len(body)
        if cur_len and (cur_len + blen) > target_chars:
            supers.append({"title": cur_title, "body": "\n\n".join(cur_body)})
            cur_title = title
            cur_body = [body]
            cur_len = blen
        else:
            if cur_title is None:
                cur_title = title
            cur_body.append(body)
            cur_len += blen
    if cur_body:
        supers.append({"title": cur_title, "body": "\n\n".join(cur_body)})
    return supers


def recursive_char_chunks(text: str, target_chars: int, overlap_chars: int) -> list[str]:
    """Simple recursive character splitter with overlap.

    Tries to split at natural boundaries (sentences) but always ensures
    chunks don't exceed target_chars.
    """
    text = text or ""
    if not text:
        return []

    # If text is smaller than target, return as-is
    if len(text) <= target_chars:
        return [text]

    chunks: list[str] = []
    start = 0

    while start < len(text):
        # Calculate end position
        end = start + target_chars

        # If we're not at the end of the text, try to break at a sentence
        if end < len(text):
            # Look for sentence boundary in the last 20% of the chunk
            search_start = int(end - target_chars * 0.2)
            chunk_segment = text[search_start:end]

            # Find last sentence boundary
            last_period = max(
                chunk_segment.rfind(". "),
                chunk_segment.rfind("! "),
                chunk_segment.rfind("? "),
                chunk_segment.rfind("\n"),
            )

            if last_period != -1:
                # Adjust end to sentence boundary
                end = search_start + last_period + 2  # +2 to include ". "

        # Extract chunk
        chunks.append(text[start:end].strip())

        # Move start position with overlap
        start = end - overlap_chars if overlap_chars > 0 else end

    return chunks


def build_chunk_docs(
    text: str, source: str, title: str | None, target_chars: int, overlap_chars: int
) -> list[dict[str, object]]:
    """Create chunk dicts for persistence to Arango/Qdrant."""
    result: list[dict[str, object]] = []
    supers = make_super_chunks(text, target_chars * 3)  # ~3x chunk target for super
    super_ids: list[str] = []
    for si, sec in enumerate(supers):
        sec_title = sec.get("title") or title
        body = sec.get("body") or ""
        atomic = recursive_char_chunks(body, target_chars, overlap_chars)
        for i, ch in enumerate(atomic):
            result.append(
                {
                    "chunk_index": len(result),
                    "text": ch,
                    "token_count": naive_token_estimate(ch),
                    "title": sec_title,
                    "section": f"{si}",
                }
            )
    return result
