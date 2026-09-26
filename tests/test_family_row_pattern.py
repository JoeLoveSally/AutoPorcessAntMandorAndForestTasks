"""Family visit row identity calibrated against device evidence.

Run 8f3a63 (2026-09-25): the promo period renamed the row title from
去家庭逛一逛 to 家庭×阿福新活动上线 (OCR swinging the collab separator ×/入/X
across captures) while the description still carries 去家庭还可获得90g饲料哦
- the old bare pattern matched nothing and row() failed as Required task
missing after a full scroll of the list.
"""

import re
from types import SimpleNamespace

from workflow.tasks import build_tasks


def family_pattern():
    tasks = build_tasks(SimpleNamespace())
    return next(call.args[0] for name, _stage, call in tasks
                if name == "manor.feed.family")


def test_family_row_pattern_accepts_the_promo_rename():
    pattern = family_pattern()

    assert re.search(pattern, "家庭×阿福新活动上线")
    assert re.search(pattern, "家庭入阿福新活动上线")
    assert re.search(pattern, "家庭X阿福新活动上线")
    assert re.search(pattern, "去家庭逛一逛")  # post-promo periods

    # The two-line description shares 去家庭 with the old title and sits
    # next to the renamed title - it must never double-match.
    assert not re.search(
        pattern,
        "参与活动赢「运动健康季」活动主题小盲盒，去家庭还可获得90g饲料哦")
    assert not re.search(pattern, "去芭芭农场逛一逛")
