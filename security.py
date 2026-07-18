from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from models import Action


SENSITIVE_FIELD_HINTS = {
    "password",
    "passcode",
    "otp",
    "2fa",
    "mfa",
    "cvv",
    "cvc",
    "card",
    "security code",
    "pin",
}

CRITICAL_ACTION_HINTS = {
    "submit",
    "checkout",
    "confirm",
    "purchase",
    "pay",
    "place order",
    "delete",
    "cancel subscription",
    "remove",
    "transfer",
}


def _normalize(value: str | None) -> str:
    return (value or "").strip().lower()


def looks_sensitive(text: str | None) -> bool:
    normalized = _normalize(text)
    if not normalized:
        return False

    if any(hint in normalized for hint in SENSITIVE_FIELD_HINTS):
        return True

    if re.search(r"\b\d{3,4}\b", normalized) and any(
        token in normalized for token in {"cvv", "cvc", "otp", "pin"}
    ):
        return True

    return False


def is_sensitive_action(action: Action) -> bool:
    haystack = " ".join(
        [
            _normalize(action.selector),
            _normalize(action.message),
            _normalize(action.value),
            _normalize(action.url),
        ]
    )

    if action.requires_confirmation:
        return True

    if action.action in {"click", "press_key", "select"}:
        return any(hint in haystack for hint in CRITICAL_ACTION_HINTS)

    if action.action == "fill" and looks_sensitive(action.selector):
        return True

    if action.action == "upload_file":
        return True

    return False


def should_redact_value(key: str | None, value: Any) -> bool:
    key_norm = _normalize(key)
    if key_norm and looks_sensitive(key_norm):
        return True

    if isinstance(value, str):
        if looks_sensitive(value):
            return True
        if re.search(r"\b(?:\d[ -]*?){13,19}\b", value):
            return True
    return False


def redact_sensitive_data(obj: Any, parent_key: str | None = None) -> Any:
    if isinstance(obj, dict):
        redacted: dict[str, Any] = {}
        for key, value in obj.items():
            if should_redact_value(key, value):
                redacted[key] = "<REDACTED>"
            else:
                redacted[key] = redact_sensitive_data(value, key)
        return redacted

    if isinstance(obj, list):
        return [redact_sensitive_data(item, parent_key) for item in obj]

    if should_redact_value(parent_key, obj):
        return "<REDACTED>"

    return obj


def upload_requires_manual_approval(file_path: str, workspace_root: Path) -> bool:
    try:
        absolute_file = Path(file_path).expanduser().resolve()
    except Exception:
        return True

    try:
        absolute_file.relative_to(workspace_root.resolve())
        return False
    except ValueError:
        return True


def sanitize_action_payload(action: Action) -> dict[str, Any]:
    payload = action.to_dict()

    if action.action == "fill" and looks_sensitive(action.selector):
        payload["value"] = "<REDACTED>"

    if action.action == "upload_file":
        payload["file_path"] = "<REDACTED_PATH>"
        payload["value"] = "<REDACTED_PATH>"

    return redact_sensitive_data(payload)


def read_openai_api_key() -> str:
    return os.getenv("OPENAI_API_KEY", "").strip()
