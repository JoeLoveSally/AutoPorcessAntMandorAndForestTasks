"""Lottery task identity patterns calibrated against device evidence.

Run bc2b84 (2026-09-24): the 抽抽乐 row carries its bare game logo
抽抽乐 at the lower-left in addition to the bracketed title
【抽抽乐】丹桂秋光来啦, so the old ^(?!.*IP).*抽抽乐 pattern (no closing
anchor) matched both elements and row() failed closed with Ambiguous
task identity - the closing 】 is the only text the plain logo lacks.
Run ffc3ae then showed the IP row carries no brackets at all in its
active period (IP抽抽乐江苏文旅装扮, left tag 限定IP), so the IP side
anchors on its ^IP prefix instead: enough to exclude the plain 抽抽乐
title while still matching every period's theme suffix.
"""

import re
from types import SimpleNamespace

from workflow.tasks import build_tasks


def registered_patterns():
    tasks = build_tasks(SimpleNamespace())
    return {
        name: call.args[0]
        for name, _stage, call in tasks
        if name in ("manor.feed.lottery", "manor.feed.ip_lottery")
    }


def test_lottery_title_patterns_discriminate_the_row_logo():
    found = registered_patterns()
    lottery = found["manor.feed.lottery"]
    ip = found["manor.feed.ip_lottery"]

    assert re.search(lottery, "【抽抽乐】丹桂秋光来啦")
    assert re.search(lottery, "【抽抽乐 】丹桂秋光来啦")
    assert re.search(lottery, "抽抽乐】丹桂秋光来啦")
    assert not re.search(lottery, "抽抽乐")  # the bare logo (bc2b84)
    assert not re.search(lottery, "【IP抽抽乐】幸运抽")
    assert not re.search(lottery, "每日抽1次小鸡装扮可得90g饲料")

    assert re.search(ip, "【IP抽抽乐】幸运抽")
    # Device evidence (run ffc3ae): the active period's row is unbracketed
    # and its left tag is 限定IP - not a bare IP抽抽乐 twin - so the prefix
    # anchors without a closing 】 while the plain title stays excluded.
    assert re.search(ip, "IP抽抽乐江苏文旅装扮")
    assert not re.search(ip, "限定IP")
    assert not re.search(ip, "【抽抽乐】丹桂秋光来啦")
