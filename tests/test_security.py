from __future__ import annotations

from models import Action
from security import is_sensitive_action, redact_sensitive_data


def test_sensitive_step_detection_for_payment_submit() -> None:
    action = Action.from_dict({"action": "click", "selector": "text=Pay and Confirm"})
    assert is_sensitive_action(action) is True


def test_sensitive_fill_detection_for_password() -> None:
    action = Action.from_dict(
        {
            "action": "fill",
            "selector": "#password",
            "value": "super-secret",
        }
    )
    assert is_sensitive_action(action) is True


def test_redaction_removes_secrets() -> None:
    data = {
        "username": "alice",
        "password": "mypassword",
        "nested": {"otp": "123456"},
        "card_number": "4242 4242 4242 4242",
    }
    redacted = redact_sensitive_data(data)

    assert redacted["username"] == "alice"
    assert redacted["password"] == "<REDACTED>"
    assert redacted["nested"]["otp"] == "<REDACTED>"
    assert redacted["card_number"] == "<REDACTED>"
