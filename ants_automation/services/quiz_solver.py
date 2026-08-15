from __future__ import annotations

import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request

from ..runtime.config import QuizConfig
from ..runtime.errors import AutomationError


def _load_env_value(path: Path | None, name: str) -> str:
    value = os.getenv(name, "").strip()
    if value or path is None or not path.is_file():
        return value
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, candidate = line.split("=", 1)
        if key.strip() == name:
            return candidate.strip().strip("\"'")
    return ""


class WebQuizSolver:
    def __init__(self, config: QuizConfig):
        self.config = config

    def solve(self, question: str, options: tuple[str, str]) -> int:
        cache = self._read_cache()
        key = self._cache_key(question, options)
        cached = cache.get(key)
        if cached in options:
            return options.index(cached)

        api_key = _load_env_value(self.config.env_file, self.config.api_key_env)
        if not api_key:
            raise AutomationError(
                f"Quiz search key is missing: {self.config.api_key_env}"
            )
        query = f"蚂蚁庄园 今日答案 {question} {' '.join(options)}"
        request = urllib.request.Request(
            self.config.search_url,
            data=json.dumps(
                {"query": query, "freshness": "noLimit", "summary": True, "count": 8},
                ensure_ascii=False,
            ).encode(),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = json.loads(response.read().decode())
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise AutomationError("Quiz web search is unavailable") from exc

        pages = payload.get("data", {}).get("webPages", {}).get("value", [])
        corpus = "\n".join(
            " ".join(str(page.get(field, "")) for field in ("name", "summary", "snippet"))
            for page in pages
            if isinstance(page, dict)
        )
        answer = self._choose(corpus, options)
        cache[key] = options[answer]
        self._write_cache(cache)
        return answer

    @staticmethod
    def _choose(corpus: str, options: tuple[str, str]) -> int:
        normalized = re.sub(r"\s+", "", corpus).lower()
        scores = []
        for option in options:
            item = re.sub(r"\s+", "", option).lower()
            strong = sum(
                len(re.findall(prefix + re.escape(item), normalized))
                for prefix in ("正确答案[:：为是]", "答案[:：为是]", "选择[:：为]?", "答[:：]")
            )
            scores.append(strong * 20 + normalized.count(item))
        if max(scores) == 0 or scores[0] == scores[1]:
            raise AutomationError("Quiz search result does not identify one answer safely")
        return 0 if scores[0] > scores[1] else 1

    def _read_cache(self) -> dict[str, str]:
        try:
            value = json.loads(self.config.cache_file.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def _write_cache(self, value: dict[str, str]) -> None:
        self.config.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.config.cache_file.write_text(
            json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @staticmethod
    def _cache_key(question: str, options: tuple[str, str]) -> str:
        return "\n".join((question.strip(), *(item.strip() for item in options)))
