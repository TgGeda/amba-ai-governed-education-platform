from __future__ import annotations

from dataclasses import replace
import re
from typing import Any

from ..schemas import LearningDocument
from .networking import NetworkingDomainPlugin


class PatternAdapter:
    def __init__(
        self,
        name: str,
        pattern: str,
        threshold: int = 5,
        priority: int = 10,
        pedagogical_approach: str = "direct_instruction",
        keywords: tuple[str, ...] = (),
    ) -> None:
        self.name = name
        self.pattern = re.compile(pattern, re.IGNORECASE)
        self.threshold = max(1, threshold)
        self.priority = priority
        self.pedagogical_approach = pedagogical_approach
        self.keywords = frozenset(k.casefold() for k in keywords)

    def score(self, text: str, metadata: dict[str, Any]) -> float:
        matches = len(self.pattern.findall(text))
        base_score = min(1.0, matches / float(self.threshold))
        meta_boost = 0.0
        meta_text = " ".join(str(v) for v in metadata.values()).casefold()

        if self.name.casefold() in meta_text:
            meta_boost += 0.35
        for kw in self.keywords:
            if kw in meta_text:
                meta_boost += 0.15

        return min(1.0, (base_score * 0.7) + (min(0.5, meta_boost) * 0.3))

    def enrich(self, document: LearningDocument) -> LearningDocument:
        meta = dict(document.metadata)
        meta["pedagogical_approach"] = self.pedagogical_approach
        meta["resolved_domain"] = self.name
        return replace(document, domain=self.name, metadata=meta)


ADAPTERS = (
    PatternAdapter(
        "mathematics",
        r"(?:\btheorem\b|\bequation\b|\bproof\b|[=∑√∫±×÷≤≥≠≈∝∞]|\bcalculate\b|\bpolynomial\b|\bderivative\b|\bintegral\b|\bmatrix\b|\bvector\b|\bgeometry\b|\balgebra\b|\bcalculus\b|\btrigonometry\b)",
        6,
        60,
        "worked_example_inquiry",
        ("math", "mathematics", "algebra", "geometry", "calculus", "stats", "statistics"),
    ),
    PatternAdapter(
        "programming",
        r"(?:```\w*|\bfunction\b|\bclass\b|\bvariable\b|\balgorithm\b|\breturn\b|\bimport\b|\bpackage\b|\bdef\b|\bvoid\b|\bpublic\b|\binterface\b|\bpointer\b|\bdata structure\b|\bcomplexity\b|\bgithub\b|\brepository\b)",
        7,
        55,
        "interactive_coding_scaffold",
        ("code", "programming", "software", "development", "python", "java", "javascript", "c++"),
    ),
    PatternAdapter(
        "natural_sciences",
        r"(?:\bexperiment\b|\bhypothesis\b|\bprocess\b|\bmeasurement\b|\benergy\b|\bcell\b|\bmolecule\b|\borganism\b|\bphotosynthesis\b|\bvelocity\b|\bacceleration\b|\bgravity\b|\bchemical\b|\breaction\b|\bevolution\b|\becosystem\b)",
        7,
        45,
        "scientific_inquiry_empirical",
        ("physics", "chemistry", "biology", "science", "ecology", "geology"),
    ),
    PatternAdapter(
        "medicine_health",
        r"(?:\bpatient\b|\bclinical\b|\bsymptom\b|\bdiagnosis\b|\btreatment\b|\bpathology\b|\btherapy\b|\bpharmacy\b|\bdisease\b|\banatomy\b|\bphysiology\b|\bdosage\b|\bprotocol\b|\bprognosis\b)",
        6,
        45,
        "clinical_case_based",
        ("medicine", "medical", "health", "nursing", "pharmacology", "clinical"),
    ),
    PatternAdapter(
        "business_economics",
        r"(?:\bmarket\b|\beconomy\b|\bfinance\b|\binflation\b|\bgdp\b|\brevenue\b|\bprofit\b|\binvestment\b|\bconsumer\b|\bsupply\b|\bdemand\b|\bcapital\b|\bliquidity\b|\binterest rate\b|\bmonetary\b)",
        6,
        40,
        "case_study_decision_framework",
        ("economics", "business", "finance", "accounting", "marketing", "management"),
    ),
    PatternAdapter(
        "language_linguistics",
        r"(?:\bgrammar\b|\bvocabulary\b|\btense\b|\bpronunciation\b|\btranslate\b|\bsyntax\b|\bmorphology\b|\bphonetics\b|\bsemantics\b|\bidiom\b|\bclause\b|\bpreposition\b|\bconjugation\b)",
        5,
        40,
        "communicative_drill_immersion",
        ("language", "english", "linguistics", "grammar", "spanish", "french", "german"),
    ),
    PatternAdapter(
        "humanities_social",
        r"(?:\bhistory\b|\bgovernment\b|\bculture\b|\bcentury\b|\btimeline\b|\bcivilization\b|\bphilosophy\b|\bsociology\b|\bpolitics\b|\bconstitution\b|\bdemocracy\b|\bart\b|\bliterature\b|\brevolution\b)",
        7,
        30,
        "socratic_dialogue_critical_thinking",
        ("history", "philosophy", "sociology", "political science", "humanities", "civics"),
    ),
    PatternAdapter(
        "general",
        r"$^",
        1,
        0,
        "universal_pedagogical_scaffold",
        (),
    ),
)

__all__ = [
    "ADAPTERS",
    "NetworkingDomainPlugin",
    "PatternAdapter",
]