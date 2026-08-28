import cv2
import numpy as np
from conftest import make_observation

from domain_data import Bounds, OverlayType, Page
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


def test_membership_plant_task_is_not_forest_home():
    # Real-device dump (run 20260827-084827): 找能量 routed here after all
    # collectible friends were exhausted.  The page still exposes 蚂蚁森林 and
    # must be rejected so post-condition recovery can return to forest home.
    page = ScreenDetector().detect(
        make_observation(
            xml(
                "蚂蚁森林",
                "支付宝会员签到",
                "养绿植得能量",
                "找能量共获得 137g 今日共获得289g",
            )
        )
    )

    assert page.page is Page.UNKNOWN
    assert "ui:支付宝会员签到" in page.evidence


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


def test_baba_task_list_is_not_misclassified_as_external_browse():
    shaped = """<?xml version='1.0'?><hierarchy rotation='0'>
      <node text='做任务集肥料' content-desc='' resource-id='' class='TextView' clickable='false' enabled='true' bounds='[0,856][1440,1192]' />
      <node text='浏览15秒得1500肥' content-desc='' resource-id='' class='TextView' clickable='false' enabled='true' bounds='[88,1852][1064,2036]' />
      <node text='森林10周年浇水得好礼' content-desc='' resource-id='' class='TextView' clickable='false' enabled='true' bounds='[88,2848][1064,3032]' />
      <node text='参与施肥挑战赢大额奖励' content-desc='' resource-id='' class='TextView' clickable='false' enabled='true' bounds='[400,1016][1012,1092]' />
      <node text='关闭做任务集肥料弹窗' content-desc='' resource-id='' class='Button' clickable='true' enabled='true' bounds='[1260,1032][1380,1148]' />
      <node text='关闭' content-desc='' resource-id='' class='Button' clickable='true' enabled='true' bounds='[656,2340][784,2464]' />
    </hierarchy>"""
    page = ScreenDetector().detect(make_observation(shaped))
    assert page.page is Page.BABA_FARM_TASKS
    assert page.element("close_reward").bounds == Bounds(656, 2340, 784, 2464)


def test_farm_challenge_banner_without_modal_close_is_not_an_overlay():
    shaped = """<?xml version='1.0'?><hierarchy rotation='0'>
      <node text='做任务集肥料' content-desc='' resource-id='' class='TextView' clickable='false' enabled='true' bounds='[0,856][1440,1192]' />
      <node text='参与施肥挑战赢大额奖励' content-desc='' resource-id='' class='TextView' clickable='false' enabled='true' bounds='[400,1016][1012,1092]' />
      <node text='关闭做任务集肥料弹窗' content-desc='' resource-id='' class='Button' clickable='true' enabled='true' bounds='[1260,1032][1380,1148]' />
      <node text='关闭' content-desc='' resource-id='' class='Button' clickable='true' enabled='true' bounds='[1244,188][1406,308]' />
    </hierarchy>"""
    page = ScreenDetector().detect(make_observation(shaped))
    assert page.page is Page.BABA_FARM_TASKS
    assert not page.overlays


def test_baba_farm_main_page_keys_fertilize_free_fertilizer_claim_now():
    page = ScreenDetector().detect(make_observation(xml("芭芭农场", "施肥", "点击领取", "立即领肥")))
    assert page.page is Page.BABA_FARM
    assert page.element("fertilize") is not None
    assert page.element("free_fertilizer") is not None
    assert page.element("claim_now") is not None


def test_baba_farm_banner_text_is_not_used_as_fertilize_action():
    shaped = """<?xml version='1.0'?><hierarchy rotation='0'>
      <node text='芭芭农场' content-desc='' resource-id='' class='TextView' clickable='false' enabled='true' bounds='[152,203][652,293]' />
      <node text='施肥赢3000肥料' content-desc='' resource-id='' class='TextView' clickable='false' enabled='true' bounds='[400,928][1012,1020]' />
      <node text='还差4次领肥料' content-desc='' resource-id='' class='TextView' clickable='false' enabled='true' bounds='[540,1852][900,1944]' />
    </hierarchy>"""
    ok, encoded = cv2.imencode(".png", np.zeros((3200, 1440, 3), dtype=np.uint8))
    assert ok
    page = ScreenDetector().detect(make_observation(shaped, screenshot=encoded.tobytes()))
    assert page.page is Page.BABA_FARM
    assert page.element("fertilize").source == "cv_layout:baba_farm_fertilize"
    assert page.element("fertilize").center == (720, 2464)


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


def test_canvas_chicken_kitchen_detects_visible_layout_controls():
    image = np.full((3200, 1440, 3), (220, 170, 115), dtype=np.uint8)
    cv2.rectangle(image, (800, 2820), (1390, 3120), (20, 165, 245), -1)
    cv2.circle(image, (420, 600), 90, (15, 100, 245), -1)
    cv2.rectangle(image, (1080, 2360), (1400, 2510), (20, 40, 245), -1)
    ok, encoded = cv2.imencode(".png", image)
    assert ok

    page = ScreenDetector().detect(make_observation(xml(), screenshot=encoded.tobytes()))

    assert page.page is Page.CHICKEN_KITCHEN
    assert {"cook", "claim_ingredient", "daily_ingredient", "donate_shop"} <= page.elements.keys()


def test_canvas_kitchen_recipe_exposes_only_close():
    image = np.full((3200, 1440, 3), 30, dtype=np.uint8)
    cv2.rectangle(image, (200, 860), (1240, 2150), (235, 245, 250), -1)
    cv2.circle(image, (720, 2688), 70, (255, 255, 255), 12)
    ok, encoded = cv2.imencode(".png", image)
    assert ok

    page = ScreenDetector().detect(make_observation(xml(), screenshot=encoded.tobytes()))

    assert page.page is Page.CHICKEN_KITCHEN
    assert set(page.elements) == {"close"}
    assert page.element("close").center == (720, 2688)


def test_bright_canvas_task_cards_do_not_look_like_kitchen_recipe():
    image = np.full((3200, 1440, 3), 35, dtype=np.uint8)
    cv2.rectangle(image, (40, 800), (1400, 3100), (245, 225, 190), -1)
    ok, encoded = cv2.imencode(".png", image)
    assert ok

    page = ScreenDetector().detect(make_observation(xml(), screenshot=encoded.tobytes()))

    assert page.page is Page.UNKNOWN


def test_canvas_kitchen_donate_detects_optional_claim():
    image = np.full((3200, 1440, 3), (25, 70, 110), dtype=np.uint8)
    cv2.rectangle(image, (850, 850), (1180, 1020), (20, 40, 245), -1)
    ok, encoded = cv2.imencode(".png", image)
    assert ok

    page = ScreenDetector().detect(make_observation(xml(), screenshot=encoded.tobytes()))

    assert page.page is Page.KITCHEN_DONATE
    assert page.element("claim") is not None


# --- canvas promo scrim overlay --------------------------------------------


def promo_screenshot() -> bytes:
    """The shared promo signature: dark scrim, raised card, centre-bottom X."""
    image = np.full((3200, 1440, 3), 28, dtype=np.uint8)
    cv2.rectangle(image, (200, 860), (1240, 2150), (110, 150, 190), -1)
    cv2.circle(image, (722, 2734), 34, (140, 140, 140), 10)
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    return encoded.tobytes()


def forest_home_xml() -> str:
    shaped = """<?xml version='1.0'?><hierarchy rotation='0'>
      <node text='蚂蚁森林' content-desc='' resource-id='' class='WebView' clickable='false' enabled='true' bounds='[0,0][1440,3200]' />
      <node text='森林广场' content-desc='' resource-id='' class='TextView' clickable='false' enabled='true' bounds='[60,2304][300,2400]' />
      <node text='1 能量雨' content-desc='' resource-id='' class='Button' clickable='true' enabled='true' bounds='[580,2408][848,2724]' />
      <node text='真爱合种' content-desc='' resource-id='' class='Button' clickable='true' enabled='true' bounds='[1104,2408][1368,2724]' />
      <node text='合种' content-desc='' resource-id='' class='Button' clickable='true' enabled='true' bounds='[1364,2408][1440,2724]' />
    </hierarchy>"""
    return shaped


def test_promo_scrim_attaches_dismissible_overlay_to_covered_page():
    page = ScreenDetector().detect(
        make_observation(forest_home_xml(), screenshot=promo_screenshot())
    )

    assert page.page is Page.FOREST_HOME
    assert [overlay.type for overlay in page.overlays] == [OverlayType.PROMO]
    close = page.element("close")
    assert close is not None
    assert close.source == "cv:modal_scrim_close"
    # The page elements stay usable for the recovery re-entry tap.
    assert page.element("love_plant") is not None


def test_promo_scrim_skipped_when_page_has_its_own_modal_controls():
    shaped = """<?xml version='1.0'?><hierarchy rotation='0'>
      <node text='丰收礼包' content-desc='' resource-id='' class='TextView' clickable='false' enabled='true' bounds='[100,200][1300,300]' />
      <node text='立即领取' content-desc='' resource-id='' class='Button' clickable='true' enabled='true' bounds='[400,1500][1040,1700]' />
      <node text='关闭' content-desc='' resource-id='' class='Button' clickable='true' enabled='true' bounds='[656,2670][784,2790]' />
    </hierarchy>"""
    page = ScreenDetector().detect(
        make_observation(shaped, screenshot=promo_screenshot())
    )

    assert page.page is Page.BABA_FARM_HARVEST
    assert page.overlays == ()
    assert page.element("close") is not None


def test_promo_scrim_ignored_without_screenshot():
    page = ScreenDetector().detect(make_observation(forest_home_xml()))
    assert page.page is Page.FOREST_HOME
    assert page.overlays == ()


def test_activity_banner_does_not_steal_the_forest_entry():
    # Real-device layout (run 20260827-035935): a full-width campaign banner
    # whose content-desc contains 蚂蚁森林 sits above the app grid; the entry
    # tap must bind to the icon label, not the banner.
    shaped = """<?xml version='1.0'?><hierarchy rotation='0'>
      <node text='' content-desc='来参加蚂蚁森林十周年啦' resource-id='' class='FrameLayout' clickable='true' enabled='true' bounds='[0,344][1440,1104]' />
      <node text='蚂蚁庄园' content-desc='' resource-id='' class='TextView' clickable='false' enabled='true' bounds='[1177,1300][1373,1353]' />
      <node text='蚂蚁森林' content-desc='' resource-id='' class='TextView' clickable='false' enabled='true' bounds='[343,1564][539,1617]' />
      <node text='' content-desc='消息盒子 蚂蚁森林 能量过期 蚂蚁庄园 饲料待领取' resource-id='' class='FrameLayout' clickable='true' enabled='true' bounds='[32,2121][1408,2567]' />
      <node text='蚂蚁森林' content-desc='' resource-id='' class='TextView' clickable='false' enabled='true' bounds='[160,2269][360,2345]' />
    </hierarchy>"""
    page = ScreenDetector().detect(make_observation(shaped))

    assert page.page is Page.ALIPAY_HOME
    forest = page.element("forest")
    manor = page.element("manor")
    assert forest.center == (441, 1590)
    assert forest.bounds == Bounds(343, 1564, 539, 1617)
    # The message-box sender label must not win over the app icon either.
    assert manor.center == (1275, 1326)


def test_love_plant_canvas_page_binds_water_from_vision_not_tree_fragments():
    # Real-device dump (run 20260827-041113): the 真爱合种 page exposes only
    # Canvas text fragments such as 累计一起攒能量; the 为爱攒能量 pill is an
    # image, and tree text must not steal the water binding.
    shaped = """<?xml version='1.0'?><hierarchy rotation='0'>
      <node text='真爱合种' content-desc='' resource-id='' class='TextView' clickable='false' enabled='true' bounds='[444,84][984,540]' />
      <node text='累计一起攒能量' content-desc='' resource-id='' class='TextView' clickable='false' enabled='true' bounds='[388,536][680,672]' />
      <node text='蚂蚁森林' content-desc='' resource-id='' class='TextView' clickable='true' enabled='true' bounds='[152,203][432,293]' />
    </hierarchy>"""
    image = np.full((3200, 1440, 3), (240, 200, 250), dtype=np.uint8)
    cv2.ellipse(image, (720, 1599), (330, 92), 0, 0, 360, (205, 90, 180), -1)
    ok, encoded = cv2.imencode(".png", image)
    assert ok

    page = ScreenDetector().detect(make_observation(shaped, screenshot=encoded.tobytes()))

    assert page.page is Page.FOREST_LOVE_PLANT
    assert page.element("water").center == (720, 1599)
    assert page.element("water").source == "cv_layout:love_plant_water"


def test_love_plant_amount_modal_is_not_misclassified_as_forest_home():
    page = ScreenDetector().detect(
        make_observation(
            xml("蚂蚁森林", "真爱合种", "你当前有21871g", "喊TA来攒", "攒能量", "+")
        )
    )
    assert page.page is Page.FOREST_LOVE_PLANT
    assert page.element("plus") is not None
    assert page.element("confirm") is not None


def test_friend_hidden_one_click_node_is_ignored_without_visual_button():
    shaped = """<?xml version='1.0'?><hierarchy rotation='0'>
      <node text='蚂蚁森林' content-desc='' resource-id='' class='WebView' clickable='false' enabled='true' bounds='[0,0][1440,3200]' />
      <node text='TA待收的能量' content-desc='' resource-id='' class='TextView' clickable='false' enabled='true' bounds='[40,340][620,470]' />
      <node text='一键收' content-desc='' resource-id='' class='Button' clickable='true' enabled='true' bounds='[1075,1800][1440,1940]' />
    </hierarchy>"""
    image = np.zeros((3200, 1440, 3), dtype=np.uint8)
    cv2.rectangle(image, (260, 560), (450, 760), (20, 80, 240), -1)  # gift bubble
    ok, encoded = cv2.imencode(".png", image)
    assert ok

    page = ScreenDetector().detect(make_observation(shaped, screenshot=encoded.tobytes()))

    assert page.page is Page.FOREST_FRIEND
    assert page.element("one_click") is None


def test_anniversary_campaign_is_not_the_forest_home_or_a_lottery():
    # Real-device dump (run 20260827-052152): the full-screen 10th-anniversary
    # campaign also contains 蚂蚁森林 and 活动剩余时间 in its tree; without the
    # campaign guard it classified as the forest home and every carousel swipe
    # ran on the wrong page.
    shaped = """<?xml version='1.0'?><hierarchy rotation='0'>
      <node text='浇水给蚂蚁森林十年之约林' content-desc='' resource-id='' class='TextView' clickable='false' enabled='true' bounds='[300,2900][1140,2980]' />
      <node text='浇水加入' content-desc='' resource-id='' class='Button' clickable='true' enabled='true' bounds='[200,2570][1240,2760]' />
      <node text='上滑种树得「10周年限定证书」' content-desc='' resource-id='' class='TextView' clickable='false' enabled='true' bounds='[250,3080][1190,3160]' />
      <node text='活动剩余时间 06天11时59分51秒' content-desc='' resource-id='' class='TextView' clickable='false' enabled='true' bounds='[360,1440][1080,1500]' />
      <node text='蚂蚁森林10周年' content-desc='' resource-id='' class='TextView' clickable='false' enabled='true' bounds='[360,420][1080,520]' />
    </hierarchy>"""
    page = ScreenDetector().detect(make_observation(shaped))
    assert page.page is Page.UNKNOWN


def test_anniversary_certificate_page_is_not_forest_home():
    shaped = """<?xml version='1.0'?><hierarchy rotation='0'>
      <node text='蚂蚁森林' content-desc='' resource-id='' class='WebView' clickable='false' enabled='true' bounds='[0,0][1440,3200]' />
      <node text='10周年种树' content-desc='' resource-id='' class='TextView' clickable='false' enabled='true' bounds='[80,170][480,280]' />
      <node text='能量雨' content-desc='' resource-id='' class='TextView' clickable='false' enabled='true' bounds='[500,2700][900,2800]' />
    </hierarchy>"""

    page = ScreenDetector().detect(make_observation(shaped))

    assert page.page is Page.UNKNOWN
