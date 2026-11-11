from pathlib import Path

from app.db.sqlite import SQLiteStore
from app.models.domain import DecisionLog


def test_activity_history_includes_generated_answer(tmp_path: Path) -> None:
    store = SQLiteStore(str(tmp_path / "activity.sqlite3"))
    store.initialize()
    store.save_decision(
        DecisionLog(
            question_id="q1",
            action="fill",
            reason="Generated answer was validated and filled.",
            answer="Battery life",
        )
    )
    history = store.activity_history()
    assert history[0]["question_id"] == "q1"
    assert history[0]["answer"] == "Battery life"
