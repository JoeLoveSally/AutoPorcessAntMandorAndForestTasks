import json
from datetime import UTC, datetime, timezone
from pathlib import Path


class Logger:
    def __init__(self, root: Path, run: str):
        self.path = root / "logs" / (run + ".jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.run = run

    def emit(self, event, **data):
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(dict(time=datetime.now(UTC).isoformat(),
                                         run=self.run, event=event, **data), ensure_ascii=False) + "\n")
