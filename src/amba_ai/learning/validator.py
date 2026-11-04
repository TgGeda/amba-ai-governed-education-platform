from __future__ import annotations

from .schemas import LearningDocument, ValidationIssue, ValidationReport


class LearningDocumentValidator:
    def validate(self, document: LearningDocument) -> ValidationReport:
        issues: list[ValidationIssue] = []

        if not document.title.strip() or document.title.casefold() in {
            "untitled",
            "document",
            "learning material",
        }:
            issues.append(
                ValidationIssue(
                    "low_quality_title",
                    "Document title is generic or missing",
                    "error",
                    "title",
                )
            )

        if not document.sections:
            issues.append(
                ValidationIssue(
                    "missing_sections",
                    "No learning sections were identified",
                    "error",
                    "sections",
                )
            )

        if not document.executive_summary.strip():
            issues.append(
                ValidationIssue(
                    "missing_executive_summary",
                    "Executive summary is missing",
                    "warning",
                    "executive_summary",
                )
            )

        if not document.learning_objectives:
            issues.append(
                ValidationIssue(
                    "missing_learning_objectives",
                    "Document does not declare learning objectives",
                    "info",
                    "learning_objectives",
                )
            )

        seen_concepts: set[str] = set()
        for concept in document.concepts:
            key = concept.name.casefold()
            if key in seen_concepts:
                issues.append(
                    ValidationIssue(
                        "duplicate_concept",
                        f"Concept defined multiple times: {concept.name}",
                        "warning",
                        f"concept:{concept.concept_id}",
                    )
                )
            seen_concepts.add(key)
            if len(concept.definition.strip()) < 10:
                issues.append(
                    ValidationIssue(
                        "shallow_definition",
                        f"Concept definition too brief: {concept.name}",
                        "warning",
                        f"concept:{concept.concept_id}",
                    )
                )
            if (
                concept.name.casefold() in concept.definition.casefold().split()[:2]
                and len(concept.definition.split()) < 4
            ):
                issues.append(
                    ValidationIssue(
                        "circular_definition",
                        f"Concept appears circular: {concept.name}",
                        "warning",
                        f"concept:{concept.concept_id}",
                    )
                )

        section_ids = {s.section_id for s in document.sections}
        for section in document.sections:
            if section.parent_id and section.parent_id not in section_ids:
                issues.append(
                    ValidationIssue(
                        "broken_parent_hierarchy",
                        f"Section '{section.heading}' references nonexistent parent",
                        "error",
                        f"section:{section.section_id}",
                    )
                )
            if (
                not section.explanation.strip()
                and not section.key_points
                and not section.technical_blocks
            ):
                issues.append(
                    ValidationIssue(
                        "empty_section",
                        f"Section has no explanatory content: {section.heading}",
                        "warning",
                        f"section:{section.section_id}",
                    )
                )

        error_count = sum(1 for i in issues if i.severity == "error")
        warning_count = sum(1 for i in issues if i.severity == "warning")
        quality_score = max(0.0, min(1.0, 1.0 - (error_count * 0.3) - (warning_count * 0.05)))

        return ValidationReport(
            valid=error_count == 0,
            issues=tuple(issues),
            quality_score=round(quality_score, 2),
        )