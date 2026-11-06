from __future__ import annotations

import io
import re
from typing import TextIO

from amba_ai.application.demo_service import JudgeDemoSummary, JudgeStageSummary

MAX_DISPLAY_ITEMS = 5
MAX_DISPLAY_LENGTH = 180
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class TerminalDemoPresenter:
    def render(
        self,
        summary: JudgeDemoSummary,
        *,
        stream: TextIO | None = None,
    ) -> str:
        if not isinstance(summary, JudgeDemoSummary):
            raise TypeError("summary must be a JudgeDemoSummary")
        lines = [
            "AMBA-GOV | EVIDENCE-GROUNDED EDUCATIONAL AI GOVERNANCE",
            f"Run: {_safe_text(summary.run_id)}",
            f"Scenario: {_safe_text(summary.scenario_id)}",
            f"Summary time: {_safe_text(summary.summarized_at)}",
            (
                "Claim boundary: application-level interpreted Y.3172 mapping; "
                "no formal conformance or certification claimed."
            ),
            f"Audit: VERIFIED ({summary.audited_block_count} blocks)",
            "",
        ]
        for stage in summary.stages:
            lines.extend(self._render_stage(stage))
        lines.extend(
            (
                "RUN LIMITATIONS AND INTEGRITY",
                f"  Limitations: {_join(summary.limitations)}",
                f"  Run digest: {_safe_text(summary.run_digest)}",
                f"  Summary digest: {_safe_text(summary.summary_digest)}",
                "  Synthetic: yes | Legal effect: no",
            )
        )
        rendered = "\n".join(lines)
        if stream is not None:
            stream.write(rendered)
            if not rendered.endswith("\n"):
                stream.write("\n")
        return rendered

    @staticmethod
    def _render_stage(stage: JudgeStageSummary) -> list[str]:
        lines = [
            f"STAGE {int(stage.stage)} | {_safe_text(stage.timestamp)}",
            f"  Released facts: {_join(stage.released_fact_ids)}",
            f"  Projections: {_join(stage.projection_ids)}",
            f"  Institutions: {_join(stage.institution_ids)}",
            f"  Observations: {stage.observation_count} | {_join(stage.observation_codes)}",
            f"  Unresolved: {_join(stage.unresolved_questions)}",
            f"  Conflicts: {_join(stage.conflict_ids)}",
            f"  Uncovered facts: {_join(stage.uncovered_fact_ids)}",
        ]
        for index, event in enumerate(stage.events, start=1):
            lines.extend(
                (
                    f"  EVENT {index} | {_safe_text(event.event_id)}",
                    f"    Operation: {_safe_text(event.operation_id)}",
                    f"    Destination: {_safe_text(event.destination_id)}",
                    f"    Recommendation: {_safe_text(event.recommended_action)}",
                    f"    Approval: {_safe_text(event.approval_status)}",
                    f"    Execution: {_safe_text(event.execution_status)}",
                    f"    Execution receipt: {_optional(event.execution_receipt_id)}",
                    f"    Review receipt: {_optional(event.review_queue_receipt_id)}",
                    f"    Distribution: {_optional(event.distribution_disposition)}",
                    f"    Acknowledgment: {_optional(event.acknowledgment_id)}",
                    f"    Y.3172 D: {_safe_text(event.distributor_status)}",
                    f"    Y.3172 SINK: {_safe_text(event.sink_status)}",
                    f"    Audit block: {event.audit_block_index}",
                    f"    Policy evidence: {_join(event.evidence_ids)}",
                    f"    Limitations: {_join(event.limitations)}",
                )
            )
        lines.append(f"  Stage digest: {_safe_text(stage.source_stage_digest)}")
        lines.append("")
        return lines


def _safe_text(value: object) -> str:
    cleaned = _CONTROL_CHARACTERS.sub("", str(value))
    return cleaned[:MAX_DISPLAY_LENGTH]


def _join(values: tuple[object, ...]) -> str:
    if not values:
        return "none"
    shown = tuple(_safe_text(item) for item in values[:MAX_DISPLAY_ITEMS])
    suffix = "" if len(values) <= MAX_DISPLAY_ITEMS else f" (+{len(values) - MAX_DISPLAY_ITEMS} more)"
    return ", ".join(shown) + suffix


def _optional(value: object | None) -> str:
    return "none" if value is None else _safe_text(value)
