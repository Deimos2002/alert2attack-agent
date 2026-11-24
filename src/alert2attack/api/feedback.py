"""Analyst decisions on single items of a case file.

A review (``alert2attack.api.reviews``) judges the whole case file. This module
is the finer grain a person needs to stay in the loop:

- every recommended action is approved or rejected by a person before it
  counts as decided, since the agent recommends and never acts;
- any timeline entry or technique can be disputed with a reason, without
  rejecting the whole verdict.

Same constraints as reviews: append-only (the latest decision on an item wins
when shown, earlier ones stay as history), and the case file itself is never
changed. Disputes and rejections export as material for a curator, never as
labels written into the dataset.
"""

from __future__ import annotations

import re
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

Decision = Literal["approve", "reject", "dispute"]

# An item is addressed by its list and position in the case file, which never
# changes after the run, so the address is stable.
TARGET_PATTERN = r"^(next_actions|timeline|techniques)/\d{1,3}$"
_DECISIONS_FOR: dict[str, set[str]] = {
    "next_actions": {"approve", "reject"},
    "timeline": {"dispute"},
    "techniques": {"dispute"},
}


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str = Field(pattern=TARGET_PATTERN)
    decision: Decision
    reason: str = Field(default="", max_length=1000)


class ItemFeedback(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    job_id: str
    scenario_id: str
    target: str
    # What the item said, copied so an export reads on its own.
    item_text: str
    decision: Decision
    reason: str
    reviewer: str
    created_at: str


class InvalidFeedback(ValueError):
    pass


def item_text(case_file: dict[str, Any], target: str) -> str:
    """The item ``target`` points at, as text. Raises ``InvalidFeedback`` if it does not exist."""
    if re.match(TARGET_PATTERN, target) is None:
        raise InvalidFeedback(f"bad target {target!r}")
    section, index = target.split("/")
    items = case_file.get(section) or []
    i = int(index)
    if i >= len(items):
        raise InvalidFeedback(f"{target} does not exist in this case file")
    item = items[i]
    if section == "next_actions":
        return f"{item['action']}: {item['rationale']['text']}"
    if section == "techniques":
        return f"{item['technique_id']} {item.get('note', '')}".strip()
    return f"{item['ts']} {item['text']}"


def build_feedback(
    *, job_id: str, scenario_id: str, case_file: dict[str, Any], request: FeedbackRequest, reviewer: str
) -> ItemFeedback:
    section = request.target.split("/")[0]
    if request.decision not in _DECISIONS_FOR[section]:
        allowed = " or ".join(sorted(_DECISIONS_FOR[section]))
        raise InvalidFeedback(f"{section} items take {allowed}, not {request.decision}")
    if request.decision in {"reject", "dispute"} and not request.reason.strip():
        raise InvalidFeedback("a rejection or dispute needs a reason")
    return ItemFeedback(
        id=str(uuid.uuid4()),
        job_id=job_id,
        scenario_id=scenario_id,
        target=request.target,
        item_text=item_text(case_file, request.target),
        decision=request.decision,
        reason=request.reason,
        reviewer=reviewer,
        created_at=datetime.now(UTC).isoformat(),
    )


class FeedbackStore(Protocol):
    def add(self, feedback: ItemFeedback) -> None: ...

    def list(self, *, job_id: str | None = None, limit: int = 500) -> list[ItemFeedback]: ...


class InMemoryFeedbackStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rows: list[ItemFeedback] = []

    def add(self, feedback: ItemFeedback) -> None:
        with self._lock:
            self._rows.append(feedback)

    def list(self, *, job_id: str | None = None, limit: int = 500) -> list[ItemFeedback]:
        with self._lock:
            rows = [r for r in self._rows if job_id is None or r.job_id == job_id]
        return sorted(rows, key=lambda r: r.created_at, reverse=True)[:limit]


_SCHEMA = """
CREATE TABLE IF NOT EXISTS item_feedback (
  id          TEXT PRIMARY KEY,
  job_id      TEXT NOT NULL,
  scenario_id TEXT NOT NULL,
  target      TEXT NOT NULL,
  item_text   TEXT NOT NULL,
  decision    TEXT NOT NULL,
  reason      TEXT NOT NULL,
  reviewer    TEXT NOT NULL,
  created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_item_feedback_job ON item_feedback(job_id);
"""


class SqliteFeedbackStore:
    """Lives in the jobs database beside reviews; same threading posture."""

    def __init__(self, path: str | Path) -> None:
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def add(self, feedback: ItemFeedback) -> None:
        row = feedback.model_dump()
        with self._lock, self._conn:
            self._conn.execute(
                f"INSERT INTO item_feedback ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
                tuple(row.values()),
            )

    def list(self, *, job_id: str | None = None, limit: int = 500) -> list[ItemFeedback]:
        sql, params = "SELECT * FROM item_feedback", []
        if job_id is not None:
            sql += " WHERE job_id = ?"
            params.append(job_id)
        sql += " ORDER BY created_at DESC LIMIT ?"
        with self._lock:
            rows = self._conn.execute(sql, [*params, limit]).fetchall()
        return [ItemFeedback(**dict(row)) for row in rows]


def export_disagreements(rows: list[ItemFeedback]) -> list[ItemFeedback]:
    """The latest decision per item, kept only where a person disagreed with the agent."""
    latest: dict[tuple[str, str], ItemFeedback] = {}
    for row in sorted(rows, key=lambda r: r.created_at):
        latest[(row.job_id, row.target)] = row
    return [r for r in latest.values() if r.decision in {"reject", "dispute"}]
