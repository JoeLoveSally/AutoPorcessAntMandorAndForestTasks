from datetime import datetime, timezone
from pathlib import Path

from ants_automation.domain.models import Observation, PageType
from ants_automation.perception.detector import PageDetector
from ants_automation.perception.ui_tree import UiTree


FIXTURES = Path(__file__).parent / "fixtures"


def observation(name: str) -> Observation:
    path = FIXTURES / name
    tree = UiTree.from_file(path)
    return Observation(
        timestamp=datetime.now(timezone.utc),
        device_serial="test",
        package="com.eg.android.AlipayGphone",
        activity="TestActivity",
        screenshot_path=None,
        ui_tree_path=path,
        ui_tree=tree,
        visible_labels=tree.visible_labels(),
    )


def test_detector_recognizes_known_pages():
    detector = PageDetector()
    assert detector.detect(observation("alipay_home.xml")).type is PageType.ALIPAY_HOME
    assert detector.detect(observation("manor_home.xml")).type is PageType.MANOR_HOME
    assert detector.detect(observation("manor_family.xml")).type is PageType.MANOR_FAMILY


def test_detector_rejects_wrong_package():
    item = observation("alipay_home.xml")
    wrong = Observation(**{**item.__dict__, "package": "com.example"})
    assert PageDetector().detect(wrong).type is PageType.UNKNOWN
