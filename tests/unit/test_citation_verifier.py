from __future__ import annotations

import inspect
import pytest

import amba_ai.governance.citation_verifier as citation_module


def test_public_citation_verifier_boundary_exists() -> None:
    assert hasattr(citation_module, "CitationVerifier")
    assert inspect.isclass(citation_module.CitationVerifier)


def test_verifier_exposes_fail_closed_verification_method() -> None:
    methods = {name for name, value in inspect.getmembers(citation_module.CitationVerifier, inspect.isfunction)}
    assert methods.intersection({"verify", "verify_citations", "verify_citation"})


def test_result_type_supports_require_valid_when_exported() -> None:
    result_types = [value for name, value in vars(citation_module).items() if inspect.isclass(value) and name.endswith("VerificationResult")]
    assert result_types, "Citation verifier must export a typed verification result"
    assert any(callable(getattr(value, "require_valid", None)) for value in result_types)


def test_failure_codes_are_typed_unique_and_stable() -> None:
    code_types = [
        value
        for name, value in vars(
            citation_module
        ).items()
        if inspect.isclass(value)
        and name.endswith("FailureCode")
    ]

    assert code_types, (
        "Citation verifier must export typed "
        "failure codes"
    )

    for code_type in code_types:
        members = tuple(code_type)

        assert members, (
            f"{code_type.__name__} "
            "must not be empty"
        )

        values = tuple(
            member.value
            for member in members
        )

        assert all(
            isinstance(value, str)
            and value.strip()
            for value in values
        )

        assert len(values) == len(
            set(values)
        )