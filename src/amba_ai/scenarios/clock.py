from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import threading
from typing import Protocol, runtime_checkable

from amba_ai.scenarios.models import (
    ScenarioConfigurationError,
    ScenarioStage,
    require_timestamp,
)


@dataclass(frozen=True, slots=True)
class ScenarioClockSnapshot:
    stage: ScenarioStage
    timestamp: str

    def __post_init__(self) -> None:
        if not isinstance(self.stage, ScenarioStage):
            raise TypeError("stage must be a ScenarioStage")
        object.__setattr__(
            self,
            "timestamp",
            require_timestamp(self.timestamp, "timestamp"),
        )


@runtime_checkable
class ScenarioClockProtocol(Protocol):
    def now_iso(self) -> str:
        ...

    @property
    def stage(self) -> ScenarioStage:
        ...

    def snapshot(self) -> ScenarioClockSnapshot:
        ...


class DeterministicScenarioClock:
    def __init__(self, *, initial_time: str, initial_stage: ScenarioStage = ScenarioStage.STAGE_1) -> None:
        self._current = self._parse(initial_time)
        if not isinstance(initial_stage, ScenarioStage):
            raise TypeError("initial_stage must be a ScenarioStage")
        self._stage = initial_stage
        self._lock = threading.RLock()

    @staticmethod
    def _parse(value: object) -> datetime:
        return datetime.fromisoformat(
            require_timestamp(value, "timestamp")
        )

    @property
    def stage(self) -> ScenarioStage:
        with self._lock:
            return self._stage

    def now_iso(self) -> str:
        with self._lock:
            return self._current.isoformat()

    def snapshot(self) -> ScenarioClockSnapshot:
        with self._lock:
            return ScenarioClockSnapshot(
                stage=self._stage,
                timestamp=self._current.isoformat(),
            )

    def advance_time(self, duration: timedelta) -> str:
        if not isinstance(duration, timedelta):
            raise TypeError("duration must be a timedelta")
        if duration.total_seconds() <= 0:
            raise ScenarioConfigurationError("duration must be positive")
        with self._lock:
            self._current += duration
            return self._current.isoformat()

    def advance_stage(self, stage: ScenarioStage, *, at_time: str | None = None) -> ScenarioStage:
        if not isinstance(stage, ScenarioStage):
            raise TypeError("stage must be a ScenarioStage")
        with self._lock:
            if int(stage) != int(self._stage) + 1:
                raise ScenarioConfigurationError("scenario stages must advance exactly one step")
            if at_time is not None:
                candidate = self._parse(at_time)
                if candidate < self._current:
                    raise ScenarioConfigurationError("scenario time must not move backward")
                self._current = candidate
            self._stage = stage
            return self._stage
