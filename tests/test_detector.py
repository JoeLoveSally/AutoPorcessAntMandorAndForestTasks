from datetime import datetime, timezone
from pathlib import Path

from ants_automation.domain.models import Observation, PageType
from ants_automation.perception.detector import PageDetector
from ants_automation.perception.ui_tree import UiTree


FIXTURES = Path(__file__).parent / "fixtures"


def observation(name: str) -> Observation:
    path = FIXTURES / name
    tree = UiTree.from_file(path)
    screenshot = path.with_suffix(".png")
    return Observation(
        timestamp=datetime.now(timezone.utc),
        device_serial="test",
        package="com.eg.android.AlipayGphone",
        activity="TestActivity",
        screenshot_path=screenshot if screenshot.is_file() else None,
        ui_tree_path=path,
        ui_tree=tree,
        visible_labels=tree.visible_labels(),
    )


def test_detector_recognizes_known_pages():
    detector = PageDetector()
    assert detector.detect(observation("alipay_home.xml")).type is PageType.ALIPAY_HOME
    assert detector.detect(observation("manor_home.xml")).type is PageType.MANOR_HOME
    feed_tasks = detector.detect(observation("manor_feed_tasks.xml"))
    assert feed_tasks.type is PageType.MANOR_FEED_TASKS
    assert feed_tasks.elements["claim_daily"].center == (1235, 1330)
    assert feed_tasks.elements["quiz"].center == (1230, 1660)
    assert feed_tasks.elements["video"].center == (1230, 2035)
    assert all(
        feed_tasks.elements[key].source.startswith("cv_template:")
        for key in ("claim_daily", "quiz", "video")
    )
    # The second entry is below the viewport and becomes actionable only after scrolling.
    assert [item.text for key, item in feed_tasks.elements.items() if key.startswith("lottery_")] == [
        "【抽抽乐】桃花为信来啦 每日抽1次小鸡装扮可得90g饲料 去完成"
    ]
    video_complete = detector.detect(observation("manor_feed_video_complete.xml"))
    assert video_complete.type is PageType.MANOR_FEED_VIDEO_COMPLETE
    assert video_complete.elements == {}
    quiz = detector.detect(observation("manor_quiz.xml"))
    assert quiz.type is PageType.MANOR_QUIZ
    assert quiz.elements["answer_a"].text == "是，越冰越好"
    assert quiz.elements["answer_b"].text == "并不是"
    quiz_result = detector.detect(observation("manor_quiz_result.xml"))
    assert quiz_result.type is PageType.MANOR_QUIZ_RESULT
    assert quiz_result.elements["claim_quiz_feed"].center == (720, 2652)
    assert detector.detect(observation("manor_family.xml")).type is PageType.MANOR_FAMILY
    donation = detector.detect(observation("manor_donation.xml"))
    assert donation.type is PageType.MANOR_DONATION
    assert donation.elements["select_project"].center == (1186, 2146)
    project = detector.detect(observation("manor_donation_project.xml"))
    assert project.type is PageType.MANOR_DONATION_PROJECT
    assert project.elements["donate_now"].center == (720, 3018)
    confirm = detector.detect(observation("manor_donation_confirm.xml"))
    assert confirm.type is PageType.MANOR_DONATION_CONFIRM
    assert confirm.elements["confirm_donation"].center == (720, 3018)
    reward = detector.detect(observation("manor_donation_reward.xml"))
    assert reward.type is PageType.MANOR_DONATION_REWARD
    completed = detector.detect(observation("manor_family_tasks_completed.xml"))
    assert completed.type is PageType.MANOR_FAMILY
    assert "donation_done" in completed.elements
    assert completed.elements["donation_done"].clickable is False


def test_detector_rejects_wrong_package():
    item = observation("alipay_home.xml")
    wrong = Observation(**{**item.__dict__, "package": "com.example"})
    assert PageDetector().detect(wrong).type is PageType.UNKNOWN
