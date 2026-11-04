from __future__ import annotations

import hashlib
import html
import re
from typing import Any

from .domain_registry import domain_registry
from .schemas import (
    LearningConcept,
    LearningDocument,
    LearningSection,
    SourceCitation,
    TechnicalBlock,
)
from .source_resolver import resolve_source_name

_COMMENT = re.compile(r"<!--.*?-->|&lt;!--.*?--&gt;", re.DOTALL | re.IGNORECASE)
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.+)$")
_FENCE = re.compile(r"^```\s*([\w+-]*)\s*$")
_DEF = re.compile(
    r"^\s*(?:[-*+]\s*)?(?:\*\*(?P<name1>[^*]+)\*\*|__(?P<name2>[^_]+)__|(?P<name3>[A-Z][A-Za-z0-9\s_-]{1,60}))\s*[:—–-]\s*(?P<defn>.{8,})$"
)
_MATH_BLOCK = re.compile(r"^\$\$(.+?)\$\$$", re.DOTALL)
_TECH_CMD = re.compile(
    r"(?:\b(?:sudo|python|pip|curl|wget|git|docker|kubectl|npm|java|gcc|g\+\+|ssh|grep|awk|sed|netstat|openssl|tcpdump|cmake|cargo|make)\b|[=∑√∫∂λπ]|\b(?:formula|algorithm|procedure|command)\b)",
    re.IGNORECASE,
)
_INSTRUCTION = re.compile(
    r"^(?:identify|understand|learn|review|explore|explain|describe|discuss|compare|ask|study|read|practice|solve|note|remember)\b",
    re.IGNORECASE,
)
_CALLOUT = re.compile(
    r"^>\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION|EXAMPLE|MISCONCEPTION)\]\s*(.*)$",
    re.IGNORECASE,
)
_RESERVED = frozenset({
    "learning objectives",
    "core concepts",
    "key concepts",
    "structured study notes",
    "sources",
    "summary",
    "notes",
    "overview",
    "table of contents",
    "references",
    "introduction",
})
_BLOOM_VERBS = {
    "remember": frozenset({"define", "list", "recall", "state", "identify", "name", "recognize"}),
    "understand": frozenset({"explain", "describe", "summarize", "paraphrase", "classify", "compare", "interpret"}),
    "apply": frozenset({"calculate", "solve", "implement", "demonstrate", "use", "apply", "execute", "construct"}),
    "analyze": frozenset({"analyze", "differentiate", "examine", "distinguish", "categorize", "investigate"}),
    "evaluate": frozenset({"evaluate", "assess", "justify", "critique", "judge", "rate", "verify"}),
    "create": frozenset({"design", "formulate", "synthesize", "develop", "generate", "compose", "plan"}),
}


def clean_text(value: Any) -> str:
    text = html.unescape(str(value or "")).replace("\\n", "\n")
    cleaned = _COMMENT.sub("", text)
    cleaned = re.sub(r"<br\s*/?>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace("\r", "")
    return cleaned.strip()


def strip_markdown(text: str) -> str:
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*|__([^_]+)__", lambda m: m.group(1) or m.group(2), text)
    text = re.sub(r"\*([^*]+)\*|_([^_]+)_", lambda m: m.group(1) or m.group(2), text)
    return re.sub(r"\s+", " ", text).strip()


def slugify(text: str) -> str:
    val = re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-")
    if val:
        return val
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def infer_bloom_level(text: str) -> str:
    tokens = re.findall(r"\b[a-z]{3,}\b", text.casefold())
    for level, verbs in _BLOOM_VERBS.items():
        if any(token in verbs for token in tokens):
            return level
    return "understand"


def is_valid_concept(name: str, definition: str) -> bool:
    clean_name = strip_markdown(name).strip(" .:-–—")
    clean_def = strip_markdown(definition)
    if len(clean_name) < 2 or len(clean_name) > 70:
        return False
    if clean_name.casefold() in _RESERVED:
        return False
    if _INSTRUCTION.match(clean_name):
        return False
    if len(clean_name.split()) > 8:
        return False
    if len(clean_def) < 8:
        return False
    if clean_name.endswith((".", "?", "!")):
        return False
    return True


class DocumentAgnosticLearningParser:
    def parse(
        self,
        *,
        document_id: int,
        markdown: str,
        metadata: dict[str, Any] | None = None,
        title: str | None = None,
        source_name: str | None = None,
    ) -> LearningDocument:
        meta = dict(metadata or {})
        text = clean_text(markdown)
        lines = text.splitlines()

        detected_title = (
            title
            or next(
                (
                    strip_markdown(m.group(2))
                    for line in lines
                    if (m := _HEADING.match(line.strip())) and len(m.group(1)) == 1
                ),
                "",
            )
            or str(meta.get("title") or "Learning Material")
        )
        resolved_source = source_name or resolve_source_name(meta, fallback=detected_title)
        citation = SourceCitation(source_name=resolved_source)

        raw_sections: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        fenced = False
        lang = ""
        code_lines: list[str] = []

        for raw_line in lines:
            stripped = raw_line.strip()
            fence_match = _FENCE.match(stripped)
            if fence_match:
                if not fenced:
                    fenced = True
                    lang = fence_match.group(1) or "text"
                    code_lines = []
                else:
                    if current is None:
                        current = {
                            "heading": "Technical Reference",
                            "level": 2,
                            "lines": [],
                            "blocks": [],
                            "callouts": [],
                        }
                        raw_sections.append(current)
                    current["blocks"].append((lang, "\n".join(code_lines).strip()))
                    fenced = False
                continue

            if fenced:
                code_lines.append(raw_line.rstrip())
                continue

            heading_match = _HEADING.match(stripped)
            if heading_match:
                h_level = len(heading_match.group(1))
                if h_level == 1 and not raw_sections:
                    continue
                current = {
                    "heading": strip_markdown(heading_match.group(2)),
                    "level": h_level,
                    "lines": [],
                    "blocks": [],
                    "callouts": [],
                }
                raw_sections.append(current)
                continue

            if current is None:
                current = {"heading": "Overview", "level": 2, "lines": [], "blocks": [], "callouts": []}
                raw_sections.append(current)

            callout_match = _CALLOUT.match(stripped)
            if callout_match:
                current["callouts"].append(
                    (callout_match.group(1).upper(), callout_match.group(2).strip())
                )
                continue

            current["lines"].append(raw_line)

        sections: list[LearningSection] = []
        concepts_map: dict[str, LearningConcept] = {}
        objectives: list[str] = []
        executive_summary = ""
        parents_hierarchy: dict[int, str] = {}
        total_word_count = 0
        bloom_counts: dict[str, int] = {}

        for index, raw in enumerate(raw_sections):
            heading = raw["heading"]
            level = int(raw["level"])
            section_id = slugify(f"{index}-{heading}")
            parent_id = next(
                (parents_hierarchy[lvl] for lvl in range(level - 1, 1, -1) if lvl in parents_hierarchy),
                None,
            )
            parents_hierarchy[level] = section_id
            for higher_level in list(parents_hierarchy.keys()):
                if higher_level > level:
                    parents_hierarchy.pop(higher_level, None)

            paragraphs: list[str] = []
            key_points: list[str] = []
            examples: list[str] = []
            misconceptions: list[str] = []
            section_concepts: list[LearningConcept] = []
            blocks: list[TechnicalBlock] = []
            line_buffer: list[str] = []

            def flush_buffer() -> None:
                if line_buffer:
                    para = strip_markdown(" ".join(line_buffer))
                    if para:
                        paragraphs.append(para)
                    line_buffer.clear()

            for src_line in raw["lines"]:
                line_str = src_line.strip()
                if not line_str:
                    flush_buffer()
                    continue

                bullet_match = _BULLET.match(line_str)
                candidate = bullet_match.group(1) if bullet_match else line_str
                if bullet_match:
                    flush_buffer()
                    point = strip_markdown(candidate)
                    if point:
                        key_points.append(point)
                else:
                    line_buffer.append(line_str)

                def_match = _DEF.match(candidate)
                if def_match:
                    name_cand = (
                        def_match.group("name1")
                        or def_match.group("name2")
                        or def_match.group("name3")
                        or ""
                    )
                    defn_cand = def_match.group("defn") or ""
                    if is_valid_concept(name_cand, defn_cand):
                        c_name = strip_markdown(name_cand).strip(" .:-–—")
                        c_defn = strip_markdown(defn_cand)
                        c_key = c_name.casefold()
                        c_bloom = infer_bloom_level(c_defn)
                        bloom_counts[c_bloom] = bloom_counts.get(c_bloom, 0) + 1
                        concept = concepts_map.get(c_key) or LearningConcept(
                            concept_id=slugify(c_name),
                            name=c_name,
                            category="core_concept",
                            definition=c_defn,
                            bloom_level=c_bloom,
                            citations=(citation,),
                        )
                        concepts_map[c_key] = concept
                        section_concepts.append(concept)

                cand_lower = candidate.casefold()
                if cand_lower.startswith(("for example:", "example:", "e.g.,", "e.g.")):
                    examples.append(strip_markdown(candidate))
                elif "misconception:" in cand_lower or "common mistake:" in cand_lower:
                    misconceptions.append(strip_markdown(candidate))

                if _TECH_CMD.search(candidate) and ("`" in candidate or candidate.startswith(("$ ", "> "))):
                    cleaned_cmd = strip_markdown(candidate).lstrip("$> ")
                    if cleaned_cmd:
                        blocks.append(
                            TechnicalBlock(
                                block_id=slugify(f"{section_id}-{len(blocks)}"),
                                block_type="command",
                                label=heading,
                                content=cleaned_cmd,
                                citations=(citation,),
                            )
                        )

            flush_buffer()

            for kind, callout_text in raw["callouts"]:
                if kind == "MISCONCEPTION":
                    misconceptions.append(callout_text)
                elif kind == "EXAMPLE":
                    examples.append(callout_text)
                else:
                    key_points.append(f"[{kind}] {callout_text}")

            for block_lang, block_code in raw["blocks"]:
                if block_code:
                    b_type = (
                        "formula"
                        if block_lang.casefold() in {"math", "latex", "tex"}
                        else "code"
                    )
                    blocks.append(
                        TechnicalBlock(
                            block_id=slugify(f"{section_id}-blk-{len(blocks)}"),
                            block_type=b_type,
                            label=heading,
                            content=block_code,
                            language=block_lang or "text",
                            citations=(citation,),
                        )
                    )

            body = "\n\n".join(paragraphs)
            sec_word_count = len(body.split()) + sum(len(kp.split()) for kp in key_points)
            total_word_count += sec_word_count
            reading_time = round(sec_word_count / 200.0, 2)

            low_heading = heading.casefold()
            if "objective" in low_heading:
                for kp in key_points:
                    if kp not in objectives:
                        objectives.append(kp)
            if not executive_summary and (
                "executive summary" in low_heading or low_heading in {"overview", "abstract"}
            ):
                executive_summary = body

            sections.append(
                LearningSection(
                    section_id=section_id,
                    heading=heading,
                    explanation=body,
                    level=level,
                    parent_id=parent_id,
                    key_points=tuple(key_points),
                    concepts=tuple(dict.fromkeys(section_concepts)),
                    technical_blocks=tuple(blocks),
                    examples=tuple(examples),
                    misconceptions=tuple(misconceptions),
                    citations=(citation,),
                    word_count=sec_word_count,
                    reading_time_minutes=reading_time,
                )
            )

        if not executive_summary:
            executive_summary = next(
                (s.explanation for s in sections if len(s.explanation) > 30), ""
            )

        if not objectives:
            for s in sections:
                if s.key_points:
                    for kp in s.key_points:
                        if len(kp) > 10 and kp not in objectives:
                            objectives.append(kp)
                        if len(objectives) >= 4:
                            break
                if len(objectives) >= 4:
                    break

        study_time = max(1, round(total_word_count / 150.0))

        doc = LearningDocument(
            document_id=document_id,
            title=detected_title,
            source_name=resolved_source,
            executive_summary=executive_summary,
            learning_objectives=tuple(dict.fromkeys(objectives)),
            concepts=tuple(concepts_map.values()),
            sections=tuple(sections),
            citations=(citation,),
            target_grade_level=str(meta.get("grade_level") or "all"),
            estimated_study_time_minutes=study_time,
            bloom_distribution=bloom_counts,
            metadata=meta,
        )

        adapter = domain_registry.resolve(text, meta)
        return adapter.enrich(doc)