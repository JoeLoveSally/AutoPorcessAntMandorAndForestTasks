from pathlib import Path

from runtime.config import QuizConfig
from web_search.quiz import QuizSolver, _score


def test_search_score_prefers_explicit_answer():
    scores = _score("今日题目的正确答案：选项乙", ("选项甲", "选项乙"))
    assert scores[1] > scores[0]


def test_missing_key_uses_configured_fixed_fallback(tmp_path: Path):
    solver = QuizSolver(
        QuizConfig(api_key_env="THIS_KEY_DOES_NOT_EXIST", fallback_option=1, cache_file=tmp_path / "cache.json")
    )
    answer = solver.solve("问题？", ("甲", "乙"))
    assert answer.option_index == 1
    assert answer.source == "fixed_fallback"
