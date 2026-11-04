from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import threading
from typing import Protocol, Sequence

try:
    from rapidfuzz import fuzz

    _HAS_RAPIDFUZZ = True
except ImportError:
    fuzz = None
    _HAS_RAPIDFUZZ = False

from amba_ai.learning.domain_plugin import DomainPlugin
from amba_ai.logger import logger
from amba_ai.models.schemas import Flashcard, MCQ


@dataclass(frozen=True, slots=True)
class KnowledgeEntry:
    canonical_question: str
    canonical_answer: str
    match_patterns: tuple[str, ...]
    keywords: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TelemetrySnapshot:
    fixes_applied: int
    mcqs_evaluated: int
    mcqs_rejected: int
    distractor_rationales_generated: int
    average_match_confidence: float
    min_match_confidence: float
    max_match_confidence: float


class KnowledgeRepository(Protocol):
    def match_entry(
        self, question: str, similarity_threshold: float = 0.78
    ) -> tuple[KnowledgeEntry | None, float]: ...


class PluginTelemetry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._fixes_applied: int = 0
        self._mcqs_evaluated: int = 0
        self._mcqs_rejected: int = 0
        self._distractor_rationales_generated: int = 0
        self._confidence_sum: float = 0.0
        self._min_confidence: float = 1.0
        self._max_confidence: float = 0.0

    def record_fix(self, confidence: float) -> None:
        with self._lock:
            self._fixes_applied += 1
            self._confidence_sum += confidence
            if confidence < self._min_confidence:
                self._min_confidence = confidence
            if confidence > self._max_confidence:
                self._max_confidence = confidence

    def record_mcq_evaluated(self) -> None:
        with self._lock:
            self._mcqs_evaluated += 1

    def record_mcq_rejected(self) -> None:
        with self._lock:
            self._mcqs_rejected += 1

    def record_distractor_rationale(self) -> None:
        with self._lock:
            self._distractor_rationales_generated += 1

    def snapshot(self) -> TelemetrySnapshot:
        with self._lock:
            avg_conf = (
                round(self._confidence_sum / self._fixes_applied, 3)
                if self._fixes_applied > 0
                else 0.0
            )
            return TelemetrySnapshot(
                fixes_applied=self._fixes_applied,
                mcqs_evaluated=self._mcqs_evaluated,
                mcqs_rejected=self._mcqs_rejected,
                distractor_rationales_generated=self._distractor_rationales_generated,
                average_match_confidence=avg_conf,
                min_match_confidence=round(self._min_confidence, 3) if self._fixes_applied > 0 else 0.0,
                max_match_confidence=round(self._max_confidence, 3) if self._fixes_applied > 0 else 0.0,
            )


class NetworkingKnowledgeRepository(KnowledgeRepository):
    DEFAULT_ENTRIES = (
        KnowledgeEntry(
            canonical_question="What transport problem does QUIC reduce across unrelated streams?",
            canonical_answer="QUIC reduces cross-stream head-of-line blocking. Loss in one stream does not require unrelated streams to wait for recovery.",
            match_patterns=(
                "what does quic eliminate in traditional tcp",
                "what transport problem does quic reduce",
                "how does quic solve head of line blocking",
                "what does quic eliminate from tcp",
            ),
            keywords=("quic", "eliminate", "tcp"),
        ),
        KnowledgeEntry(
            canonical_question="How do standard 1-RTT setup and resumed 0-RTT differ in QUIC?",
            canonical_answer="A normal connection uses 1-RTT setup. An eligible resumed session may use 0-RTT when prior session state is available.",
            match_patterns=(
                "what is quic s handshake process",
                "how does quic handshake work",
                "difference between 1-rtt and 0-rtt in quic",
                "quic connection establishment time",
            ),
            keywords=("quic", "handshake"),
        ),
        KnowledgeEntry(
            canonical_question="Which curl command tests whether a server can use HTTP/3?",
            canonical_answer="Run curl --http3 -I https://example.com. If HTTP/3 is not negotiated, another supported HTTP version may be used.",
            match_patterns=(
                "how do you check for http 3 support using curl",
                "test http3 support with curl",
                "command to check http 3 curl",
            ),
            keywords=("curl", "http", "3"),
        ),
        KnowledgeEntry(
            canonical_question="Which host-level commands can inspect UDP port 443 usage?",
            canonical_answer="Use `ss -u -a | grep 443`, `netstat -uapn | grep 443`, or `lsof -i UDP:443`.",
            match_patterns=(
                "how do you diagnose quic support on a host",
                "inspect udp port 443 commands",
                "commands to check port 443 udp host",
            ),
            keywords=("diagnose", "quic", "host"),
        ),
        KnowledgeEntry(
            canonical_question="Why does QUIC require different diagnostic techniques than TCP?",
            canonical_answer="Much of QUIC transport metadata is encrypted, so diagnosis relies more on latency, loss, jitter, flow behavior, endpoint telemetry, and logs.",
            match_patterns=(
                "what is the importance of quic s removal of tcp level observability",
                "why does quic make monitoring difficult",
                "quic observability challenges compared to tcp",
            ),
            keywords=("quic", "observability"),
        ),
        KnowledgeEntry(
            canonical_question="Which deployment examples does the source associate with QUIC and HTTP/3?",
            canonical_answer="The source mentions Google, YouTube, Cloudflare, and mobile traffic as deployment examples.",
            match_patterns=(
                "where is quic already widely used",
                "quic real world deployments",
                "companies using quic and http3",
            ),
            keywords=("quic", "widely", "used"),
        ),
        KnowledgeEntry(
            canonical_question="Which Wireshark display filters can help identify QUIC traffic?",
            canonical_answer="Useful filters include `udp.port == 443`, `quic`, and `tls && udp`.",
            match_patterns=(
                "what does wireshark show about quic",
                "wireshark filters for quic traffic",
                "inspect quic in wireshark",
            ),
            keywords=("wireshark", "quic"),
        ),
        KnowledgeEntry(
            canonical_question="What does the ALPN identifier `h3` represent?",
            canonical_answer="The `h3` identifier represents HTTP/3, which runs over QUIC.",
            match_patterns=(
                "what does the presence of h3 indicate in tls alpn",
                "what does alpn identifier h3 mean",
                "tls alpn h3 negotiation",
            ),
            keywords=("alpn", "h3"),
        ),
    )

    def __init__(self, override_file: Path | None = None) -> None:
        self._entries: list[KnowledgeEntry] = list(self.DEFAULT_ENTRIES)
        if override_file and override_file.exists():
            self._load_from_file(override_file)

    def _load_from_file(self, file_path: Path) -> None:
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                custom: list[KnowledgeEntry] = []
                for item in data:
                    custom.append(
                        KnowledgeEntry(
                            canonical_question=item["canonical_question"],
                            canonical_answer=item["canonical_answer"],
                            match_patterns=tuple(item.get("match_patterns", ())),
                            keywords=tuple(item.get("keywords", ())),
                        )
                    )
                self._entries = custom
        except Exception as exc:
            logger.warning(
                "Failed to load networking knowledge overrides",
                extra={"context": {"path": str(file_path), "error": str(exc)}},
            )

    @staticmethod
    def _compute_fuzzy_ratio(text_a: str, text_b: str) -> float:
        if _HAS_RAPIDFUZZ and fuzz is not None:
            return float(fuzz.token_sort_ratio(text_a, text_b)) / 100.0
        return float(SequenceMatcher(None, text_a, text_b).ratio())

    def match_entry(
        self, question: str, similarity_threshold: float = 0.78
    ) -> tuple[KnowledgeEntry | None, float]:
        norm_q = re.sub(r"\W+", " ", question.lower()).strip()
        tokens = set(norm_q.split())

        best_entry: KnowledgeEntry | None = None
        best_composite_score = 0.0

        for entry in self._entries:
            keyword_score = 0.0
            if entry.keywords:
                overlap = len(set(entry.keywords) & tokens)
                keyword_score = overlap / len(entry.keywords)

            pattern_score = 0.0
            for pattern in entry.match_patterns:
                ratio = self._compute_fuzzy_ratio(norm_q, pattern)
                if ratio > pattern_score:
                    pattern_score = ratio

            composite_score = (0.70 * pattern_score) + (0.30 * keyword_score)

            if composite_score > best_composite_score:
                best_composite_score = composite_score
                best_entry = entry

        if best_composite_score >= similarity_threshold:
            return best_entry, round(best_composite_score, 3)

        return None, 0.0


class FlashcardRefiner:
    def __init__(
        self, repository: KnowledgeRepository, telemetry: PluginTelemetry
    ) -> None:
        self.repository = repository
        self.telemetry = telemetry

    def refine(self, cards: Sequence[Flashcard]) -> list[Flashcard]:
        refined: list[Flashcard] = []

        for card in cards:
            q_clean = re.sub(r"<[^>]+>", "", card.question).strip()
            a_clean = re.sub(r"<[^>]+>", "", card.answer).strip()

            entry, confidence = self.repository.match_entry(q_clean)
            if entry:
                self.telemetry.record_fix(confidence)
                logger.debug(
                    "Applied canonical networking knowledge match",
                    extra={
                        "context": {
                            "original_question": q_clean,
                            "canonical_question": entry.canonical_question,
                            "confidence": confidence,
                        }
                    },
                )
                refined.append(
                    Flashcard(
                        question=entry.canonical_question,
                        answer=entry.canonical_answer,
                        source_ref=card.source_ref,
                    )
                )
            else:
                refined.append(
                    Flashcard(
                        question=q_clean,
                        answer=a_clean,
                        source_ref=card.source_ref,
                    )
                )

        return refined


class MCQRefiner:
    def __init__(self, telemetry: PluginTelemetry) -> None:
        self.telemetry = telemetry

    def refine(self, mcqs: Sequence[MCQ]) -> list[MCQ]:
        refined: list[MCQ] = []

        for m in mcqs:
            self.telemetry.record_mcq_evaluated()
            q_clean = re.sub(r"<[^>]+>", "", m.question).strip()
            ch_clean = [re.sub(r"<[^>]+>", "", x).strip() for x in m.choices]
            ans_clean = re.sub(r"<[^>]+>", "", m.correct_answer).strip()
            exp_clean = re.sub(r"<[^>]+>", "", m.explanation).strip()

            if len(ch_clean) != 4:
                self.telemetry.record_mcq_rejected()
                continue

            if ans_clean not in ch_clean:
                self.telemetry.record_mcq_rejected()
                continue

            if len(set(ch_clean)) != 4:
                self.telemetry.record_mcq_rejected()
                continue

            refined.append(
                MCQ(
                    question=q_clean,
                    choices=ch_clean,
                    correct_answer=ans_clean,
                    explanation=exp_clean,
                    source_ref=m.source_ref,
                )
            )

        return refined


class DistractorAnalyzer:
    def __init__(self, telemetry: PluginTelemetry) -> None:
        self.telemetry = telemetry

    def analyze(self, question: str, choice: str, correct: str) -> str:
        self.telemetry.record_distractor_rationale()
        q_low = question.lower()
        c_low = choice.lower()

        if "port" in q_low:
            if "tcp" in c_low:
                return "QUIC web traffic is carried over UDP rather than TCP, commonly on port 443."
            if "80" in c_low:
                return "Port 80 is allocated to unencrypted HTTP, not standard HTTP/3 over QUIC."
            if "53" in c_low:
                return "Port 53 is reserved for DNS traffic."
            return "This port number does not match standard web transport services."

        if any(w in q_low for w in ("alpn", "identifier", "h3")):
            return "The tested protocol identifier is negotiated via TLS ALPN and does not match this option."

        if any(w in q_low for w in ("head-of-line", "stream", "blocking")):
            return "Stream multiplexing isolates loss recovery; this alternative does not reflect independent stream behavior."

        return f"This choice does not match the source-verified specification for {correct}."


class NetworkingDomainPlugin(DomainPlugin):
    @property
    def domain_name(self) -> str:
        return "networking"

    @property
    def description(self) -> str:
        return "Networking protocol and transport layer specialization."

    def __init__(self, override_file: Path | None = None) -> None:
        self.telemetry = PluginTelemetry()
        self.repository = NetworkingKnowledgeRepository(override_file)
        self.flashcard_refiner = FlashcardRefiner(self.repository, self.telemetry)
        self.mcq_refiner = MCQRefiner(self.telemetry)
        self.distractor_analyzer = DistractorAnalyzer(self.telemetry)

    def refine_flashcards(
        self,
        cards: Sequence[Flashcard],
        raw_text: str,
    ) -> list[Flashcard]:
        return self.flashcard_refiner.refine(cards)

    def refine_mcqs(
        self,
        mcqs: Sequence[MCQ],
        raw_text: str,
    ) -> list[MCQ]:
        return self.mcq_refiner.refine(mcqs)

    def get_alternative_distractor_rationale(
        self,
        question: str,
        choice: str,
        correct: str,
    ) -> str:
        return self.distractor_analyzer.analyze(question, choice, correct)