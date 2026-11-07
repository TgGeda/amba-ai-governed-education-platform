from __future__ import annotations

from dataclasses import replace

import pytest

from amba_ai.governance.models import LocatorVerificationStatus, PolicyRecordIdentity
from amba_ai.governance.record_registry import PolicyRecordRegistry
from amba_ai.governance.verified_policy_records import verified_itu_y3172_records
from amba_ai.rag.policy_chunk_models import PolicyChunkError
from amba_ai.rag.policy_chunk_record_linker import (
    ChunkRecordMatchStatus,
    ExcerptExactness,
    PolicyChunkRecordLink,
    PolicyChunkRecordLinker,
    SourcePolicyChunk,
    build_link_report,
)

ARTIFACT = "e42f9a3be3f951d3e19b9007f876f0b389c81b4693f0d8576e18185a1acfe67b"
SOURCE = "ITU-T-Y3172-2019"
VERSION = "1.0"


def registry_and_records():
    registry = PolicyRecordRegistry()
    records = verified_itu_y3172_records()
    for record in records:
        registry.register(record)
    return registry, {record.official_locator: record for record in records}


def chunk(text: str, *, page: int = 10, source: str = SOURCE, version: str = VERSION, artifact: str = ARTIFACT, ordinal: int = 0):
    return SourcePolicyChunk.create(
        source_id=source,
        version_id=version,
        artifact_sha256=artifact,
        page_start=page,
        page_end=page,
        raw_text=text,
        ordinal=ordinal,
    )


@pytest.mark.parametrize(
    ("locator", "heading"),
    (
        ("Clause 3.2.6", "3.2.6 ML sandbox\nDefinition text."),
        ("Clause 7.4", "7.4 Declarative ML application specification\nText."),
        ("Clause 8.1", "8.1 High-level ML pipeline components\nText."),
        ("Clause 9", "9 Security considerations\nText."),
    ),
)
def test_single_clause_records_link_structurally(locator: str, heading: str) -> None:
    registry, records = registry_and_records()
    link = PolicyChunkRecordLinker(registry).link_chunk(chunk(heading), records[locator].identity)
    assert link.match_status is ChunkRecordMatchStatus.STRUCTURAL_MATCH
    assert link.excerpt_exactness is ExcerptExactness.SOURCE_DERIVED
    assert link.registered_locator == locator


def test_clause_8_2_contributes_to_multi_clause_record() -> None:
    registry, records = registry_and_records()
    record = records["Clauses 8.1 and 8.2"]
    link = PolicyChunkRecordLinker(registry).link_chunk(
        chunk("8.2 ML sandbox components\nText."), record.identity
    )
    assert link.match_status is ChunkRecordMatchStatus.PARTIAL_STRUCTURAL_MATCH
    assert link.matched_locators == ("8.2",)


def test_multi_clause_record_requires_both_locators_across_chunks() -> None:
    registry, records = registry_and_records()
    record = records["Clauses 8.1 and 8.2"]
    linker = PolicyChunkRecordLinker(registry)
    partial = linker.assess_record(
        (chunk("8.1 Architecture components\nText."),), record.identity
    )
    assert partial.match_status is ChunkRecordMatchStatus.PARTIAL_STRUCTURAL_MATCH
    assert partial.is_complete is False
    complete = linker.assess_record(
        (
            chunk("8.1 Architecture components\nText.", ordinal=0),
            chunk("8.2 Sandbox components\nText.", page=11, ordinal=1),
        ),
        record.identity,
    )
    assert complete.match_status is ChunkRecordMatchStatus.STRUCTURAL_MATCH
    assert complete.matched_locators == ("8.1", "8.2")
    assert complete.is_complete is True


def test_semantic_score_cannot_create_record_link() -> None:
    registry, records = registry_and_records()
    record = records["Clause 9"]
    linker = PolicyChunkRecordLinker(registry)
    no_score = linker.link_chunk(chunk("Unrelated source text."), record.identity)
    perfect_score = linker.link_chunk(
        chunk("Unrelated source text."), record.identity, semantic_score=1.0
    )
    assert no_score.match_status is ChunkRecordMatchStatus.LOCATOR_NOT_FOUND
    assert perfect_score.match_status is ChunkRecordMatchStatus.LOCATOR_NOT_FOUND


def test_source_id_mismatch_fails_closed() -> None:
    registry, records = registry_and_records()
    result = PolicyChunkRecordLinker(registry).link_chunk(
        chunk("9 Security considerations", source="OTHER-SOURCE"),
        records["Clause 9"].identity,
    )
    assert result.match_status is ChunkRecordMatchStatus.SOURCE_IDENTITY_MISMATCH
    assert result.excerpt_exactness is ExcerptExactness.NOT_ASSESSED


def test_version_id_mismatch_fails_closed() -> None:
    registry, records = registry_and_records()
    result = PolicyChunkRecordLinker(registry).link_chunk(
        chunk("9 Security considerations", version="2.0"),
        records["Clause 9"].identity,
    )
    assert result.match_status is ChunkRecordMatchStatus.SOURCE_IDENTITY_MISMATCH


def test_artifact_digest_mismatch_fails_closed() -> None:
    registry, records = registry_and_records()
    result = PolicyChunkRecordLinker(registry).link_chunk(
        chunk("9 Security considerations", artifact="f" * 64),
        records["Clause 9"].identity,
    )
    assert result.match_status is ChunkRecordMatchStatus.ARTIFACT_MISMATCH


def test_structural_match_does_not_upgrade_to_exact() -> None:
    registry, records = registry_and_records()
    link = PolicyChunkRecordLinker(registry).link_chunk(
        chunk("9 Security considerations"), records["Clause 9"].identity
    )
    assert link.excerpt_exactness is ExcerptExactness.SOURCE_DERIVED
    assert records["Clause 9"].locator_verification_status is LocatorVerificationStatus.VERIFIED_STRUCTURAL
    with pytest.raises(PolicyChunkError, match="cannot produce verified_exact"):
        PolicyChunkRecordLink(
            chunk_id=link.chunk_id,
            record_identity=link.record_identity,
            match_status=ChunkRecordMatchStatus.STRUCTURAL_MATCH,
            matched_locators=("9",),
            required_locators=("9",),
            source_page_start=1,
            source_page_end=1,
            excerpt_exactness=ExcerptExactness.VERIFIED_EXACT,
            registered_locator="Clause 9",
        )


def test_chunk_page_range_is_preserved() -> None:
    registry, records = registry_and_records()
    candidate = SourcePolicyChunk.create(
        source_id=SOURCE,
        version_id=VERSION,
        artifact_sha256=ARTIFACT,
        page_start=20,
        page_end=21,
        raw_text="9 Security considerations",
        ordinal=0,
    )
    link = PolicyChunkRecordLinker(registry).link_chunk(candidate, records["Clause 9"].identity)
    assert (link.source_page_start, link.source_page_end) == (20, 21)


def test_registered_locator_remains_authoritative() -> None:
    registry, records = registry_and_records()
    record = records["Clause 7.4"]
    link = PolicyChunkRecordLinker(registry).link_chunk(
        chunk("7.4 Declarative specification"), record.identity
    )
    assert link.registered_locator == record.official_locator
    assert link.matched_locators == ("7.4",)


def test_unmatched_source_chunk_has_no_record_authority() -> None:
    registry, records = registry_and_records()
    result = PolicyChunkRecordLinker(registry).link_chunk(
        chunk("Unmatched appendix material."), records["Clause 9"].identity
    )
    assert result.match_status is ChunkRecordMatchStatus.LOCATOR_NOT_FOUND
    assert result.matched_locators == ()
    assert result.excerpt_exactness is ExcerptExactness.NOT_ASSESSED


def test_non_structural_record_requires_human_review() -> None:
    registry, records = registry_and_records()
    original = records["Clause 9"]
    altered = replace(original, locator_verification_status=LocatorVerificationStatus.VERIFIED_EXACT)
    other_registry = PolicyRecordRegistry()
    other_registry.register(altered)
    result = PolicyChunkRecordLinker(other_registry).link_chunk(
        chunk("9 Security considerations"), altered.identity
    )
    assert result.match_status is ChunkRecordMatchStatus.HUMAN_REVIEW_REQUIRED


def test_report_is_deterministic_and_disclaims_exactness() -> None:
    registry, records = registry_and_records()
    linker = PolicyChunkRecordLinker(registry)
    assessment = linker.assess_record(
        (chunk("9 Security considerations"),), records["Clause 9"].identity
    )
    report = build_link_report(
        source_id=SOURCE,
        version_id=VERSION,
        artifact_sha256=ARTIFACT,
        assessments=(assessment,),
    )
    assert report["matching_method"] == "deterministic_structural_locator"
    assert report["semantic_score_creates_links"] is False
    assert report["verified_exact_excerpt_claimed"] is False
    assert report["formal_y3172_conformance_claimed"] is False
