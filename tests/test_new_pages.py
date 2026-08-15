from datetime import datetime, timezone

from ants_automation.domain.models import Observation, PageType
from ants_automation.perception.detector import PageDetector
from ants_automation.perception.ui_tree import UiTree


def _observation(*labels: tuple[str, bool, str]) -> Observation:
    nodes = []
    for index, (text, clickable, bounds) in enumerate(labels):
        nodes.append(
            f'<node index="{index}" text="{text}" content-desc="" resource-id="" '
            f'class="android.widget.TextView" clickable="{str(clickable).lower()}" '
            f'enabled="true" bounds="{bounds}" />'
        )
    tree = UiTree.from_xml(f"<hierarchy>{''.join(nodes)}</hierarchy>")
    return Observation(
        datetime.now(timezone.utc), "test", "com.eg.android.AlipayGphone", "Test",
        None, None, tree, tree.visible_labels(), (),
    )


def test_lottery_detector_finds_market_task_draw_and_next_wheel():
    page = PageDetector().detect(_observation(
        ("森林寻宝", False, "[0,100][400,200]"),
        ("去森林集市逛一逛（0/2）", False, "[50,1200][800,1300]"),
        ("去完成", True, "[900,1200][1200,1320]"),
        ("立即抽奖", True, "[300,700][900,900]"),
        ("FE电动力程式派对", True, "[700,200][1200,300]"),
    ))
    assert page.type is PageType.LOTTERY
    assert {"task_market", "draw", "next_wheel"} <= page.elements.keys()


def test_lottery_reward_detector_accepts_continue_button():
    page = PageDetector().detect(_observation(
        ("恭喜抽中20g能量", False, "[200,700][1000,900]"),
        ("做任务继续抽", True, "[300,1800][900,2000]"),
    ))
    assert page.type is PageType.LOTTERY_REWARD
    assert "confirm_reward" in page.elements


def test_lottery_detector_suppresses_draw_when_no_chances_remain():
    page = PageDetector().detect(_observation(
        ("森林寻宝", False, "[0,100][400,200]"),
        ("剩余0次抽奖机会", False, "[300,600][900,700]"),
        ("立即抽奖", True, "[300,700][900,900]"),
    ))
    assert page.type is PageType.LOTTERY
    assert "draw" not in page.elements
    assert "draws_done" in page.elements


def test_energy_rain_intro_detector_accepts_open_button():
    page = PageDetector().detect(_observation(
        ("天天能量雨", False, "[200,700][1000,900]"),
        ("立即开启", True, "[300,1800][900,2000]"),
    ))
    assert page.type is PageType.FOREST_RAIN
    assert "start" in page.elements
