"""Structure-aware chunking.

Chunks never cross a page or section boundary, so each chunk has one unambiguous
citation. Inside a block we split on paragraphs, then sentences, then words.
"""

import re
from dataclasses import dataclass

from app.rag.parsers import Block

_SENTENCE = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Chunk:
    index: int
    text: str
    page: int | None
    section: str | None


def _split_units(text: str, size: int) -> list[str]:
    """Break text into units no longer than `size`, preferring natural boundaries."""
    units: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if len(para) <= size:
            units.append(para)
            continue
        for sent in _SENTENCE.split(para):
            if len(sent) <= size:
                units.append(sent)
            else:
                words, cur = sent.split(), ""
                for w in words:
                    if len(cur) + len(w) + 1 > size and cur:
                        units.append(cur)
                        cur = ""
                    cur = f"{cur} {w}".strip()
                if cur:
                    units.append(cur)
    return units


def _pack(units: list[str], size: int, overlap: int) -> list[str]:
    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for u in units:
        if cur and cur_len + len(u) + 2 > size:
            chunks.append("\n\n".join(cur))
            # Carry trailing units forward as overlap for context continuity.
            carried, carried_len = [], 0
            for prev in reversed(cur):
                if carried_len + len(prev) > overlap:
                    break
                carried.insert(0, prev)
                carried_len += len(prev) + 2
            cur, cur_len = carried, carried_len
        cur.append(u)
        cur_len += len(u) + 2
    if cur:
        chunks.append("\n\n".join(cur))
    return chunks


def chunk_blocks(blocks: list[Block], size: int = 1000, overlap: int = 150, min_chars: int = 40) -> list[Chunk]:
    out: list[Chunk] = []
    # Merge small consecutive blocks that share page+section so we don't create
    # dozens of tiny low-signal chunks.
    merged: list[Block] = []
    for b in blocks:
        if not b.text.strip():
            continue
        prev = merged[-1] if merged else None
        if (
            prev
            and not prev.atomic
            and not b.atomic
            and prev.page == b.page
            and prev.section == b.section
            and len(prev.text) + len(b.text) < size
        ):
            prev.text = f"{prev.text}\n\n{b.text}"
        else:
            merged.append(Block(b.text, b.page, b.section, b.atomic))

    for b in merged:
        pieces = [b.text] if b.atomic and len(b.text) <= size * 3 else _pack(_split_units(b.text, size), size, overlap)
        for piece in pieces:
            if len(piece.strip()) < min_chars and out and out[-1].page == b.page and out[-1].section == b.section:
                out[-1].text += "\n\n" + piece
                continue
            out.append(Chunk(len(out), piece.strip(), b.page, b.section))
    return out
