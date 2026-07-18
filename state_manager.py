from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models import Plan
from security import redact_sensitive_data


def utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class StateManager:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or (Path(__file__).resolve().parent / "agent_state.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    status TEXT NOT NULL,
                    current_step INTEGER NOT NULL,
                    plan_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_error TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    ts TEXT NOT NULL,
                    step_idx INTEGER,
                    event_type TEXT NOT NULL,
                    payload_json TEXT,
                    FOREIGN KEY(run_id) REFERENCES runs(run_id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_run_ts ON events(run_id, ts)"
            )

    def create_run(self, goal: str, plan: Plan) -> str:
        run_id = str(uuid.uuid4())
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (run_id, goal, status, current_step, plan_json, created_at, updated_at, last_error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    goal,
                    "planned",
                    0,
                    json.dumps(plan.to_dict()),
                    now,
                    now,
                    None,
                ),
            )
        return run_id

    def load_run(self, run_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Run not found: {run_id}")

        data = dict(row)
        data["plan_json"] = json.loads(data["plan_json"])
        return data

    def get_latest_resumable_run(self) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM runs
                WHERE status IN ('waiting_user', 'running')
                ORDER BY updated_at DESC
                LIMIT 1
                """
            ).fetchone()

        if row is None:
            return None

        data = dict(row)
        data["plan_json"] = json.loads(data["plan_json"])
        return data

    def update_progress(
        self,
        run_id: str,
        step_idx: int,
        status: str,
        last_error: str | None = None,
        plan: Plan | None = None,
    ) -> None:
        now = utc_now()
        with self._connect() as conn:
            if plan is None:
                conn.execute(
                    """
                    UPDATE runs
                    SET current_step = ?, status = ?, updated_at = ?, last_error = ?
                    WHERE run_id = ?
                    """,
                    (step_idx, status, now, last_error, run_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE runs
                    SET current_step = ?, status = ?, updated_at = ?, last_error = ?, plan_json = ?
                    WHERE run_id = ?
                    """,
                    (
                        step_idx,
                        status,
                        now,
                        last_error,
                        json.dumps(plan.to_dict()),
                        run_id,
                    ),
                )

    def replace_plan(self, run_id: str, plan: Plan) -> None:
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE runs
                SET plan_json = ?, updated_at = ?
                WHERE run_id = ?
                """,
                (json.dumps(plan.to_dict()), now, run_id),
            )

    def append_event(
        self,
        run_id: str,
        event_type: str,
        payload: dict[str, Any],
        step_idx: int | None = None,
    ) -> None:
        safe_payload = redact_sensitive_data(payload)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO events (run_id, ts, step_idx, event_type, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    utc_now(),
                    step_idx,
                    event_type,
                    json.dumps(safe_payload),
                ),
            )

    def load_events(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE run_id = ? ORDER BY id ASC",
                (run_id,),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["payload_json"] = json.loads(item["payload_json"] or "{}")
            result.append(item)
        return result
