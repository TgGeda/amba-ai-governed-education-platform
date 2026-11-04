from __future__ import annotations

import pytest

from amba_ai.rag.policy_chunking import PolicyStructureChunker


def test_structural_units_are_preserved() -> None:
    chunks = PolicyStructureChunker().chunk(
        record_id="record",
        locator="synthetic://record",
        text=(
            "Clause Scope\n"
            "Applies here.\n"
            "Clause Rule\n"
            "Do not distribute."
        ),
    )

    assert len(chunks) == 2
    assert chunks[0].text == (
        "Clause Scope\n"
        "Applies here."
    )
    assert chunks[1].text == (
        "Clause Rule\n"
        "Do not distribute."
    )
    assert all(
        chunk.locator == "synthetic://record"
        for chunk in chunks
    )


def test_deterministic_ids_and_integrity_hashes() -> None:
    chunker = PolicyStructureChunker()

    first = chunker.chunk(
        record_id="record",
        locator="synthetic://record",
        text="Section One\nText",
    )

    second = chunker.chunk(
        record_id="record",
        locator="synthetic://record",
        text="Section One\nText",
    )

    assert first == second
    assert first[0].chunk_id == second[0].chunk_id
    assert len(first[0].text_sha256) == 64
    assert (
        first[0].to_canonical_json()
        == first[0].to_canonical_json()
    )


def test_numbered_paragraphs_and_tables_are_structural() -> None:
    chunks = PolicyStructureChunker().chunk(
        record_id="record",
        locator="synthetic://record",
        text=(
            "1. Scope\n"
            "Applies.\n"
            "\n"
            "Metric | Threshold | Unit\n"
            "--- | --- | ---\n"
            "Latency | 50 | ms\n"
            "Availability | 99.9 | percent"
        ),
    )

    assert any(
        chunk.structure_type == "numbered_paragraph"
        for chunk in chunks
    )

    rows = tuple(
        chunk
        for chunk in chunks
        if chunk.structure_type == "table_row"
    )

    assert len(rows) == 2

    assert all(
        "Metric | Threshold | Unit" in row.text
        for row in rows
    )

    assert rows[0].text.endswith(
        "Latency | 50 | ms"
    )

    assert rows[1].text.endswith(
        "Availability | 99.9 | percent"
    )


def test_debug_table_parsing() -> None:
    chunks = PolicyStructureChunker().chunk(
        record_id="record",
        locator="synthetic://record",
        text=(
            "1. Scope\n"
            "Applies.\n"
            "\n"
            "Metric | Threshold | Unit\n"
            "--- | --- | ---\n"
            "Latency | 50 | ms\n"
            "Availability | 99.9 | percent"
        ),
    )

    print()

    for chunk in chunks:
        print(
            chunk.structure_type,
            repr(chunk.text),
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "record_id": "",
            "text": "x",
            "locator": "l",
        },
        {
            "record_id": "r",
            "text": "",
            "locator": "l",
        },
        {
            "record_id": "r",
            "text": "x",
            "locator": "",
        },
    ],
)
def test_invalid_inputs_fail(
    kwargs: dict[str, str],
) -> None:
    with pytest.raises(ValueError):
        PolicyStructureChunker().chunk(**kwargs)