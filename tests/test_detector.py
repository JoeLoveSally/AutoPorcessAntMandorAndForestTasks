from conftest import make_observation

from domain_data import OverlayType, Page
from screen_perception import ScreenDetector


def xml(*nodes: str) -> str:
    body = "".join(
        f'<node text="{text}" content-desc="" resource-id="" class="TextView" '
        f'clickable="true" enabled="true" bounds="[10,{100 + index * 100}][1300,{180 + index * 100}]" />'
        for index, text in enumerate(nodes)
    )
    return f'<?xml version="1.0"?><hierarchy rotation="0">{body}</hierarchy>'


def test_alipay_home_requires_both_entries():
    page = ScreenDetector().detect(make_observation(xml("蚂蚁庄园", "蚂蚁森林")))
    assert page.page is Page.ALIPAY_HOME
    assert set(page.elements) == {"manor", "forest"}


def test_overlay_does_not_replace_underlying_feed_page():
    page = ScreenDetector().detect(
        make_observation(xml("饲料任务", "领饲料", "猜价格赢饲料", "放弃奖励"))
    )
    assert page.page is Page.MANOR_FEED_TASKS
    assert page.overlays[0].type is OverlayType.PRODUCT_QUIZ
    assert page.element("abandon_reward") is not None


def test_wrong_package_is_unknown():
    page = ScreenDetector().detect(
        make_observation(xml("蚂蚁庄园", "蚂蚁森林"), package="example.app")
    )
    assert page.page is Page.UNKNOWN


def test_quiz_without_letter_prefixes_detects_two_layout_options():
    shaped = """<?xml version='1.0'?><hierarchy rotation='0'>
      <node text='题目来源 - 答答星球' content-desc='' resource-id='' class='TextView' clickable='false' enabled='true' bounds='[100,2900][1300,3000]' />
      <node text='云南过桥米线中常加入的象牙菜指哪种食材' content-desc='' resource-id='' class='TextView' clickable='false' enabled='true' bounds='[100,900][1300,1100]' />
      <node text='草芽' content-desc='' resource-id='' class='TextView' clickable='false' enabled='true' bounds='[500,1850][900,2050]' />
      <node text='黄豆芽' content-desc='' resource-id='' class='TextView' clickable='false' enabled='true' bounds='[500,2100][900,2300]' />
    </hierarchy>"""
    page = ScreenDetector().detect(make_observation(shaped))
    assert page.page is Page.MANOR_QUIZ
    assert [page.elements[key].text for key in ("option_0", "option_1")] == ["草芽", "黄豆芽"]


def test_forest_home_card_does_not_look_like_energy_rain_start_page():
    page = ScreenDetector().detect(
        make_observation(xml("蚂蚁森林", "天天能量雨", "找能量", "真爱合种"))
    )
    assert page.page is Page.FOREST_HOME


def test_forest_sign_reward_overlay_wins_over_underlying_home():
    page = ScreenDetector().detect(
        make_observation(xml("蚂蚁森林", "我的活力值", "关闭奖励弹窗", "立即领取"))
    )
    assert page.page is Page.FOREST_SIGN_REWARD
    assert page.element("close_reward") is not None
    assert page.element("claim") is not None


def test_hidden_donation_modal_does_not_replace_visible_detail_page():
    shaped = """<?xml version='1.0'?><hierarchy rotation='0'>
      <node text='本期目标：帮助32人' content-desc='' resource-id='' class='TextView' clickable='false' enabled='true' bounds='[100,1800][900,1900]' />
      <node text='立即捐蛋' content-desc='' resource-id='' class='TextView' clickable='true' enabled='true' bounds='[400,2900][1000,3100]' />
      <node text='捐爱心蛋' content-desc='' resource-id='' class='TextView' clickable='false' enabled='true' bounds='[0,0][0,0]' />
    </hierarchy>"""
    page = ScreenDetector().detect(make_observation(shaped))
    assert page.page is Page.MANOR_DONATION_DETAIL


# --- baba farm & chicken kitchen pages (calibration-aware smoke tests) -----


def test_baba_farm_harvest_page_detected_before_main_page():
    page = ScreenDetector().detect(make_observation(xml("丰收礼包", "立即领取", "关闭")))
    assert page.page is Page.BABA_FARM_HARVEST
    assert page.element("claim") is not None
    assert page.element("close") is not None


def test_baba_farm_tasks_sub_page_locates_sub_task_claims():
    shaped = """<?xml version='1.0'?><hierarchy rotation='0'>
      <node text='做任务集肥料' content-desc='' resource-id='' class='TextView' clickable='false' enabled='true' bounds='[100,200][1300,300]' />
      <node text='每日签到' content-desc='' resource-id='' class='TextView' clickable='false' enabled='true' bounds='[100,800][900,900]' />
      <node text='领取' content-desc='' resource-id='' class='TextView' clickable='true' enabled='true' bounds='[1100,800][1300,900]' />
      <node text='蚂蚁庄园小鸡肥料' content-desc='' resource-id='' class='TextView' clickable='false' enabled='true' bounds='[100,1500][900,1600]' />
      <node text='领取' content-desc='' resource-id='' class='TextView' clickable='true' enabled='true' bounds='[1100,1500][1300,1600]' />
      <node text='关闭' content-desc='' resource-id='' class='TextView' clickable='true' enabled='true' bounds='[1300,200][1400,300]' />
    </hierarchy>"""
    page = ScreenDetector().detect(make_observation(shaped))
    assert page.page is Page.BABA_FARM_TASKS
    assert page.element("daily_sign_claim") is not None
    assert page.element("chicken_feed_claim") is not None
    assert page.element("close") is not None


def test_baba_farm_main_page_keys_fertilize_free_fertilizer_claim_now():
    page = ScreenDetector().detect(make_observation(xml("芭芭农场", "施肥", "点击领取", "立即领肥")))
    assert page.page is Page.BABA_FARM
    assert page.element("fertilize") is not None
    assert page.element("free_fertilizer") is not None
    assert page.element("claim_now") is not None


def test_kitchen_donate_sub_page_detected_before_main_kitchen():
    page = ScreenDetector().detect(make_observation(xml("献爱心 得食材", "领10g食材")))
    assert page.page is Page.KITCHEN_DONATE
    assert page.element("claim") is not None


def test_chicken_kitchen_main_page_still_detected_without_daily_ingredient():
    page = ScreenDetector().detect(make_observation(xml("小鸡厨房", "做美食", "爱心食材店", "关闭")))
    assert page.page is Page.CHICKEN_KITCHEN
    assert page.element("cook") is not None
    assert page.element("donate_shop") is not None
    assert page.element("daily_ingredient") is None
