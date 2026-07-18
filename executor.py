from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

from models import Action, Plan, RunStatus
from security import is_sensitive_action, sanitize_action_payload, upload_requires_manual_approval
from state_manager import StateManager

if TYPE_CHECKING:
    from browser_controller import BrowserController
    from planner import Planner


class Executor:
    def __init__(
        self,
        browser_controller: "BrowserController",
        state_manager: StateManager,
        planner: "Planner",
        logger: logging.Logger,
        workspace_root: Path,
    ) -> None:
        self.browser_controller = browser_controller
        self.state_manager = state_manager
        self.planner = planner
        self.logger = logger
        self.workspace_root = workspace_root

    def run(self, run_id: str, plan: Plan, start_step: int = 0) -> RunStatus:
        step_idx = start_step
        self.browser_controller.start()
        self.state_manager.update_progress(run_id, start_step, "running", plan=plan)

        try:
            while step_idx < len(plan.steps):
                step = plan.steps[step_idx]

                try:
                    page_context = self.browser_controller.capture_context()
                except Exception:
                    page_context = {}

                self.state_manager.append_event(
                    run_id,
                    "step_started",
                    {
                        "step_idx": step_idx,
                        "step": sanitize_action_payload(step),
                        "page_context": page_context,
                    },
                    step_idx=step_idx,
                )

                if step.action == "wait_for_user":
                    message = step.message or "Human action required. Complete task then press ENTER to continue."
                    self.state_manager.update_progress(run_id, step_idx, "waiting_user", plan=plan)
                    print(f"\nHuman action required: {message}")
                    input("Press ENTER when done...")
                    self.state_manager.append_event(
                        run_id,
                        "human_action_completed",
                        {"step_idx": step_idx, "message": message},
                        step_idx=step_idx,
                    )
                    self.state_manager.update_progress(run_id, step_idx, "running", plan=plan)
                    step_idx += 1
                    continue

                if is_sensitive_action(step):
                    if not self._confirm_sensitive_step(step):
                        self.state_manager.update_progress(run_id, step_idx, "aborted", plan=plan)
                        self.state_manager.append_event(
                            run_id,
                            "run_aborted",
                            {"reason": "user_rejected_sensitive_step", "step_idx": step_idx},
                            step_idx=step_idx,
                        )
                        return "aborted"

                attempts = max(1, step.retries + 1)
                last_error: Exception | None = None

                for attempt in range(1, attempts + 1):
                    try:
                        self.execute_step(step, step_idx)
                        last_error = None
                        break
                    except Exception as exc:  # noqa: BLE001
                        last_error = exc
                        self.logger.warning(
                            "Step %s failed on attempt %s/%s: %s",
                            step_idx,
                            attempt,
                            attempts,
                            exc,
                        )
                        self.state_manager.append_event(
                            run_id,
                            "step_attempt_failed",
                            {
                                "step_idx": step_idx,
                                "attempt": attempt,
                                "attempts": attempts,
                                "error": str(exc),
                            },
                            step_idx=step_idx,
                        )
                        if attempt < attempts:
                            time.sleep(1)

                if last_error is None:
                    self.state_manager.update_progress(run_id, step_idx + 1, "running", plan=plan)
                    self.state_manager.append_event(
                        run_id,
                        "step_completed",
                        {"step_idx": step_idx},
                        step_idx=step_idx,
                    )
                    step_idx += 1
                    continue

                error_text = str(last_error)
                try:
                    artifacts = self.browser_controller.capture_artifacts(run_id, step_idx)
                except Exception as artifact_error:  # noqa: BLE001
                    artifacts = {"capture_error": str(artifact_error)}

                try:
                    context = self.browser_controller.capture_context()
                except Exception:
                    context = {}

                self.state_manager.append_event(
                    run_id,
                    "step_failed",
                    {
                        "step_idx": step_idx,
                        "error": error_text,
                        "artifacts": artifacts,
                    },
                    step_idx=step_idx,
                )

                remaining_steps = [item.to_dict() for item in plan.steps[step_idx:]]
                try:
                    recovered = self.planner.recover_plan(
                        goal=plan.goal,
                        remaining_steps=remaining_steps,
                        error=error_text,
                        page_context={"page": context, "artifacts": artifacts},
                    )
                except Exception as recovery_error:  # noqa: BLE001
                    self.logger.error("Recovery planning failed: %s", recovery_error)
                    self.state_manager.update_progress(
                        run_id,
                        step_idx,
                        "failed",
                        last_error=f"{error_text}; recovery_failed={recovery_error}",
                        plan=plan,
                    )
                    return "failed"

                plan = Plan(
                    goal=plan.goal,
                    steps=plan.steps[:step_idx] + recovered.steps,
                    metadata={
                        **plan.metadata,
                        "recovered": True,
                        "last_error": error_text,
                    },
                )
                self.state_manager.update_progress(
                    run_id,
                    step_idx,
                    "running",
                    last_error=error_text,
                    plan=plan,
                )
                self.state_manager.append_event(
                    run_id,
                    "recovery_applied",
                    {
                        "step_idx": step_idx,
                        "new_remaining_steps": len(recovered.steps),
                    },
                    step_idx=step_idx,
                )

            self.state_manager.update_progress(run_id, len(plan.steps), "completed", plan=plan)
            self.state_manager.append_event(
                run_id,
                "run_completed",
                {"total_steps": len(plan.steps)},
            )
            return "completed"

        except KeyboardInterrupt:
            self.logger.warning("Interrupted by user. Run can be resumed later.")
            self.state_manager.update_progress(run_id, step_idx, "waiting_user", plan=plan)
            self.state_manager.append_event(
                run_id,
                "run_interrupted",
                {"step_idx": step_idx},
                step_idx=step_idx,
            )
            return "waiting_user"
        finally:
            self.browser_controller.stop()

    def execute_step(self, step: Action, step_idx: int) -> None:
        page = self.browser_controller.get_page()

        if step.action in {"open_url", "navigate"}:
            url = step.url or step.value
            if not url:
                raise ValueError(f"Step {step_idx} requires URL")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            return

        if step.action == "click":
            page.locator(step.selector).first.click(timeout=12000)
            return

        if step.action == "fill":
            page.locator(step.selector).first.fill(step.value or "", timeout=12000)
            return

        if step.action == "select":
            page.locator(step.selector).first.select_option(step.value or "", timeout=12000)
            return

        if step.action == "wait":
            page.wait_for_timeout(step.ms or 1000)
            return

        if step.action == "scroll":
            amount = int(step.value) if step.value and str(step.value).lstrip("-").isdigit() else 1200
            page.mouse.wheel(0, amount)
            return

        if step.action == "press_key":
            key = step.key or step.value
            if not key:
                raise ValueError(f"Step {step_idx} requires keyboard key")
            page.keyboard.press(key)
            return

        if step.action == "upload_file":
            file_path = step.file_path or step.value
            if not file_path:
                raise ValueError(f"Step {step_idx} requires file_path")

            path_obj = Path(file_path).expanduser().resolve()
            if not path_obj.exists():
                raise FileNotFoundError(f"File not found for upload: {path_obj}")

            if upload_requires_manual_approval(str(path_obj), self.workspace_root):
                print(f"\nUpload path is outside workspace: {path_obj}")
                allowed = input("Type YES to allow this upload: ").strip().upper() == "YES"
                if not allowed:
                    raise PermissionError("Upload blocked by user")

            page.locator(step.selector).first.set_input_files(str(path_obj), timeout=12000)
            return

        if step.action == "wait_for_user":
            message = step.message or "Human action required."
            print(f"Human action required: {message}")
            input("Press ENTER when done...")
            return

        raise ValueError(f"Unsupported action type: {step.action}")

    def _confirm_sensitive_step(self, step: Action) -> bool:
        print("\nSensitive action requires confirmation.")
        print(f"Action: {step.action}")
        if step.selector:
            print(f"Selector: {step.selector}")
        if step.url:
            print(f"URL: {step.url}")
        if step.message:
            print(f"Message: {step.message}")

        answer = input("Type YES to continue this step: ").strip().upper()
        return answer == "YES"
