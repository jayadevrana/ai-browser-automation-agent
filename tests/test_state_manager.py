from __future__ import annotations

from pathlib import Path

from models import Plan
from state_manager import StateManager


def test_state_resume_returns_latest_waiting_run(tmp_path: Path) -> None:
    manager = StateManager(tmp_path / "state.db")

    first_plan = Plan.from_dict(
        {
            "goal": "Goal 1",
            "steps": [{"action": "wait_for_user", "message": "step"}],
        }
    )
    second_plan = Plan.from_dict(
        {
            "goal": "Goal 2",
            "steps": [{"action": "wait_for_user", "message": "step"}],
        }
    )

    run1 = manager.create_run("Goal 1", first_plan)
    run2 = manager.create_run("Goal 2", second_plan)

    manager.update_progress(run1, step_idx=1, status="completed", plan=first_plan)
    manager.update_progress(run2, step_idx=0, status="waiting_user", plan=second_plan)

    resumable = manager.get_latest_resumable_run()
    assert resumable is not None
    assert resumable["run_id"] == run2
    assert resumable["status"] == "waiting_user"


def test_events_are_redacted_before_storage(tmp_path: Path) -> None:
    manager = StateManager(tmp_path / "state.db")
    plan = Plan.from_dict(
        {
            "goal": "Goal",
            "steps": [{"action": "wait_for_user", "message": "step"}],
        }
    )
    run_id = manager.create_run("Goal", plan)

    manager.append_event(
        run_id,
        "test",
        {"password": "hello", "otp": "123456", "safe": "ok"},
    )

    events = manager.load_events(run_id)
    assert events[0]["payload_json"]["password"] == "<REDACTED>"
    assert events[0]["payload_json"]["otp"] == "<REDACTED>"
    assert events[0]["payload_json"]["safe"] == "ok"
