from __future__ import annotations

from pathlib import Path

import pytest

from amba_ai.application.settings import (
    ApplicationProfile,
    ApplicationSettings,
    default_settings,
)


def test_default_profiles_are_safe_and_distinct(tmp_path: Path) -> None:
    desktop = default_settings(ApplicationProfile.DESKTOP, project_root=tmp_path)
    headless = default_settings(ApplicationProfile.HEADLESS, project_root=tmp_path)
    demo = default_settings(ApplicationProfile.DEMO, project_root=tmp_path)
    test = default_settings(ApplicationProfile.TEST, project_root=tmp_path)

    assert desktop.enable_ui is True
    assert headless.enable_ui is False
    assert desktop.synthetic_only is False
    assert headless.synthetic_only is False
    assert demo.synthetic_only is True
    assert test.synthetic_only is True
    assert demo.allow_external_network is False
    assert test.allow_external_network is False
    assert demo.database_path.name == "amba_ai_demo.db"
    assert test.database_path.name == "amba_ai_test.db"


def test_paths_are_absolute_and_serialization_is_deterministic(tmp_path: Path) -> None:
    settings = default_settings(ApplicationProfile.TEST, project_root=tmp_path)

    assert settings.database_path.is_absolute()
    assert settings.knowledge_base_root.is_absolute()
    assert settings.configuration_root.is_absolute()
    assert settings.migrations_root.is_absolute()
    assert settings.to_canonical_json() == settings.to_canonical_json()


def test_path_overrides_accept_strings_and_normalize(tmp_path: Path) -> None:
    database_path = tmp_path / "custom" / "application.db"
    settings = default_settings(
        ApplicationProfile.TEST,
        project_root=tmp_path,
        overrides={"database_path": str(database_path)},
    )

    assert settings.database_path == database_path.resolve(strict=False)


def test_unknown_and_invalid_overrides_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown application setting"):
        default_settings(
            ApplicationProfile.TEST,
            project_root=tmp_path,
            overrides={"unknown": True},
        )

    with pytest.raises(TypeError, match="override names must be strings"):
        default_settings(
            ApplicationProfile.TEST,
            project_root=tmp_path,
            overrides={1: True},  # type: ignore[dict-item]
        )

    with pytest.raises(TypeError, match="strict Boolean"):
        default_settings(
            ApplicationProfile.TEST,
            project_root=tmp_path,
            overrides={"strict_governance": 1},
        )


def test_profile_cannot_be_changed_by_override(tmp_path: Path) -> None:
    settings = default_settings(ApplicationProfile.TEST, project_root=tmp_path)

    with pytest.raises(ValueError, match="profile cannot be changed"):
        settings.with_overrides(profile=ApplicationProfile.DEMO)


def test_profile_invariants_fail_closed(tmp_path: Path) -> None:
    base = default_settings(ApplicationProfile.TEST, project_root=tmp_path)

    with pytest.raises(ValueError, match="synthetic-only"):
        base.with_overrides(synthetic_only=False)

    with pytest.raises(ValueError, match="external network"):
        base.with_overrides(allow_external_network=True)

    desktop = default_settings(ApplicationProfile.DESKTOP, project_root=tmp_path)
    with pytest.raises(ValueError, match="must enable the UI"):
        desktop.with_overrides(enable_ui=False)


def test_project_root_validation() -> None:
    with pytest.raises(TypeError, match="path or string"):
        default_settings(
            ApplicationProfile.TEST,
            project_root=object(),  # type: ignore[arg-type]
        )

    with pytest.raises(ValueError, match="must not be empty"):
        default_settings(ApplicationProfile.TEST, project_root=" ")


def test_application_settings_rejects_relative_paths(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="absolute path"):
        ApplicationSettings(
            profile=ApplicationProfile.TEST,
            database_path=Path("relative.db"),
            knowledge_base_root=tmp_path / "kb",
            configuration_root=tmp_path / "config",
            migrations_root=tmp_path / "migrations",
            synthetic_only=True,
        )
