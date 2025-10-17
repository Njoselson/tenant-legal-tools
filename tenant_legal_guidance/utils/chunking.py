import re
from typing import Dict, List, Optional


def naive_token_estimate(text: str) -> int:
    """Rough token estimator (~4 chars per token)."""
    if not text:
        return 0
    return max(1, int(len(text) / 4))


def split_headings(text: str) -> List[Dict[str, Optional[str]]]:
    """Split text into sections by common heading patterns, returning list of {title, body}."""
    if not text:
        return []
    # Headings: lines in ALL CAPS or numbered sections
    pattern = re.compile(r"^(?P<h>\s*(?:[A-Z][A-Z\s\-]{3,}|\d+\.[\d\.]*\s+.+))$", re.M)
    parts: List[Dict[str, Optional[str]]] = []
    last = 0
    current_title: Optional[str] = None
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


def make_super_chunks(text: str, target_chars: int) -> List[Dict[str, Optional[str]]]:
    """Aggregate heading sections into ~target-sized super-chunks."""
    sections = split_headings(text)
    supers: List[Dict[str, Optional[str]]] = []
    cur_title: Optional[str] = None
    cur_body: List[str] = []
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


def recursive_char_chunks(text: str, target_chars: int, overlap_chars: int) -> List[str]:
    """Split text into overlapping chunks by paragraphs, approximately target size.
    Uses paragraphs and sentences to avoid breaking mid-idea.
    """
    text = text or ""
    if not text:
        return []
    paras = re.split(r"\n\s*\n+", text)
    chunks: List[str] = []
    cur: List[str] = []
    cur_len = 0
    for p in paras:
        p = p.strip()
        if not p:
            continue
        if cur_len and (cur_len + len(p)) > target_chars:
            chunks.append("\n\n".join(cur))
            if overlap_chars > 0 and chunks[-1]:
                tail = chunks[-1][-overlap_chars:]
                cur = [tail]
                cur_len = len(tail)
            else:
                cur = []
                cur_len = 0
        cur.append(p)
        cur_len += len(p)
    if cur:
        chunks.append("\n\n".join(cur))
    return chunks


def build_chunk_docs(text: str, source: str, title: Optional[str], target_chars: int, overlap_chars: int) -> List[Dict[str, object]]:
    """Create chunk dicts for persistence to Arango/Qdrant."""
    result: List[Dict[str, object]] = []
    supers = make_super_chunks(text, target_chars * 3)  # ~3x chunk target for super
    super_ids: List[str] = []
    for si, sec in enumerate(supers):
        sec_title = sec.get("title") or title
        body = sec.get("body") or ""
        atomic = recursive_char_chunks(body, target_chars, overlap_chars)
        for i, ch in enumerate(atomic):
            result.append({
                "chunk_index": len(result),
                "text": ch,
                "token_count": naive_token_estimate(ch),
                "title": sec_title,
                "section": f"{si}",
            })
    return result


