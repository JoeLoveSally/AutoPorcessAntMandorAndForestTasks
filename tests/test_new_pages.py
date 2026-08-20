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


def test_lottery_detector_marks_browse_task_complete_from_progress():
    page = PageDetector().detect(_observation(
        ("抽抽乐", False, "[0,100][400,200]"),
        ("去杂货铺逛一逛（3/3）", False, "[50,1200][800,1300]"),
        ("立即抽奖", True, "[300,700][900,900]"),
    ))
    assert page.type is PageType.LOTTERY
    assert "task_store" not in page.elements
    assert "task_store_done" in page.elements


def test_lottery_reward_detector_accepts_continue_button():
    page = PageDetector().detect(_observation(
        ("恭喜抽中20g能量", False, "[200,700][1000,900]"),
        ("做任务继续抽", True, "[300,1800][900,2000]"),
    ))
    assert page.type is PageType.LOTTERY_REWARD
    assert "confirm_reward" in page.elements


def test_lottery_reward_detector_accepts_any_prize_count_acknowledgement():
    page = PageDetector().detect(_observation(
        ("抽抽乐", False, "[0,100][400,200]"),
        ("3件奖品", False, "[0,580][1440,956]"),
        ("我知道了", False, "[356,2124][1084,2284]"),
    ))
    assert page.type is PageType.LOTTERY_REWARD
    assert page.elements["confirm_reward"].center == (720, 2204)


def test_lottery_detector_suppresses_draw_when_no_chances_remain():
    page = PageDetector().detect(_observation(
        ("森林寻宝", False, "[0,100][400,200]"),
        ("剩余0次抽奖机会", False, "[300,600][900,700]"),
        ("立即抽奖", True, "[300,700][900,900]"),
    ))
    assert page.type is PageType.LOTTERY
    assert "draw" not in page.elements
    assert "draws_done" in page.elements


def test_lottery_detector_keeps_task_claim_separate_from_feed_exchange():
    page = PageDetector().detect(_observation(
        ("抽抽乐", False, "[0,100][400,200]"),
        ("还剩27次机会", False, "[740,1816][1048,1880]"),
        ("每日签到", False, "[320,2468][1080,2532]"),
        ("领取", True, "[1104,2492][1340,2592]"),
        ("去杂货铺逛一逛 (1/3)", False, "[320,2720][1080,2788]"),
        ("领取", True, "[1104,2748][1340,2844]"),
        ("消耗饲料换机会", False, "[320,2976][1080,3040]"),
        ("去完成", True, "[1104,3000][1340,3096]"),
    ))
    assert page.type is PageType.LOTTERY
    assert "task_store" not in page.elements
    assert page.elements["claim_task_store"].center == (1222, 2796)
    assert page.elements["exchange_feed"].center == (1222, 3048)
    assert page.elements["claim_daily_chance"].center == (1222, 2542)
    assert page.elements["draw_count"].text == "27"


def test_lottery_detector_recognizes_feed_exchange_confirmation():
    page = PageDetector().detect(_observation(
        ("消耗180g饲料，可换取2次机会", False, "[312,1408][1128,1492]"),
        ("确认兑换", True, "[728,1680][1160,1836]"),
    ))
    assert page.type is PageType.LOTTERY
    assert page.elements["confirm_exchange"].center == (944, 1758)


def test_lottery_detector_recognizes_completed_feed_exchange():
    page = PageDetector().detect(_observation(
        ("抽抽乐", False, "[0,100][400,200]"),
        ("消耗饲料换机会", False, "[320,2976][1080,3040]"),
        ("已完成", False, "[1104,3000][1340,3096]"),
    ))
    assert page.type is PageType.LOTTERY
    assert "exchange_feed" not in page.elements
    assert "exchange_feed_done" in page.elements


def test_lottery_detector_recognizes_completed_daily_chance():
    page = PageDetector().detect(_observation(
        ("抽抽乐", False, "[0,100][400,200]"),
        ("每日签到", False, "[320,2468][1080,2532]"),
        ("已完成", False, "[1104,2492][1340,2592]"),
    ))
    assert page.type is PageType.LOTTERY
    assert "claim_daily_chance" not in page.elements
    assert "daily_chance_done" in page.elements


def test_energy_rain_intro_detector_accepts_open_button():
    page = PageDetector().detect(_observation(
        ("天天能量雨", False, "[200,700][1000,900]"),
        ("立即开启", True, "[300,1800][900,2000]"),
    ))
    assert page.type is PageType.FOREST_RAIN
    assert "start" in page.elements


def test_co_plant_detector_recognizes_100g_dialog_and_reward():
    dialog = PageDetector().detect(_observation(
        ("爱情合种", False, "[0,100][400,200]"),
        ("100", False, "[600,1600][800,1700]"),
        ("+", True, "[900,1550][1050,1720]"),
        ("浇水", True, "[300,1900][1100,2100]"),
    ))
    assert dialog.type is PageType.FOREST_CO_PLANT
    assert dialog.elements["amount_value"].text == "100"
    assert {"increase_amount", "confirm_water"} <= dialog.elements.keys()

    reward = PageDetector().detect(_observation(
        ("爱情合种", False, "[0,100][400,200]"),
        ("我知道啦", True, "[300,1900][1100,2100]"),
    ))
    assert reward.type is PageType.FOREST_CO_PLANT
    assert "reward_ack" in reward.elements
