import sqlite3
import json
from pathlib import Path

from app.models.domain import DecisionLog, ProfileFact, UnresolvedAnswer


class SQLiteStore:
    def __init__(self, path: str) -> None:
        self.path = path

    def initialize(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS profile_facts (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    verified INTEGER NOT NULL,
                    source TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS unresolved_answers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS decision_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_id TEXT,
                    action TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    validation_json TEXT,
                    answer TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(decision_logs)").fetchall()
            }
            if "answer" not in columns:
                connection.execute("ALTER TABLE decision_logs ADD COLUMN answer TEXT")

    def save_profile_fact(self, fact: ProfileFact) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO profile_facts(key, value, verified, source) VALUES (?, ?, ?, ?)",
                (fact.key, fact.value, fact.verified, fact.source),
            )

    def save_unresolved(self, unresolved: UnresolvedAnswer) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "INSERT INTO unresolved_answers(question_id, reason) VALUES (?, ?)",
                (unresolved.question_id, unresolved.reason),
            )

    def save_decision(self, decision: DecisionLog) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "INSERT INTO decision_logs(question_id, action, reason, validation_json, answer) VALUES (?, ?, ?, ?, ?)",
                (
                    decision.question_id,
                    decision.action,
                    decision.reason,
                    decision.validation.model_dump_json() if decision.validation else json.dumps(None),
                    decision.answer,
                ),
            )

    def activity_history(self, limit: int = 100) -> list[dict[str, object]]:
        bounded_limit = max(1, min(limit, 500))
        with sqlite3.connect(self.path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT id, question_id, action, reason, answer, created_at "
                "FROM decision_logs ORDER BY id DESC LIMIT ?",
                (bounded_limit,),
            ).fetchall()
        return [dict(row) for row in rows]
