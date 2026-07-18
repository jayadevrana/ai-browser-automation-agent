from __future__ import annotations

import pytest

from models import Plan


def test_plan_validation_accepts_valid_actions() -> None:
    plan = Plan.from_dict(
        {
            "goal": "Sign up for service",
            "steps": [
                {"action": "open_url", "url": "https://example.com"},
                {"action": "click", "selector": "text=Start", "retries": 1},
            ],
            "metadata": {"source": "test"},
        }
    )

    assert plan.goal == "Sign up for service"
    assert len(plan.steps) == 2
    assert plan.steps[0].action == "open_url"


def test_plan_validation_rejects_unknown_action() -> None:
    with pytest.raises(ValueError, match="Unsupported action"):
        Plan.from_dict(
            {
                "goal": "Bad plan",
                "steps": [
                    {"action": "drag_and_drop", "selector": "#a", "value": "#b"},
                ],
            }
        )
