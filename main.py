from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from browser_controller import BrowserController
from executor import Executor
from logger import setup_logger
from models import Plan
from planner import Planner
from security import read_openai_api_key
from state_manager import StateManager


def prompt_goal() -> str:
    while True:
        goal = input("Enter your goal: ").strip()
        if goal:
            return goal
        print("Goal cannot be empty.")


def prompt_resume() -> bool:
    answer = input("Resume this run? (y/N): ").strip().lower()
    return answer in {"y", "yes"}


def env_to_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def default_chrome_user_data_dir() -> Path:
    if os.name == "nt":
        local_app_data = os.getenv("LOCALAPPDATA", "")
        return Path(local_app_data) / "Google" / "Chrome" / "User Data"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
    return Path.home() / ".config" / "google-chrome"


def bootstrap_planner() -> Planner:
    api_key = read_openai_api_key()
    if not api_key:
        if sys.stdin.isatty():
            api_key = getpass.getpass(
                "OPENAI_API_KEY not found. Enter API key (input hidden, not stored, press ENTER to skip): "
            ).strip()
        else:
            print("OPENAI_API_KEY not found. Continuing with fallback planning mode.")

    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini"
    return Planner(api_key=api_key, model=model)


def main() -> int:
    project_root = Path(__file__).resolve().parent
    load_dotenv(project_root / ".env")

    bootstrap_logger = setup_logger()
    state_manager = StateManager(project_root / "agent_state.db")
    planner = bootstrap_planner()

    run_id: str
    plan: Plan
    start_step: int

    resumable = state_manager.get_latest_resumable_run()
    if resumable:
        print("Found resumable run:")
        print(f"Run ID: {resumable['run_id']}")
        print(f"Goal: {resumable['goal']}")
        print(f"Status: {resumable['status']}")
        print(f"Current step index: {resumable['current_step']}")

        if prompt_resume():
            run_id = resumable["run_id"]
            plan = Plan.from_dict(resumable["plan_json"])
            start_step = int(resumable["current_step"])
        else:
            goal = prompt_goal()
            plan = planner.plan_goal(goal)
            run_id = state_manager.create_run(goal, plan)
            start_step = 0
    else:
        goal = prompt_goal()
        plan = planner.plan_goal(goal)
        run_id = state_manager.create_run(goal, plan)
        start_step = 0

    logger = setup_logger(run_id=run_id)
    planner.logger = logger

    logger.info("Starting run %s", run_id)
    logger.info("Goal: %s", plan.goal)
    logger.info("Steps planned: %s", len(plan.steps))

    state_manager.append_event(
        run_id,
        "run_started",
        {
            "goal": plan.goal,
            "start_step": start_step,
            "planned_steps": len(plan.steps),
        },
        step_idx=start_step,
    )

    use_chrome_profile = env_to_bool("USE_CHROME_PROFILE", default=False)
    profile_directory = os.getenv("CHROME_PROFILE_DIR", "Default").strip() or None
    browser_channel = os.getenv("BROWSER_CHANNEL", "").strip()
    if not browser_channel:
        browser_channel = "chrome" if use_chrome_profile else "chromium"

    persistent_user_data_dir: Path | None = None
    if use_chrome_profile:
        configured = os.getenv("CHROME_USER_DATA_DIR", "").strip()
        persistent_user_data_dir = Path(os.path.expanduser(configured)) if configured else default_chrome_user_data_dir()
        logger.info("Using Chrome profile mode with user data dir: %s", persistent_user_data_dir)
        logger.info("If Chrome profile is locked, close Chrome and retry.")

    browser_controller = BrowserController(
        headless=False,
        browser_channel=browser_channel,
        persistent_user_data_dir=persistent_user_data_dir,
        profile_directory=profile_directory if use_chrome_profile else None,
    )
    executor = Executor(
        browser_controller=browser_controller,
        state_manager=state_manager,
        planner=planner,
        logger=logger,
        workspace_root=project_root,
    )

    try:
        status = executor.run(run_id=run_id, plan=plan, start_step=start_step)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Fatal error: %s", exc)
        state_manager.update_progress(run_id, start_step, "failed", last_error=str(exc), plan=plan)
        state_manager.append_event(
            run_id,
            "run_failed",
            {
                "error": str(exc),
            },
            step_idx=start_step,
        )
        print("Run failed.")
        return 1

    print(f"Run finished with status: {status}")
    logger.info("Run finished with status: %s", status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
