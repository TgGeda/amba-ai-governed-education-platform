from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from enum import Enum
from pathlib import Path
from typing import Any

from amba_ai.governance.models import to_canonical_json


class ApplicationProfile(str, Enum):
    DESKTOP = "desktop"
    HEADLESS = "headless"
    DEMO = "demo"
    TEST = "test"


_PATH_FIELDS = frozenset(
    {
        "database_path",
        "knowledge_base_root",
        "configuration_root",
        "migrations_root",
    }
)
_BOOLEAN_FIELDS = frozenset(
    {
        "strict_governance",
        "initialize_database",
        "verify_knowledge_base",
        "enable_ui",
        "allow_external_network",
        "synthetic_only",
    }
)


@dataclass(frozen=True, slots=True)
class ApplicationSettings:
    profile: ApplicationProfile
    database_path: Path
    knowledge_base_root: Path
    configuration_root: Path
    migrations_root: Path
    strict_governance: bool = True
    initialize_database: bool = True
    verify_knowledge_base: bool = True
    enable_ui: bool = False
    allow_external_network: bool = False
    synthetic_only: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.profile, ApplicationProfile):
            raise TypeError("profile must be an ApplicationProfile")

        for field_name in _PATH_FIELDS:
            value = getattr(self, field_name)
            if not isinstance(value, Path):
                raise TypeError(f"{field_name} must be a pathlib.Path")
            if not value.is_absolute():
                raise ValueError(f"{field_name} must be an absolute path")
            object.__setattr__(
                self,
                field_name,
                value.resolve(strict=False),
            )

        for field_name in _BOOLEAN_FIELDS:
            if type(getattr(self, field_name)) is not bool:
                raise TypeError(f"{field_name} must be a strict Boolean")

        if self.profile in {
            ApplicationProfile.DEMO,
            ApplicationProfile.TEST,
        }:
            if not self.synthetic_only:
                raise ValueError(
                    f"{self.profile.value} profile must be synthetic-only"
                )
            if self.allow_external_network:
                raise ValueError(
                    f"{self.profile.value} profile cannot allow external network access"
                )

        if self.profile is ApplicationProfile.DESKTOP:
            if not self.enable_ui:
                raise ValueError("desktop profile must enable the UI")
        elif self.enable_ui:
            raise ValueError("only the desktop profile may enable the UI")

    def with_overrides(self, **changes: object) -> ApplicationSettings:
        normalized = _normalize_overrides(changes)
        if "profile" in normalized and normalized["profile"] is not self.profile:
            raise ValueError("profile cannot be changed through overrides")
        return replace(self, **normalized)

    def to_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile.value,
            "database_path": self.database_path.as_posix(),
            "knowledge_base_root": self.knowledge_base_root.as_posix(),
            "configuration_root": self.configuration_root.as_posix(),
            "migrations_root": self.migrations_root.as_posix(),
            "strict_governance": self.strict_governance,
            "initialize_database": self.initialize_database,
            "verify_knowledge_base": self.verify_knowledge_base,
            "enable_ui": self.enable_ui,
            "allow_external_network": self.allow_external_network,
            "synthetic_only": self.synthetic_only,
        }

    def to_canonical_json(self) -> str:
        return to_canonical_json(self.to_dict())


def _require_project_root(value: Path | str) -> Path:
    if not isinstance(value, (Path, str)):
        raise TypeError("project_root must be a path or string")

    if isinstance(value, str) and not value.strip():
        raise ValueError("project_root must not be empty")

    return Path(value).expanduser().resolve(strict=False)


def _normalize_overrides(
    overrides: Mapping[str, object],
) -> dict[str, object]:
    if not isinstance(overrides, Mapping):
        raise TypeError("overrides must be a mapping")

    allowed_fields = {field.name for field in fields(ApplicationSettings)}
    normalized: dict[str, object] = {}

    for raw_name, value in overrides.items():
        if not isinstance(raw_name, str):
            raise TypeError("override names must be strings")

        name = raw_name.strip()
        if not name:
            raise ValueError("override names must not be empty")
        if name not in allowed_fields:
            raise ValueError(f"unknown application setting: {name}")
        if name in normalized:
            raise ValueError(f"duplicate application setting override: {name}")

        if name in _PATH_FIELDS:
            if not isinstance(value, (Path, str)):
                raise TypeError(f"{name} override must be a path or string")
            if isinstance(value, str) and not value.strip():
                raise ValueError(f"{name} override must not be empty")
            normalized[name] = Path(value).expanduser().resolve(strict=False)
        else:
            normalized[name] = value

    return normalized


def default_settings(
    profile: ApplicationProfile,
    *,
    project_root: Path | str = Path("."),
    overrides: Mapping[str, object] | None = None,
) -> ApplicationSettings:
    if not isinstance(profile, ApplicationProfile):
        raise TypeError("profile must be an ApplicationProfile")

    root = _require_project_root(project_root)

    if profile is ApplicationProfile.TEST:
        database_path = root / "build" / "test" / "amba_ai_test.db"
    elif profile is ApplicationProfile.DEMO:
        database_path = root / "build" / "demo" / "amba_ai_demo.db"
    else:
        database_path = root / "data" / "amba_ai.db"

    settings = ApplicationSettings(
        profile=profile,
        database_path=database_path,
        knowledge_base_root=root / "kb",
        configuration_root=root / "config",
        migrations_root=root / "src" / "amba_ai" / "db" / "migrations",
        strict_governance=True,
        initialize_database=True,
        verify_knowledge_base=True,
        enable_ui=profile is ApplicationProfile.DESKTOP,
        allow_external_network=False,
        synthetic_only=profile in {
            ApplicationProfile.DEMO,
            ApplicationProfile.TEST,
        },
    )

    if overrides is None:
        return settings

    return settings.with_overrides(**_normalize_overrides(overrides))
