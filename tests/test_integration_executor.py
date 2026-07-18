from __future__ import annotations

import logging
from pathlib import Path

import pytest

from executor import Executor
from models import Plan
from state_manager import StateManager


class FakeMouse:
    def __init__(self) -> None:
        self.last_scroll = 0

    def wheel(self, _x: int, y: int) -> None:
        self.last_scroll = y


class FakeKeyboard:
    def __init__(self) -> None:
        self.last_key: str | None = None

    def press(self, key: str) -> None:
        self.last_key = key


class FakeLocator:
    def __init__(self, page: "FakePage", selector: str) -> None:
        self.page = page
        self.selector = selector

    @property
    def first(self) -> "FakeLocator":
        return self

    def _maybe_fail(self) -> None:
        if self.selector in self.page.fail_selectors:
            raise RuntimeError(f"Selector not found: {self.selector}")

    def click(self, timeout: int = 0) -> None:  # noqa: ARG002
        self._maybe_fail()
        self.page.clicked.append(self.selector)

    def fill(self, value: str, timeout: int = 0) -> None:  # noqa: ARG002
        self._maybe_fail()
        self.page.filled[self.selector] = value

    def select_option(self, value: str, timeout: int = 0) -> None:  # noqa: ARG002
        self._maybe_fail()
        self.page.selected[self.selector] = value

    def set_input_files(self, value: str, timeout: int = 0) -> None:  # noqa: ARG002
        self._maybe_fail()
        self.page.uploaded[self.selector] = value


class FakePage:
    def __init__(self, fail_selectors: set[str] | None = None) -> None:
        self.fail_selectors = fail_selectors or set()
        self.current_url = "about:blank"
        self.clicked: list[str] = []
        self.filled: dict[str, str] = {}
        self.selected: dict[str, str] = {}
        self.uploaded: dict[str, str] = {}
        self.waited_ms: list[int] = []
        self.mouse = FakeMouse()
        self.keyboard = FakeKeyboard()

    def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 0) -> None:  # noqa: ARG002
        self.current_url = url

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(self, selector)

    def wait_for_timeout(self, ms: int) -> None:
        self.waited_ms.append(ms)


class FakeBrowserController:
    def __init__(self, page: FakePage) -> None:
        self.page = page
        self.started = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.started = False

    def get_page(self) -> FakePage:
        return self.page

    def capture_context(self) -> dict:
        return {
            "url": self.page.current_url,
            "title": "Fake",
            "buttons": ["Next"],
            "inputs": [],
            "links": [],
            "body_excerpt": "fake page",
        }

    def capture_artifacts(self, run_id: str, step_idx: int) -> dict:
        return {
            "run_id": run_id,
            "step_idx": step_idx,
            "screenshot": "fake.png",
            "html": "fake.html",
            "context": "fake.json",
        }


class FakePlanner:
    def __init__(self) -> None:
        self.calls = 0

    def recover_plan(self, goal: str, remaining_steps: list[dict], error: str, page_context: dict) -> Plan:  # noqa: ARG002
        self.calls += 1
        return Plan.from_dict(
            {
                "goal": goal,
                "steps": [{"action": "click", "selector": "#done", "retries": 0}],
                "metadata": {"source": "recovery"},
            }
        )


@pytest.fixture
def test_logger() -> logging.Logger:
    logger = logging.getLogger("test_executor")
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


def test_local_flow_open_fill_click_wait_for_user(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    test_logger: logging.Logger,
) -> None:
    state = StateManager(tmp_path / "state.db")
    page = FakePage()
    browser = FakeBrowserController(page)
    planner = FakePlanner()

    executor = Executor(
        browser_controller=browser,
        state_manager=state,
        planner=planner,
        logger=test_logger,
        workspace_root=tmp_path,
    )

    plan = Plan.from_dict(
        {
            "goal": "Sign up",
            "steps": [
                {"action": "open_url", "url": "https://example.com"},
                {"action": "fill", "selector": "#email", "value": "a@b.com"},
                {"action": "click", "selector": "#next"},
                {"action": "wait_for_user", "message": "Complete CAPTCHA"},
            ],
        }
    )
    run_id = state.create_run(plan.goal, plan)

    monkeypatch.setattr("builtins.input", lambda _msg="": "")

    status = executor.run(run_id, plan, start_step=0)
    assert status == "completed"
    assert page.current_url == "https://example.com"
    assert page.filled["#email"] == "a@b.com"
    assert "#next" in page.clicked


def test_failure_recovery_replans_when_selector_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    test_logger: logging.Logger,
) -> None:
    state = StateManager(tmp_path / "state.db")
    page = FakePage(fail_selectors={"#missing"})
    browser = FakeBrowserController(page)
    planner = FakePlanner()

    executor = Executor(
        browser_controller=browser,
        state_manager=state,
        planner=planner,
        logger=test_logger,
        workspace_root=tmp_path,
    )

    plan = Plan.from_dict(
        {
            "goal": "Recover from missing selector",
            "steps": [
                {"action": "click", "selector": "#missing", "retries": 0},
                {"action": "click", "selector": "#will-not-run", "retries": 0},
            ],
        }
    )
    run_id = state.create_run(plan.goal, plan)

    monkeypatch.setattr("builtins.input", lambda _msg="": "")

    status = executor.run(run_id, plan, start_step=0)
    assert status == "completed"
    assert planner.calls == 1
    assert "#done" in page.clicked


def test_pause_and_resume_after_keyboard_interrupt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    test_logger: logging.Logger,
) -> None:
    state = StateManager(tmp_path / "state.db")
    page = FakePage()
    browser = FakeBrowserController(page)
    planner = FakePlanner()

    executor = Executor(
        browser_controller=browser,
        state_manager=state,
        planner=planner,
        logger=test_logger,
        workspace_root=tmp_path,
    )

    plan = Plan.from_dict(
        {
            "goal": "Pause and resume",
            "steps": [
                {"action": "wait_for_user", "message": "Do manual step"},
                {"action": "click", "selector": "#done"},
            ],
        }
    )
    run_id = state.create_run(plan.goal, plan)

    def raise_interrupt(_msg: str = "") -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", raise_interrupt)
    first_status = executor.run(run_id, plan, start_step=0)
    assert first_status == "waiting_user"

    resumable = state.get_latest_resumable_run()
    assert resumable is not None
    assert resumable["run_id"] == run_id
    assert resumable["current_step"] == 0

    monkeypatch.setattr("builtins.input", lambda _msg="": "")
    resumed_plan = Plan.from_dict(resumable["plan_json"])
    second_status = executor.run(run_id, resumed_plan, start_step=resumable["current_step"])

    assert second_status == "completed"
    assert "#done" in page.clicked
