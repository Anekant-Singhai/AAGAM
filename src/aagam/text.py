"""Cleaning page text before it is read for structure."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

EDGE_LINES = 3


def _shape(line: str) -> str:
    return re.sub(r"\d+", "#", " ".join(line.split()).lower())


def strip_running_lines(pages: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Drop headers and footers that repeat at the top or bottom of most pages ("Notice 3", "4 H.G. Infra ...")."""
    if len(pages) < 3:
        return pages
    counts: Counter[str] = Counter()
    for _, text in pages:
        lines = [line for line in text.split("\n") if line.strip()]
        edges = {_shape(line) for line in lines[:EDGE_LINES] + lines[-EDGE_LINES:]}
        counts.update(edges)
    running = {shape for shape, n in counts.items() if n >= max(3, len(pages) * 0.4) and len(shape) <= 80}
    if not running:
        return pages
    cleaned = []
    for page_no, text in pages:
        lines = text.split("\n")
        kept_idx = [i for i, line in enumerate(lines) if line.strip()]
        edge = set(kept_idx[:EDGE_LINES] + kept_idx[-EDGE_LINES:])
        cleaned.append((page_no, "\n".join(line for i, line in enumerate(lines) if not (i in edge and _shape(line) in running))))
    return cleaned


@dataclass(frozen=True)
class Joined:
    """Pages joined into one text, with a way back from a position to its page."""

    text: str
    starts: list[tuple[int, int]]  # (offset, page_no)

    def page_at(self, offset: int) -> int:
        page = self.starts[0][1] if self.starts else 1
        for start, page_no in self.starts:
            if start > offset:
                break
            page = page_no
        return page


def join_pages(pages: list[tuple[int, str]]) -> Joined:
    parts, starts, offset = [], [], 0
    for page_no, text in pages:
        starts.append((offset, page_no))
        parts.append(text)
        offset += len(text) + 1
    return Joined("\n".join(parts), starts)


def reflow(text: str) -> str:
    """Join the line breaks a PDF puts inside sentences; keep paragraph breaks."""
    text = text.replace("­", "").replace("￾", "")
    lines = [" ".join(line.split()) for line in text.split("\n")]
    out: list[str] = []
    for line in lines:
        if not line:
            if out and out[-1] != "":
                out.append("")
            continue
        starts_paragraph = bool(re.match(r"(RESOLVED|\(?[a-z]\)|\(?[ivx]+\)|\d+\.\s|[•\-–]\s)", line))
        if out and out[-1] and not starts_paragraph and not re.search(r"[.:;]['\"”]?$", out[-1]):
            out[-1] = f"{out[-1]} {line}"
        else:
            if out and out[-1] and starts_paragraph:
                out.append("")
            out.append(line)
    return "\n".join(out).strip().replace("\n\n\n", "\n\n")
