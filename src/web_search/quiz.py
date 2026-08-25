from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from runtime.config import QuizConfig


@dataclass(frozen=True, slots=True)
class QuizAnswer:
    option_index: int
    source: str
    confidence: float


class QuizSolver:
    def __init__(self, config: QuizConfig):
        self.config = config

    def solve(self, question: str, options: tuple[str, str]) -> QuizAnswer:
        cache = self._read_cache()
        key = self._cache_key(question, options)
        if cached := cache.get(key):
            if cached in options:
                return QuizAnswer(options.index(cached), "cache", 1.0)
        try:
            answer, confidence = self._search(question, options)
        except Exception:
            return QuizAnswer(self.config.fallback_option, "fixed_fallback", 0.0)
        cache[key] = options[answer]
        self._write_cache(cache)
        return QuizAnswer(answer, "web_search", confidence)

    def _search(self, question: str, options: tuple[str, str]) -> tuple[int, float]:
        api_key = _env_value(self.config.env_file, self.config.api_key_env)
        if not api_key:
            raise RuntimeError("search key missing")
        request = urllib.request.Request(
            self.config.search_url,
            data=json.dumps(
                {"query": f"蚂蚁庄园 {question} 正确答案", "freshness": "noLimit", "summary": True, "count": 8},
                ensure_ascii=False,
            ).encode(),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                payload = json.loads(response.read().decode())
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("search unavailable") from exc
        pages = payload.get("data", {}).get("webPages", {}).get("value", [])
        corpus = "\n".join(
            " ".join(str(page.get(field, "")) for field in ("name", "summary", "snippet"))
            for page in pages
            if isinstance(page, dict)
        )
        scores = _score(corpus, options)
        if max(scores) <= 0 or scores[0] == scores[1]:
            raise RuntimeError("ambiguous search result")
        winner = 0 if scores[0] > scores[1] else 1
        confidence = abs(scores[0] - scores[1]) / max(scores)
        if confidence < 0.15:
            raise RuntimeError("low-confidence search result")
        return winner, confidence

    def _read_cache(self) -> dict[str, str]:
        try:
            value = json.loads(self.config.cache_file.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def _write_cache(self, value: dict[str, str]) -> None:
        self.config.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.config.cache_file.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _cache_key(question: str, options: tuple[str, str]) -> str:
        return "\n".join((question.strip(), *(item.strip() for item in options)))


def _score(corpus: str, options: tuple[str, str]) -> tuple[int, int]:
    normalized = re.sub(r"\s+", "", corpus).lower()
    scores: list[int] = []
    for option in options:
        item = re.sub(r"\s+", "", option).lower()
        strong = sum(
            len(re.findall(prefix + re.escape(item), normalized))
            for prefix in ("正确答案[:：为是]", "答案[:：为是]", "选择[:：为]?", "答[:：]")
        )
        scores.append(strong * 20 + normalized.count(item))
    return scores[0], scores[1]


def _env_value(path: Path | None, name: str) -> str:
    if value := os.getenv(name, "").strip():
        return value
    if path is None or not path.is_file():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        if key.strip() == name:
            return value.strip().strip("\"'")
    return ""
