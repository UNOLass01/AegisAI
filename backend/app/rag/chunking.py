"""Deterministic markdown chunker for the AegisAI knowledge base.

Splits documents on headings, then packs paragraphs into size-capped chunks
with overlap for long paragraphs. Every chunk carries source attribution
(filename, title, incident id) for evidence grounding.
"""
import re

INCIDENT_RE = re.compile(r"incident\s*#?\s*(\d+)", re.IGNORECASE)
HEADING_RE = re.compile(r"^#{1,6}\s+(.*)")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def parse_incident_id(text: str) -> str | None:
    match = INCIDENT_RE.search(text)
    return match.group(1) if match else None


def parse_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        match = HEADING_RE.match(line.strip())
        if match:
            return match.group(1).strip()
    return fallback


def _hard_split(paragraph: str, max_chars: int, overlap: int) -> list[str]:
    if len(paragraph) <= max_chars:
        return [paragraph]
    sentences = SENTENCE_RE.split(paragraph)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        # A single pathological sentence still gets char-split with overlap.
        while len(sentence) > max_chars:
            chunks.append(sentence[:max_chars])
            sentence = sentence[max_chars - overlap :]
        current = sentence
    if current:
        chunks.append(current)
    return chunks


def chunk_markdown(
    text: str, source: str, max_chars: int = 600, overlap: int = 100
) -> list[dict]:
    """Split markdown into attributed chunks.

    Returns dicts with keys: text, source, title, incident_id, seq.
    """
    text = text.strip()
    if not text:
        return []
    title = parse_title(text, fallback=source)
    incident_id = parse_incident_id(text)

    # Keep each heading attached to its section.
    sections: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if HEADING_RE.match(line.strip()) and current:
            sections.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append("\n".join(current).strip())

    chunks: list[dict] = []

    def emit(piece: str) -> None:
        piece = piece.strip()
        if piece:
            chunks.append(
                {
                    "text": piece,
                    "source": source,
                    "title": title,
                    "incident_id": incident_id,
                    "seq": len(chunks),
                }
            )

    for section in sections:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", section) if p.strip()]
        pending = ""
        for paragraph in paragraphs:
            for piece in _hard_split(paragraph, max_chars, overlap):
                candidate = f"{pending}\n\n{piece}".strip() if pending else piece
                if len(candidate) <= max_chars:
                    pending = candidate
                else:
                    emit(pending)
                    pending = piece
        emit(pending)
    return chunks
