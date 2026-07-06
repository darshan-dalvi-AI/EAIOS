"""Sentence-aware chunking with overlap. Sections/pages are preserved as metadata
so citations can point back to the exact location."""
import re

SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def chunk_blocks(blocks: list[dict], target_chars: int = 900, overlap_chars: int = 150) -> list[dict]:
    chunks: list[dict] = []
    for block in blocks:
        for piece in _split_text(block["text"], target_chars, overlap_chars):
            chunks.append({"section": block.get("section", ""), "page": block.get("page", 0), "text": piece})
    return chunks


def _split_text(text: str, target: int, overlap: int) -> list[str]:
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) <= target:
        return [text] if text else []

    sentences = SENTENCE_END.split(text)
    pieces: list[str] = []
    current = ""
    for sentence in sentences:
        if len(current) + len(sentence) + 1 > target and current:
            pieces.append(current.strip())
            current = current[-overlap:] if overlap else ""  # sliding-window overlap
        current = f"{current} {sentence}".strip()
    if current.strip():
        pieces.append(current.strip())
    return pieces
