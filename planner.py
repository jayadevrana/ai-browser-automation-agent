from __future__ import annotations

import json
import logging
import re
from typing import Any

from openai import OpenAI

from models import Plan


class Planner:
    def __init__(self, api_key: str, model: str = "gpt-4.1-mini", logger: logging.Logger | None = None) -> None:
        self.api_key = api_key.strip()
        self.model = model.strip() or "gpt-4.1-mini"
        self.logger = logger or logging.getLogger(__name__)
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None

    def plan_goal(self, goal: str) -> Plan:
        if not goal.strip():
            raise ValueError("Goal cannot be empty")

        if self.client is None:
            self.logger.warning("OPENAI_API_KEY not provided. Using fallback plan.")
            return self._fallback_plan(goal)

        messages = [
            {
                "role": "system",
                "content": self._system_prompt(),
            },
            {
                "role": "user",
                "content": (
                    "Generate a browser automation plan for this goal.\n"
                    f"Goal: {goal}\n"
                    "Return only valid JSON."
                ),
            },
        ]

        response_text = self._call_llm(messages)
        return self._parse_plan(response_text)

    def recover_plan(
        self,
        goal: str,
        remaining_steps: list[dict[str, Any]],
        error: str,
        page_context: dict[str, Any],
    ) -> Plan:
        if self.client is None:
            self.logger.warning("No OpenAI client available. Using fallback recovery plan.")
            return self._fallback_recovery_plan(goal, error)

        context_json = json.dumps(page_context, ensure_ascii=True)
        remaining_json = json.dumps(remaining_steps, ensure_ascii=True)

        messages = [
            {
                "role": "system",
                "content": self._system_prompt(recovery=True),
            },
            {
                "role": "user",
                "content": (
                    "A step failed during execution. Recover with a revised next-step plan.\n"
                    f"Goal: {goal}\n"
                    f"Error: {error}\n"
                    f"Remaining steps: {remaining_json}\n"
                    f"Live page context: {context_json}\n"
                    "Return only valid JSON."
                ),
            },
        ]

        response_text = self._call_llm(messages)
        return self._parse_plan(response_text)

    def _call_llm(self, messages: list[dict[str, str]]) -> str:
        assert self.client is not None
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=messages,
            max_tokens=1800,
        )
        content = response.choices[0].message.content or ""
        return content.strip()

    def _parse_plan(self, raw: str) -> Plan:
        cleaned = self._extract_json(raw)
        data = json.loads(cleaned)
        return Plan.from_dict(data)

    def _extract_json(self, text: str) -> str:
        text = text.strip()

        code_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL)
        if code_match:
            return code_match.group(1).strip()

        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("LLM response did not contain JSON object")
        return text[start : end + 1]

    def _fallback_plan(self, goal: str) -> Plan:
        lower_goal = goal.lower()
        if "oracle" in lower_goal and "rdp" in lower_goal:
            steps: list[dict[str, Any]] = [
                {"action": "open_url", "url": "https://www.oracle.com/cloud/free/", "retries": 1},
                {"action": "click", "selector": "text=Start for free", "retries": 1},
                {
                    "action": "wait_for_user",
                    "message": "Complete sign-up, CAPTCHA, email/phone verification, and payment verification. Press ENTER when the Oracle dashboard is ready.",
                    "requires_confirmation": True,
                },
                {
                    "action": "wait_for_user",
                    "message": "Create and configure the VM manually if selectors do not match. Press ENTER when done.",
                    "requires_confirmation": True,
                },
            ]
        elif "hostinger" in lower_goal and "domain" in lower_goal:
            steps = [
                {"action": "open_url", "url": "https://www.hostinger.com", "retries": 1},
                {"action": "wait_for_user", "message": "Search and select the domain. Press ENTER to continue."},
                {"action": "wait_for_user", "message": "Complete login and payment verification. Press ENTER when purchase is complete."},
            ]
        else:
            steps = [
                {
                    "action": "wait_for_user",
                    "message": (
                        "OpenAI API key not configured. Perform the task manually in browser and press ENTER."
                    ),
                    "requires_confirmation": True,
                }
            ]

        return Plan.from_dict(
            {
                "goal": goal,
                "steps": steps,
                "metadata": {"source": "fallback"},
            }
        )

    def _fallback_recovery_plan(self, goal: str, error: str) -> Plan:
        return Plan.from_dict(
            {
                "goal": goal,
                "steps": [
                    {
                        "action": "wait_for_user",
                        "message": (
                            f"Automation stopped due to error: {error}. Resolve manually and press ENTER to continue."
                        ),
                        "requires_confirmation": True,
                    }
                ],
                "metadata": {"source": "fallback_recovery"},
            }
        )

    def _system_prompt(self, recovery: bool = False) -> str:
        mode = "recovery" if recovery else "planning"
        return (
            "You are a browser automation planner. "
            f"Mode: {mode}. "
            "Output strictly one JSON object with keys: goal, steps, metadata. "
            "Allowed action values: open_url, click, fill, select, wait, scroll, wait_for_user, navigate, press_key, upload_file. "
            "For click/fill/select/upload_file include selector. "
            "For open_url/navigate include url. "
            "For fill/select include value. "
            "For wait include ms. "
            "For press_key include key. "
            "For upload_file include file_path. "
            "Use wait_for_user for captcha/otp/email verification/payment/login checkpoints. "
            "Never propose bypassing captcha, payment checks, or website security. "
            "Keep steps concise and executable with CSS selectors or text selectors. "
            "Always set retries as an integer where appropriate."
        )
