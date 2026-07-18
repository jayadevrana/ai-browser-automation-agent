from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ActionType = Literal[
    "open_url",
    "click",
    "fill",
    "select",
    "wait",
    "scroll",
    "wait_for_user",
    "navigate",
    "press_key",
    "upload_file",
]

RunStatus = Literal[
    "planned",
    "running",
    "waiting_user",
    "failed",
    "completed",
    "aborted",
]

VALID_ACTIONS = {
    "open_url",
    "click",
    "fill",
    "select",
    "wait",
    "scroll",
    "wait_for_user",
    "navigate",
    "press_key",
    "upload_file",
}


@dataclass
class Action:
    action: ActionType
    selector: str | None = None
    value: str | None = None
    url: str | None = None
    ms: int | None = None
    key: str | None = None
    file_path: str | None = None
    message: str | None = None
    requires_confirmation: bool = False
    retries: int = 2

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Action":
        if not isinstance(data, dict):
            raise ValueError("Action must be a JSON object")

        action = data.get("action")
        if action not in VALID_ACTIONS:
            raise ValueError(f"Unsupported action: {action}")

        retries = int(data.get("retries", 2) or 0)

        obj = cls(
            action=action,
            selector=data.get("selector"),
            value=data.get("value"),
            url=data.get("url"),
            ms=int(data["ms"]) if data.get("ms") is not None else None,
            key=data.get("key"),
            file_path=data.get("file_path"),
            message=data.get("message"),
            requires_confirmation=bool(data.get("requires_confirmation", False)),
            retries=max(0, retries),
        )
        obj.validate()
        return obj

    def validate(self) -> None:
        if self.action in {"open_url", "navigate"} and not (self.url or self.value):
            raise ValueError(f"Action '{self.action}' requires 'url' or 'value'")

        if self.action in {"click", "fill", "select", "upload_file"} and not self.selector:
            raise ValueError(f"Action '{self.action}' requires 'selector'")

        if self.action == "fill" and self.value is None:
            raise ValueError("Action 'fill' requires 'value'")

        if self.action == "select" and self.value is None:
            raise ValueError("Action 'select' requires 'value'")

        if self.action == "press_key" and not (self.key or self.value):
            raise ValueError("Action 'press_key' requires 'key' or 'value'")

        if self.action == "upload_file" and not (self.file_path or self.value):
            raise ValueError("Action 'upload_file' requires 'file_path' or 'value'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "selector": self.selector,
            "value": self.value,
            "url": self.url,
            "ms": self.ms,
            "key": self.key,
            "file_path": self.file_path,
            "message": self.message,
            "requires_confirmation": self.requires_confirmation,
            "retries": self.retries,
        }


@dataclass
class Plan:
    goal: str
    steps: list[Action] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Plan":
        if not isinstance(data, dict):
            raise ValueError("Plan must be a JSON object")

        goal = str(data.get("goal", "")).strip()
        if not goal:
            raise ValueError("Plan requires non-empty 'goal'")

        raw_steps = data.get("steps")
        if not isinstance(raw_steps, list):
            raise ValueError("Plan requires 'steps' array")

        steps = [Action.from_dict(item) for item in raw_steps]
        metadata = data.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise ValueError("Plan 'metadata' must be a JSON object")

        return cls(goal=goal, steps=steps, metadata=metadata)

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "steps": [step.to_dict() for step in self.steps],
            "metadata": self.metadata,
        }
