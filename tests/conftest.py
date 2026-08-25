from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from domain_data import Observation
from screen_perception import UiTree


def make_observation(
    xml: str,
    *,
    package: str = "com.eg.android.AlipayGphone",
    screenshot: bytes | None = None,
) -> Observation:
    tree = UiTree.from_bytes(xml.encode())
    return Observation(
        id="obs-1",
        captured_at=datetime.now(timezone.utc),
        device_serial="serial",
        package=package,
        activity="Activity",
        width=1440,
        height=3200,
        screenshot_path=Path("shot.png"),
        ui_tree_path=Path("tree.xml"),
        screenshot=screenshot,
        ui_tree=tree,
    )
