from __future__ import annotations

import json
import re
import html
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from PySide6.QtCore import QObject, Signal

from amba_ai.logger import logger


@dataclass(frozen=True)
class AgentCommand:
    action: str
    payload: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {"action": self.action, **self.payload}


class AgentBridge(QObject):
    ui_action_requested = Signal(dict)
    ui_action_rejected = Signal(dict)
    text_processed = Signal(str)

    def __init__(
        self,
        parent: Optional[QObject] = None,
        allowed_actions: Optional[Iterable[str]] = None,
        max_commands_per_message: int = 8,
        command_keys: Sequence[str] = ("action",),
    ) -> None:
        super().__init__(parent)
        # Validate allowed actions upfront
        self._allowed_actions = {a.strip() for a in (allowed_actions or ()) if isinstance(a, str) and a.strip()}
        self._max_commands = max(1, int(max_commands_per_message))
        self._command_keys = tuple(command_keys)

    def process_llm_output(self, text: Optional[str]) -> str:
        if not text:
            self.text_processed.emit("")
            return ""

        # Use robust HTML entity decoding
        normalized = html.unescape(str(text))
        blocks = self._extract_json_objects(normalized)

        commands: List[AgentCommand] = []
        removals: List[Tuple[int, int]] = []

        for raw, start, end in blocks:
            if len(commands) >= self._max_commands:
                break

            parsed = self._parse_json(raw)
            if parsed is None:
                logger.debug("Discarded malformed JSON block")
                continue

            command = self._build_command(parsed)
            if command is None:
                continue

            removals.append((start, end))

            if self._is_allowed(command.action):
                commands.append(command)
            else:
                rejected = command.to_dict()
                logger.warning("Rejected UI command: %s", rejected)
                self.ui_action_rejected.emit(rejected)

        cleaned = self._normalize_text(self._remove_ranges(normalized, removals))

        for command in commands:
            payload = command.to_dict()
            logger.debug("Emitting UI command: %s", payload)
            self.ui_action_requested.emit(payload)

        self.text_processed.emit(cleaned)
        return cleaned

    def set_allowed_actions(self, actions: Iterable[str]) -> None:
        self._allowed_actions = {str(a).strip() for a in actions if str(a).strip()}

    def allow_action(self, action: str) -> None:
        cleaned = str(action).strip()
        if cleaned:
            self._allowed_actions.add(cleaned)

    def disallow_action(self, action: str) -> None:
        self._allowed_actions.discard(str(action).strip())

    def clear_allowed_actions(self) -> None:
        self._allowed_actions.clear()

    def has_allowed_action_filter(self) -> bool:
        return bool(self._allowed_actions)

    def _is_allowed(self, action: str) -> bool:
        return not self._allowed_actions or action in self._allowed_actions

    def _build_command(self, payload: Mapping[str, Any]) -> Optional[AgentCommand]:
        action_key = None
        action_value = None

        for key in self._command_keys:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                action_key = key
                action_value = value.strip()
                break

        if not action_value:
            return None

        # Only keep JSON-safe values in payload
        clean_payload = {
            k: v for k, v in payload.items()
            if k != action_key and self._is_json_safe(v)
        }

        return AgentCommand(action=action_value, payload=clean_payload)

    @staticmethod
    def _is_json_safe(value: Any) -> bool:
        return isinstance(value, (str, int, float, bool, type(None)))

    @staticmethod
    def _parse_json(raw: str) -> Optional[Dict[str, Any]]:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    @classmethod
    def _extract_json_objects(cls, text: str) -> List[Tuple[str, int, int]]:
        results = []
        i = 0
        n = len(text)

        while i < n:
            if text[i] != "{":
                i += 1
                continue

            end = cls._find_matching_brace(text, i)
            if end is None:
                i += 1
                continue

            results.append((text[i:end + 1], i, end + 1))
            i = end + 1

        return results

    @staticmethod
    def _find_matching_brace(text: str, start: int) -> Optional[int]:
        depth = 0
        in_string = False
        escape = False

        for i in range(start, len(text)):
            c = text[i]

            if escape:
                escape = False
                continue

            if c == "\\":
                escape = True
                continue

            if c == '"':
                in_string = not in_string
                continue

            if in_string:
                continue

            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return i

        return None

    @staticmethod
    def _remove_ranges(text: str, ranges: Sequence[Tuple[int, int]]) -> str:
        if not ranges:
            return text

        merged: List[Tuple[int, int]] = []
        for start, end in sorted(ranges):
            if not merged or start > merged[-1][1]:
                merged.append((start, end))
            else:
                s, e = merged[-1]
                merged[-1] = (s, max(e, end))

        out: List[str] = []
        cursor = 0
        for start, end in merged:
            out.append(text[cursor:start])
            cursor = end
        out.append(text[cursor:])
        return "".join(out)

    @staticmethod
    def _normalize_text(text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        lines = [line.rstrip() for line in text.split("\n")]
        cleaned = "\n".join(lines).strip()
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
        return cleaned.strip()
