"""family_action confirm-dismissal calibrated against device evidence.

Run 3b0d9e (2026-09-24): the food-selection sheet opened as page UNKNOWN
(its title OCRs 已选4份美食..., matching neither a page rule nor the
confirm overlay), the 确认 tap landed, and the list returned carrying
请家人吃一顿美食(1/3) - yet the postcondition also demanded 美食 absence
while the row title itself contains 美食, so a verified 0/3 -> 1/3 请客
timed out. Page == family_tasks alone proves the sheet closed; the open
sheet classifies UNKNOWN (same shape as the feed dialog's
将消耗180g饲料 frame, run f81adb).
"""

from domain_data import Element, Observation
from workflow.manor.daily import Manor


def obs(page, texts=(), oid="fixture"):
    elements = [Element(text, (100, 1900, 900, 1990), oid) for text in texts]
    return Observation(oid, 0.0, 1440, 3200, "alipay", elements, page)


class FakeSession:
    def __init__(self, *, row_texts=(), title="请家人吃一顿美食(0/3)",
                 button="去请客"):
        self.task = "manor.family.meal"
        self._row_obs = obs("family_tasks", row_texts)
        self._title = title
        self._button = button
        self._tap_element_results = [
            obs("UNKNOWN", ["已选4份美食请客吃饭",
                            "每个家人的小鸡会根据选择的美食，立即产蛋哦!",
                            "亲密度+3", "确认"]),
        ]
        self._tap_results = [
            obs("family_tasks", ["请客成功", "请家人吃一顿美食(1/3)", "16点后可来请客"]),
        ]
        self._ensure = self._row_obs
        self.tap_element_calls = []
        self.tap_calls = []
        self.done_args = []
        self.complete_row_calls = []
        self.obs = None

    def row(self, _pattern, page="feed"):
        assert page == "family_tasks"
        title = Element(self._title, (292, 2516, 875, 2579), "fixture")
        button = Element(self._button, (1144, 1970, 1300, 2050), "fixture")
        return self._row_obs, title, button

    def tap_element(self, _obs, element, predicate, **kwargs):
        self.tap_element_calls.append((element.text, kwargs))
        after = self._tap_element_results.pop(0)
        assert predicate(after), "the open sheet must satisfy the opener predicate"
        self.obs = after
        return after

    def tap(self, pattern, predicate, **kwargs):
        self.tap_calls.append((pattern, kwargs))
        after = self._tap_results.pop(0)
        # The scripted post-dismissal frame carries 美食 inside the row
        # title; the old not-o.has(prompt) clause failed exactly here.
        assert predicate(after), "the verified post-treat list must satisfy the predicate"
        self.obs = after
        return after

    def done(self, _obs, **kwargs):
        self.done_args.append(kwargs)

    def ensure(self, page):
        return self._ensure

    def complete_row(self, pattern, page="feed"):
        self.complete_row_calls.append((pattern, page))


def test_meal_confirm_survives_a_row_title_that_contains_the_prompt():
    session = FakeSession()

    Manor(session).family_action("meal")

    assert [call[1]["name"] for call in session.tap_element_calls] == ["family-meal"]
    assert session.tap_calls[0][0] == "^确认$"
    assert session.tap_calls[0][1]["spend"] is True
    assert session.done_args == []
    assert len(session.complete_row_calls) == 1
    assert "请家人吃一顿美食" in session.complete_row_calls[0][0]
    assert session.complete_row_calls[0][1] == "family_tasks"


def test_feed_skips_when_no_family_chicken_is_feedable():
    # Device evidence (2026-09-24, run 974051): the slot rendered the
    # disabled two-line label 暂无小鸡可喂 (OCR segments it as 暂无小鸡 +
    # 可喂), so no TASK_BUTTON matched - three row-refresh frames, then the
    # column-fallback tap landed on the dead label and nothing opened.
    session = FakeSession(
        row_texts=("帮喂家人小鸡(0/1)", "暂无小鸡", "可喂"),
        title="帮喂家人小鸡(0/1)",
        button="暂无小鸡可喂",
    )

    Manor(session).family_action("feed")

    assert session.done_args == [{"skipped": True}]
    assert session.tap_element_calls == []
    assert session.tap_calls == []


def test_meal_treats_the_misread_come_back_pill_as_done():
    # Device evidence (2026-10-09, run eaf7d5): the 小号's family list rendered
    # the disabled pill as 朋天再来 while the donate row's identical pill read
    # 明天再来 in the SAME frame (明 and 朋 share the 月 radical). The done
    # check missed it, the loop tried to act on the dead label, and the run
    # died on "Task completion not verified: ^请家人吃一顿美食...". The
    # variant must resolve as already-done instead of a failed submission.
    session = FakeSession(
        row_texts=("请家人吃一顿美食(1/3)", "朋天再来"),
        title="请家人吃一顿美食(1/3)",
        button="朋天再来",
    )

    Manor(session).family_action("meal")

    assert session.done_args == [{"already": True}]
    assert session.tap_element_calls == []
    assert session.tap_calls == []
