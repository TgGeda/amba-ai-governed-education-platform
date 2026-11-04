from __future__ import annotations

import html
import json
from pathlib import Path
import re
from typing import Any, Iterable, Sequence

from amba_ai.models.schemas import Flashcard, MCQ

SCHEMA_VERSION = "ambaai.learning.v3.1"

BAD_PATTERNS = (
    r"key idea in point\s+\d+",
    r"best matches key point\s+\d+",
    r"this point is unrelated",
    r"does not contain educational content",
    r"this statement contradicts",
    r"hello,? online friend",
)


def _val(obj: Any, name: str, default: Any = None) -> Any:
    return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)


def _clean(text: Any) -> str:
    cleaned = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"[🟣👋]+\s*", "", cleaned)
    cleaned = cleaned.replace("\u2013", "-").replace("\u2014", "-")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _key(query: str) -> str:
    return re.sub(r"\W+", " ", str(query or "").lower()).strip()


def _is_weak(text: str) -> bool:
    low = str(text or "").lower()
    return any(re.search(p, low) for p in BAD_PATTERNS)


def source_label(doc: Any, ref: Any = None) -> str:
    meta = dict(_val(doc, "metadata", {}) or {})
    title = None
    for cand in (
        meta.get("original_filename"),
        meta.get("filename"),
        meta.get("original_path"),
        meta.get("source_path"),
        meta.get("stored_path"),
        _val(doc, "source_path"),
        _val(doc, "title"),
    ):
        if cand:
            title = Path(str(cand)).name
            break
    title = title or "Uploaded learning material"
    m = re.search(r"(?:page|p\.?)[\s:#]*(\d+)", str(ref or ""), re.IGNORECASE)
    return f"{title} · Page {m.group(1)}" if m else title


def normalize_card(card: Any, doc: Any) -> Flashcard | None:
    q = _clean(_val(card, "question", _val(card, "front", "")))
    a = _clean(_val(card, "answer", _val(card, "back", "")))
    if not q or not a or _is_weak(q) or _is_weak(a) or len(a) > 600 or len(q) < 5:
        return None

    ref = _val(card, "source_ref", _val(card, "source", None))
    return Flashcard(
        question=q,
        answer=a,
        source_ref=source_label(doc, ref),
    )


def normalize_mcq(mcq: Any, doc: Any) -> MCQ | None:
    q = _clean(_val(mcq, "question", ""))
    choices = [_clean(c) for c in list(_val(mcq, "choices", _val(mcq, "options", [])) or [])]
    answer = _clean(_val(mcq, "correct_answer", _val(mcq, "answer", "")))
    explanation = _clean(_val(mcq, "explanation", _val(mcq, "rationale", "")))

    if not q or _is_weak(q) or len(choices) != 4 or len(set(choices)) != 4 or not explanation:
        return None

    if answer not in choices:
        normalized_answer = answer.lower().strip()
        matched = next((c for c in choices if c.lower().strip() == normalized_answer), None)
        if matched:
            answer = matched
        else:
            return None

    if any(_is_weak(c) or len(c) > 300 for c in choices):
        return None

    lengths = [len(c) for c in choices]
    if max(lengths) > max(50, min(lengths) * 5):
        return None

    ref = _val(mcq, "source_ref", _val(mcq, "source", None))
    return MCQ(
        question=q,
        choices=choices,
        correct_answer=answer,
        explanation=explanation,
        source_ref=source_label(doc, ref),
    )


def fill_missing_flashcards(cards: Sequence[Flashcard], count: int, doc: Any) -> list[Flashcard]:
    out: list[Flashcard] = []
    seen: set[str] = set()

    for c in cards:
        if c and c.question:
            k = _key(c.question)
            if k not in seen:
                out.append(c)
                seen.add(k)
        if len(out) >= count:
            return out[:count]

    raw_text = str(_val(doc, "raw_text", ""))
    if raw_text:
        sentences = [
            s.strip()
            for s in re.split(r"(?<=[.!?])\s+", raw_text)
            if 35 <= len(s.strip()) <= 220 and not _is_weak(s)
        ]
        label = source_label(doc)
        for s in sentences:
            q = f"What key principle does the material establish regarding: {s[:50]}...?"
            if _key(q) not in seen:
                out.append(Flashcard(question=q, answer=s, source_ref=label))
                seen.add(_key(q))
            if len(out) >= count:
                return out[:count]

    while len(out) < count:
        idx = len(out) + 1
        q = f"Key Concept Review {idx}"
        out.append(
            Flashcard(
                question=f"What is the designated learning focus for concept {idx}?",
                answer=f"Refer to the source document for full details regarding section {idx}.",
                source_ref=source_label(doc),
            )
        )

    return out[:count]


def _section(markdown: str, heading: str, level: int | None = None) -> str:
    hashes = rf"#{{{level}}}" if level else r"##+"
    pattern = rf"(?ims)^{hashes}\s+{re.escape(heading)}\s*$\n(.*?)(?=^##+\s+|\Z)"
    match = re.search(pattern, markdown)
    return match.group(1).strip() if match else ""


def _sentences(text: str, limit: int = 3) -> list[str]:
    cleaned = re.sub(r"[`*_#>]", "", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if len(part.strip()) > 24][:limit]


def _bullets(text: str, limit: int = 5) -> list[str]:
    result: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("- ", "* ")):
            item = stripped[2:].strip()
            if item and item not in result:
                result.append(item)
        if len(result) >= limit:
            break
    return result


def build_fast_summary(markdown: str, fallback_title: str, source: str) -> str:
    clean_notes = re.sub(r"\n{3,}", "\n\n", str(markdown or "")).strip()
    title = next((line[2:].strip() for line in clean_notes.splitlines() if line.startswith("# ")), fallback_title)
    objectives = _bullets(_section(clean_notes, "Learning Objectives", 2), 4)
    why = _section(clean_notes, "Why It Matters", 3)
    mechanisms = _section(clean_notes, "Core Mechanisms", 3)
    definitions = _section(clean_notes, "Key Definitions", 3)
    comparison = _section(clean_notes, "Comparison and Relationships", 3)

    executive_items = _sentences(why, 2) + _sentences(mechanisms, 2)
    executive = " ".join(executive_items)
    if not executive:
        body = re.sub(r"(?m)^#{1,6}\s+.*$", "", clean_notes)
        executive = " ".join(_sentences(body, 3))
    if not executive:
        executive = "A concise, source-grounded overview of the uploaded learning material."

    concepts = _bullets(definitions, 5) or _sentences(mechanisms, 4)

    takeaways: list[str] = []
    for block in (why, mechanisms, comparison):
        for item in _sentences(block, 3):
            if item not in takeaways:
                takeaways.append(item)
            if len(takeaways) >= 5:
                break

    lines = [
        f"<!-- {SCHEMA_VERSION} -->",
        f"# {title}",
        "",
        "## Executive Summary",
        executive,
        "",
        "## Learning Objectives",
    ]
    lines.extend(f"- {item}" for item in (objectives or [
        "Explain the central concepts and their relationships.",
        "Apply the source material during review and assessment.",
    ]))
    lines.extend(["", "## Core Concepts"])
    lines.extend(f"- {item}" for item in (concepts or takeaways[:4]))
    lines.extend(["", "## Why It Matters", why or executive])
    lines.extend(["", "## How It Works", mechanisms or executive])
    lines.extend(["", "## Key Takeaways"])
    lines.extend(f"- {item}" for item in (takeaways[:5] or [executive]))
    lines.extend([
        "",
        "## One-Minute Review",
        "Review the core mechanism, practical benefit, diagnostic or application method, and principal limitation described by the source.",
        "",
        "## Sources",
        f"- {source}",
    ])
    return "\n".join(lines).strip()


def _inline(s: str) -> str:
    x = html.escape(s)
    x = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", x)
    x = re.sub(r"`(.+?)`", r"<code>\1</code>", x)
    return x


def md_to_html(md: str) -> str:
    lines = str(md or "").splitlines()
    out: list[str] = []
    in_code = False
    bullets = False
    css = """<style>
body{font-family:"Segoe UI",Arial;color:#172033;background:#fffaf3;line-height:1.55;margin:22px}
h1{font-size:28px;color:#0f172a;border-bottom:3px solid #38bdf8;padding-bottom:10px}
h2{font-size:20px;color:#0e7490;margin-top:24px}
h3{font-size:16px;color:#7c3aed}
.card{background:#f8fafc;border:1px solid #dbe7ef;border-radius:12px;padding:14px 18px;margin:12px 0}
code,pre{font-family:Consolas;background:#0f172a;color:#e2e8f0;border-radius:8px}
pre{padding:14px;white-space:pre-wrap}
li{margin:6px 0}
blockquote{border-left:4px solid #f59e0b;background:#fff7e6;padding:10px 14px;margin:12px 0}
</style>"""
    for line in lines:
        s = line.rstrip()
        if s.strip().startswith("```"):
            if bullets:
                out.append("</ul>")
                bullets = False
            out.append("</pre>" if in_code else "<pre>")
            in_code = not in_code
            continue
        if in_code:
            out.append(html.escape(s))
            continue
        m = re.match(r"^(#{1,3})\s+(.*)", s)
        if m:
            if bullets:
                out.append("</ul>")
                bullets = False
            n = len(m.group(1))
            out.append(f"<h{n}>{html.escape(m.group(2))}</h{n}>")
            continue
        if re.match(r"^[-*]\s+", s):
            if not bullets:
                out.append("<ul>")
                bullets = True
            out.append(f"<li>{_inline(s[2:])}</li>")
            continue
        if bullets:
            out.append("</ul>")
            bullets = False
        if s.startswith(">"):
            out.append(f"<blockquote>{_inline(s.lstrip('> '))}</blockquote>")
        elif s.strip():
            out.append(f'<div class="card">{_inline(s)}</div>')
    if bullets:
        out.append("</ul>")
    if in_code:
        out.append("</pre>")
    return f"<html><head>{css}</head><body>{''.join(out)}</body></html>"


def outline_html(md: str) -> str:
    heads: list[tuple[int, str]] = []
    for line in str(md).splitlines():
        m = re.match(r"^(#{1,3})\s+(.*)", line.strip())
        if m:
            heads.append((len(m.group(1)), m.group(2)))
    rows = "".join(
        f'<div style="margin-left:{(n-1)*22}px;padding:9px;border-left:3px solid #{"38bdf8" if n==1 else "8b5cf6"};margin-bottom:7px"><b>{html.escape(t)}</b></div>'
        for n, t in heads
    )
    return f'<html><body style="font-family:Segoe UI;color:#172033;background:#fffaf3;margin:22px"><h2>Study Outline</h2>{rows}</body></html>'


def concepts_html(md: str) -> str:
    stop = {"offline study notes", "key points from the source material", "suggested study actions", "learning objectives", "sources"}
    values: list[str] = []
    for line in str(md).splitlines():
        s = re.sub(r"^#{1,3}\s+|^[-*]\s+", "", line.strip()).strip()
        if not s or s.lower() in stop or _is_weak(s) or len(s) > 90:
            continue
        if any(k in s.lower() for k in ("concept", "definition", "mechanism", "principle", "rule", "law", "theory", "method")):
            if s not in values:
                values.append(s)
    cards = "".join(
        f'<span style="display:inline-block;background:#eef8ff;border:1px solid #38bdf8;border-radius:16px;padding:8px 12px;margin:6px">{html.escape(v)}</span>'
        for v in values[:16]
    )
    return f'<html><body style="font-family:Segoe UI;color:#172033;background:#fffaf3;margin:22px"><h2>Core Concepts</h2>{cards}</body></html>'