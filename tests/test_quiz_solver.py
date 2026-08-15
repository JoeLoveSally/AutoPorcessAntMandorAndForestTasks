from pathlib import Path

import pytest

from ants_automation.runtime.config import QuizConfig
from ants_automation.runtime.errors import AutomationError
from ants_automation.services.quiz_solver import WebQuizSolver, _load_env_value


def test_quiz_solver_uses_explicit_answer_phrase():
    assert WebQuizSolver._choose(
        "这道蚂蚁庄园题的正确答案：并不是。冷饮过冰会刺激肠胃。",
        ("是，越冰越好", "并不是"),
    ) == 1


def test_quiz_solver_rejects_ambiguous_results():
    with pytest.raises(AutomationError):
        WebQuizSolver._choose("网页同时列出了甲和乙", ("甲", "乙"))


def test_dotenv_reader_does_not_mutate_environment(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("TEST_SEARCH_TOKEN", raising=False)
    path = tmp_path / ".env"
    path.write_text("TEST_SEARCH_TOKEN=placeholder\n", encoding="utf-8")
    assert _load_env_value(path, "TEST_SEARCH_TOKEN") == "placeholder"
