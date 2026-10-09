from pathlib import Path

import cv2

from domain_data import Element, Observation
from screen_perception import classify


def observation(*texts):
    oid = "classification"
    elements = [
        Element(text, (40, 100 + index * 100, 600, 170 + index * 100), oid)
        for index, text in enumerate(texts)
    ]
    return Observation(oid, 0.0, 1440, 3200, "alipay", elements)


FIXTURES = Path(__file__).parent / "fixtures"


def screen_observation(oid, texts, fixture):
    """Build an observation from a real half-scale device screenshot."""
    image = cv2.imread(str(FIXTURES / fixture))
    assert image is not None, f"missing fixture {fixture}"
    height, width = image.shape[:2]
    elements = [
        Element(text, (int(width * .1), int(height * (.1 + .05 * index)),
                       int(width * .6), int(height * (.12 + .05 * index))), oid)
        for index, text in enumerate(texts)
    ]
    return classify(Observation(oid, 0.0, width, height, "alipay", elements, image=image))


def test_feed_page_is_not_misclassified_as_quiz_from_task_card_title():
    obs = classify(observation("饲料任务", "庄园小课堂", "去答题"))

    assert obs.page == "feed"


def test_quiz_page_without_feed_title_is_still_recognized():
    obs = classify(observation("庄园小课堂", "以下哪个说法正确"))

    assert obs.page == "quiz"


def test_current_diary_page_without_legacy_title_is_recognized():
    obs = classify(observation("全部日记", "上一篇", "下一篇", "贴贴小鸡"))

    assert obs.page == "diary"


def test_family_task_list_is_not_misclassified_as_donation_projects():
    obs = classify(observation(
        "攒亲密度", "每日捐蛋做好事(0/1)", "去捐蛋", "捐爱心蛋，可得10亲密度",
        "请家人吃一顿美食(0/3)",
    ))

    assert obs.page == "family_tasks"


def test_donation_pages_tolerate_observed_ocr_variants():
    detail = classify(observation("本期目标：帮助633人", "项目介绍", "主即捐蛋"))
    current_detail = classify(observation("我的约定", "当前有90颗爱心蛋可捐", "捐爱心蛋"))
    quantity = classify(observation("捐爱心蛋", "1 颗", "当前还有92颗爱心蛋可捐", "主即捐蛋"))
    current_quantity = classify(observation(
        "我的约定", "捐爱心蛋做公益", "/颗", "5颗", "自定义",
        "当前有90颗爱心蛋可捐，1颗爱心蛋=1份爱心", "捐爱心蛋",
    ))
    success = classify(observation("本次捐了1颗爱心蛋", "获取今日份幸运签"))

    assert detail.page == "donate_detail"
    assert current_detail.page == "donate_detail"
    assert quantity.page == "donate_quantity"
    assert current_quantity.page == "donate_quantity"
    assert success.page == "donate_success"


def test_forest_home_is_not_misclassified_from_activity_titles():
    obs = classify(observation(
        "蚂蚁森林", "找能量>", "森林广场", "能量雨", "真爱合种", "今日",
    ))

    assert obs.page == "forest"


def test_forest_child_pages_require_child_specific_evidence():
    love = classify(observation("蚂蚁森林", "真爱合种", "攒能量明细", "已为爱攒100g能量"))
    cooperate = classify(observation("小树苗", "今日排行", "证书", "浇水"))

    assert love.page == "love"
    assert cooperate.page == "cooperate"


def test_real_ad_and_quiz_copy_are_recognized_without_page_title():
    assert classify(observation("看15s视频", "领小鸡饲料")).page == "ad"
    assert classify(observation("滑动浏览得90g", "男士鞋子")).page == "ad"
    assert classify(observation("题目来源一答答星球", "沸水", "温水")).page == "quiz"


def test_known_reward_dialog_is_an_overlay_even_when_base_is_unknown():
    obs = classify(observation("奖励已放入背包", "我知道啦"))

    assert obs.overlays == ["reward"]


def test_seven_day_gift_is_a_dismissible_reward_overlay():
    obs = classify(observation("恭喜获得七日礼包", "立即领取"))

    assert obs.page == "UNKNOWN"
    assert obs.overlays == ["reward"]


def test_family_campaign_is_a_dismissible_overlay():
    obs = classify(observation("欢乐全家桶", "家庭家具上新啦", "去看看", "立即签到"))

    assert obs.page == "family"
    assert obs.overlays == ["reward"]


def test_forest_campaign_modal_is_a_dismissible_overlay_with_close_control():
    obs = screen_observation(
        "popup",
        ["蚂蚁森林", "森林广场", "广东瑰宝季", "升段位守护古树得实物周边", "领皮肤参赛"],
        "forest_campaign_popup.jpg",
    )

    assert obs.page == "forest"
    assert obs.overlays == ["forest_campaign"]
    close = [element for element in obs.elements if element.text == "广告关闭"]
    assert len(close) == 1
    assert abs(close[0].point[0] / obs.width - .5) < .03
    assert abs(close[0].point[1] / obs.height - .868) < .03


def test_home_coupon_modal_is_a_dismissible_overlay_with_close_control():
    # Real-device evidence (2026-09-25, run 41640d): the 广州生活卡 /
    # 支付打车外卖组合券包 card covered the middle of the home's常用 icon
    # row - 蚂蚁森林 and 游戏中心 at x347-816 sit behind it - while the
    # bottom nav stayed readable, so the page still classified alipay,
    # overlays stayed empty, and the forest entry tap found 0. The card
    # carries no close text; the vision circle floats below it.
    obs = screen_observation(
        "home-promo",
        ["扫一扫", "收付款", "出行", "卡包", "金秋丰收节", "红包发放中",
         "广州生活卡", "支付打车外卖组合券包", "400", "蚂蚁庄园", "芭芭农场",
         "荷包", "更多", "常用", "最近消息", "我的"],
        "home_promo.jpg",
    )

    assert obs.page == "alipay"
    assert obs.overlays == ["home_promo"]
    close = [element for element in obs.elements if element.text == "广告关闭"]
    assert len(close) == 1
    assert abs(close[0].point[0] / obs.width - .5) < .03
    assert abs(close[0].point[1] / obs.height - .687) < .03


def test_home_coupon_modal_tall_template_keeps_its_low_close_control():
    # Real-device evidence (2026-09-29, run b8d5e5): the same 广州生活卡
    # slot re-rendered as a taller 领12张 card - its circle sits at .85h,
    # past the 09-25 scan band's .80h edge, so overlays stayed empty and
    # the chain's first anchor OCR read 蚁庄园 (the card's left edge
    # clipped 蚂) before failing with "found 0". A Back press on that
    # frame exits Alipay outright (measured), and the circle still
    # floats centered below the CTA button - the lowest centered circle
    # in the band is the close control on both templates.
    obs = screen_observation(
        "home-promo-0929",
        ["扫一扫", "收付款", "出行", "卡包", "广州生活卡限时放送", "领12张",
         "可爆涨外卖红包", "立即领取", "蚁庄园", "芭芭农", "常用",
         "为你推荐", "推荐", "消息", "我的"],
        "home_promo_0929.jpg",
    )

    assert obs.page == "alipay"
    assert obs.overlays == ["home_promo"]
    close = [element for element in obs.elements if element.text == "广告关闭"]
    assert len(close) == 1
    assert abs(close[0].point[0] / obs.width - .5) < .03
    assert abs(close[0].point[1] / obs.height - .85) < .03


def test_home_coupon_modal_restores_the_page_when_the_dim_hides_the_home_signature():
    # Device evidence (2026-10-09, run 75b3a0): the taller 领12张 card dims
    # the quick-icon row hard enough that OCR dropped 扫一扫 and clipped the
    # grid label 市民中心 to 市民中, so no alipay group-one marker survived
    # and the frame stayed UNKNOWN - the promo never classified as an
    # overlay, and forest.self's entry starved on ensure's Back wait
    # (Postcondition failed: return; page=UNKNOWN). The interstitial only
    # ever sits on the Alipay home, so a verified close circle restores the
    # page identity and the overlay then dismisses normally.
    obs = screen_observation(
        "home-promo-1009",
        ["收付款", "出行", "广州生活卡", "领12张", "可爆涨外卖红包", "立即领取",
         "市民中", "蚁庄园", "芭芭农", "常用", "推荐", "消息", "我的"],
        "home_promo_1009.jpg",
    )

    assert obs.page == "alipay"
    assert obs.overlays == ["home_promo"]
    close = [element for element in obs.elements if element.text == "广告关闭"]
    assert len(close) == 1
    assert abs(close[0].point[0] / obs.width - .5) < .03
    assert abs(close[0].point[1] / obs.height - .855) < .03


def test_clean_home_with_the_banner_copy_is_not_reflagged_after_dismissal():
    # Real-device evidence (2026-09-29, run 4374cb): once the modal closed,
    # the home's own 广州生活卡限时放送 banner kept satisfying the text gate,
    # the second dismissal hunted a circle on the clean page, tapped it,
    # and the chain fell out of the page (postcondition return/UNKNOWN,
    # then Back exited Alipay). The modal's backdrop dims the band left of
    # the card to ~65 gray while this clean frame reads ~220 - the dim
    # gate must keep overlays empty on the very copy that fooled the text.
    obs = screen_observation(
        "home-clean-banner",
        ["扫一扫", "收付款", "出行", "卡包", "广州生活卡限时放送", "点击领取",
         "400元", "市民中心", "蚂蚁庄园", "芭芭农场", "蚂蚁森林", "常用",
         "最近消息", "为你推荐", "推荐", "我的"],
        "home_clean_banner_0929.jpg",
    )

    assert obs.page == "alipay"
    assert obs.overlays == []


def test_home_without_the_coupon_signature_is_never_flagged_from_vision_alone():
    # The circle scan must stay gated on the card's text: the normal home
    # shows round icons in the same lower band and must not be dimmed into
    # an overlay the router would try to close.
    obs = screen_observation(
        "home-clean",
        ["扫一扫", "收付款", "出行", "卡包", "蚂蚁庄园", "芭芭农场",
         "更多", "常用", "最近消息", "我的"],
        "home_promo.jpg",
    )

    assert obs.page == "alipay"
    assert obs.overlays == []


def test_normal_forest_home_is_not_flagged_as_campaign_modal():
    obs = screen_observation(
        "home", ["蚂蚁森林", "森林广场", "找能量", "105g"], "forest_home_normal.jpg",
    )

    assert obs.page == "forest"
    assert obs.overlays == []


def test_forest_home_entrance_badge_does_not_flip_the_page_to_treasure():
    # Real-device evidence (2026-09-22): OCR read the floating entrance badge
    # as a full "森林寻宝" and the single-pattern rule misclassified the home.
    obs = classify(observation("蚂蚁森林", "森林广场", "找能量", "森林寻宝"))

    assert obs.page == "forest"


def test_alipay_home_is_recognized_when_ocr_confuses_the_sweep_label():
    # Real-device evidence (2026-09-22): "扫一扫" came back as "扫一拉".
    obs = classify(observation("扫一拉", "收付款", "蚂蚁庄园", "蚂蚁森林", "我的"))

    assert obs.page == "alipay"


def test_treasure_page_is_recognized_from_child_specific_evidence():
    obs = classify(observation("森林寻宝", "立即抽奖", "浏览赚金币"))

    assert obs.page == "treasure"


def test_ocr_confusing_li_with_zhu_still_recognizes_buttons_and_pages():
    # Real-device evidence (2026-09-20..22): the family page read
    # "立即签到" as "主即签到" and the reward destination read "立即领取"
    # as "主即领取" - 立/主 is a systematic device-OCR confusion.
    assert classify(observation("家庭", "主即签到")).page == "family"
    assert classify(observation("森林寻宝", "主即抽奖", "浏览赚金币")).page == "treasure"
    assert classify(observation("能量雨", "主即开始")).page == "rain"


def test_rain_splash_is_recognized_but_the_plaza_card_stays_forest():
    # Real-device evidence (2026-09-24, run fc6273): opening the 能量雨 card
    # landed on a splash whose headline reads 拯救绿色能量 and whose CTA
    # OCRs as 主即开启 - none of the old round/result markers existed, so the
    # entry tap timed out on page=UNKNOWN. The card label alone on the
    # forest home must keep classifying as forest.
    splash = classify(observation("天天能量雨", "规则", "拯救绿色能量",
                                  "拯救的能量都属于自己", "主即开启"))
    home = classify(observation("蚂蚁森林", "森林广场", "找能量", "能量雨"))

    assert splash.page == "rain"
    assert home.page == "forest"


def test_home_signature_outranks_child_icon_badges():
    # Real-device evidence (2026-09-24, run 386e27): the transient 领肥料
    # badge beside the home's 芭芭农场 icon matched the farm rule, ensure
    # planned Back from the real alipay home, and the back exited the app to
    # the unrecognized launcher (task died waiting for page != UNKNOWN).
    home = classify(observation("扫一扫", "收付款", "我的", "蚂蚁庄园",
                                "芭芭农场", "领肥料"))
    farm = classify(observation("芭芭农场", "施肥", "肥料"))

    assert home.page == "alipay"
    assert farm.page == "farm"


def test_feed_bag_refusal_is_an_overflow_overlay():
    # Device evidence (2026-09-24, run 0ace75): claiming the sign at the
    # 1800g cap pops 饲料袋已满 / 先消耗一些饲料再来领取吧~ with 知道了 /
    # 去帮好友喂食 instead of spec L29's discard-confirm; OCR also misread
    # the title as 饲料袋巴满 on a later frame.
    obs = classify(observation("饲料袋巴满", "先消耗一些饲料再来领取吧~",
                               "去帮好友喂食", "知道了", "饲料任务"))

    assert obs.page == "feed"
    assert "overflow" in obs.overlays


def test_bag_almost_full_confirm_is_an_overflow_overlay():
    # Device evidence (2026-09-25, run 7ecb00): claiming the sign at 60g
    # headroom pops the near-full confirm 饲料袋快满了 / 现在饲料袋只能装下
    # 60g，确认领取吗？ with 去帮好友喂食 + 确认; the untagged dialog left
    # page UNKNOWN with overlays=[] so the daily-sign postcondition
    # starved for 12 captures and timed out.
    obs = classify(observation("饲料袋快满了", "现在饲料袋只能装下60g，确认领取吗？",
                               "去帮好友喂食", "确认", "饲料任务"))

    assert obs.page == "feed"
    assert "overflow" in obs.overlays


def test_donate_detail_page_is_distinguished_from_the_project_list():
    # Device evidence (2026-09-24, run 17b8ff): the project detail page
    # (活动截止时间 / 筹集中 / 爱心值奖励 tabs / bottom-center 去捐蛋) has
    # none of the demo-era markers and classified UNKNOWN, so the
    # first-project postcondition timed out; the list keeps its own rule.
    detail = classify(observation("活动截止时间", "2026/10/25", "筹集中",
                                  "爱心值奖励", "去捐蛋"))
    listing = classify(observation("捐爱心蛋", "我已助力92个项目", "去捐蛋",
                                   "正在筹集第 2间房 70.4%"))

    assert detail.page == "donate_detail"
    assert listing.page == "donate_projects"


def test_manor_home_is_not_misclassified_by_the_fundraising_card():
    # Device evidence (2026-09-24, run 866f6a): the home's 第2间房 card
    # reads 正在筹集中 and the bottom nav always carries 去捐蛋, so the old
    # 筹集中 token matched donate_detail before the manor rule and the
    # ^蚂蚁庄园$ entry postcondition timed out on page=donate_detail.
    obs = classify(observation(
        "蚂蚁庄园", "集齐普通美食", "七日礼包", "装扮", "小鸡乐园",
        "第2间房", "正在筹集中", "好友", "领饲料", "家庭", "去捐蛋", "1800g",
    ))

    assert obs.page == "manor"


def test_quiz_result_view_is_recognized_as_the_quiz_page():
    # Device evidence (2026-09-24, run add4f1): the answer-explanation
    # view drops every list/header marker and carries only the outcome
    # line, so it classified UNKNOWN while the quiz-answer postcondition
    # demanded page == quiz (its text half, 回答错误;, already matched).
    obs = classify(observation(
        "答案： 反射热辐射(我的答案： 吸收热辐射)", "回答错误;",
        "解析", "在常见金属中，银对热辐射的反射能力最强，",
        "去领取饲料",
    ))

    assert obs.page == "quiz"


def test_lottery_panel_after_the_ad_claims_still_classifies():
    # Device evidence (2026-09-24, run 9828af): with the sign card claimed
    # and the finished (3/3) ad row collapsed out of view, the post-claim
    # panel carried only its header, the exchange subtask and the chance
    # counter - none of the original group-2 markers - so ensure read
    # UNKNOWN while standing on the lottery page and the recovery backed
    # straight out of it.
    obs = classify(observation(
        "装扮抽抽乐", "还剩4次机会", "立即抽奖",
        "做任务得机会机会到期失效记得使用哦",
        "消耗饲料换机会", "消耗180g饲料，可换取2次机会",
    ))

    assert obs.page == "lottery"


def test_brush_font_home_survives_the_sweep_label_misread():
    # Device evidence (2026-09-24, run 0ce9ab): the brush-font home read
    # 扫一扫 as 拉一拉 (neither the exact text nor the earlier 扫一拉
    # variant) while 收付款 and 我的 were clean, so all three recognises
    # failed and the recovery's backs walked Alipay out to the launcher.
    observed = classify(observation(
        "拉一拉", "收付款", "出行", "卡包", "市民中心", "医疗健康",
        "蚂蚁庄园", "芭芭农场", "蚂蚁森林", "更多", "最近消息",
        "为你推荐", "推荐", "理财", "视频", "消息", "我的",
    ))

    assert observed.page == "alipay"

    # Worst font case: the whole 扫一扫 family reads as something new -
    # the always-clean home grid label still anchors group one.
    future_variant = classify(observation(
        "收付款", "卡包", "市民中心", "手机营业厅", "支付宝荷包",
        "蚂蚁庄园", "蚂蚁森林", "我的",
    ))

    assert future_variant.page == "alipay"


def test_event_period_kitchen_page_classifies_without_its_title():
    # Device evidence (2026-09-25, run 697d65): six identical stable captures
    # after kitchen-open carry no 小鸡厨房 title (the header reads 秋食风味录)
    # while the spec L77 layout markers - 爱心食材店, 领今日食材, 做美食 - are
    # all OCR'd, so the entry postcondition starved on page=UNKNOWN. The
    # child 献爱心 得食材 page shares 食材 with group two and must keep its
    # own rule.
    obs = classify(observation(
        "秋食风味录", "普通美食 10 /27", "爱心美食已解锁1个", "去施肥领食材>",
        "截止时间：2026.10.31", "爱心食材店", "0肥料", "主人，我出去啦",
        "领今日食材", "做美食", "1440g", "180g", "30g",
    ))
    # Run d9fb5d: the child's own header is 爱心食材店 (the tap target's
    # label repeats as the page title), so without the 献爱心 rule coming
    # first the kitchen group stole it and the store postcond timed out.
    child = classify(observation("献爱心得食材", "规则",
                                 "捐赠获得的食材将自动计入食材库不会过期哦",
                                 "爱心食材店", "领取每日限量食材", "领10g食材"))

    assert obs.page == "kitchen"
    assert child.page == "ingredient_shop"


def test_farm_promo_card_is_a_dismissible_overlay_with_close_control():
    # Real-device evidence (2026-09-26, run 7d8d95): the timed 领3000肥料
    # card pops over the freshly opened 做任务集肥料 drawer a couple of
    # beats after the auto-jump. Its backdrop blur erases the drawer
    # header, the frame classifies farm from the nav title and card text,
    # and the router has no farm -> farm_tasks route (the drawer opens
    # only via the jump) - the card must close through its circle.
    obs = screen_observation(
        "farm-promo",
        ["支付宝·芭芭农场", "肥", "肥", "肥", "领3000肥料",
         "玩寻道大千砍树20次即得", "限时翻倍", "领肥料"],
        "farm_promo.jpg",
    )

    assert obs.page == "farm"
    assert obs.overlays == ["farm_promo"]
    close = [element for element in obs.elements if element.text == "广告关闭"]
    assert len(close) == 1
    assert abs(close[0].point[0] / obs.width - .50) < .03
    assert abs(close[0].point[1] / obs.height - .742) < .03


def test_farm_entry_welcome_card_is_never_flagged_from_vision_alone():
    # The entry welcome card (auto-claim countdown) carries no 领N肥料
    # title; without the text gate its round sacks sit in the same lower
    # band as the promo close circle and would be dimmed into a phantom
    # overlay the router keeps trying to close.
    obs = screen_observation(
        "farm-welcome",
        ["支付宝·芭芭农场", "欢迎来到芭芭农场", "1100肥料待领取", "500", "600",
         "肥", "肥", "明日肥料", "每日签到", "大额肥料", "签到领肥3s"],
        "farm_welcome.jpg",
    )

    assert obs.page == "farm"
    assert obs.overlays == []


def test_farm_welcome_card_label_row_never_fires_the_reward_overlay():
    # Device evidence (2026-09-27, run 80393d): the welcome card's own
    # label row (明日肥料|获得奖励|每日签到) OCRs joined as
    # 明日肥料获得奖励每日答到, which fired the reward family; the dismissal's
    # Back fallback then left the farm one beat before its countdown-driven
    # auto-jump (the drawer lands with the card still on screen, run
    # 9d8f76) and the jump wait starved on page=feed. The card is
    # self-managing state: its frames must stay overlay-free.
    obs = screen_observation(
        "farm-welcome",
        ["支付宝·芭芭农场", "欢迎来到芭芭农场", "明日肥料获得奖励每日签到",
         "2100肥料待领取", "肥料+2100", "还差2次领肥"],
        "farm_welcome.jpg",
    )

    assert obs.page == "farm"
    assert "reward" not in obs.overlays


def test_farm_gift_popup_is_a_dismissible_overlay_with_close_control():
    # Device evidence (2026-09-30, run f427d5): the daily fertilize's
    # 丰收礼包 popup renders a bare circle bottom-center under its CTA;
    # the flow's Android Back from it left the whole 芭芭农场 container
    # for feed (spec L67 closes it with the X), so the circle must be
    # found while the popup is still up - pending state included, since
    # the claim tap needs the classified overlay to ride through.
    obs = screen_observation(
        "farm-gift-pending",
        ["支付宝·芭芭农场", "丰收礼包待领取", "2027.12.3前可领取肥料礼包",
         "肥料", "立即领取"],
        "farm_gift_pending.jpg",
    )

    assert obs.page == "farm"
    assert obs.overlays == ["farm_gift"]
    close = [element for element in obs.elements if element.text == "广告关闭"]
    assert len(close) == 1
    assert abs(close[0].point[0] / obs.width - .50) < .03
    assert abs(close[0].point[1] / obs.height - .726) < .03


def test_farm_gift_popup_survives_the_ocr_半_misread_on_the_claimed_state():
    # Same popup after the claim: OCR flipped the title's 丰 to 半 on
    # frames it read correctly a beat earlier (0157 against 0155), so the
    # gate must accept the [半丰] character class or the claimed state
    # (the only one the flow closes from) never classifies.
    obs = screen_observation(
        "farm-gift-claimed",
        ["支付宝·芭芭农场", "半收礼包已领取", "600肥料已发放",
         "肥料", "点此逛一逛再赚1000肥料>"],
        "farm_gift_claimed.jpg",
    )

    assert obs.page == "farm"
    assert obs.overlays == ["farm_gift"]
    close = [element for element in obs.elements if element.text == "广告关闭"]
    assert len(close) == 1
    assert abs(close[0].point[1] / obs.height - .726) < .03


def test_costume_promo_modal_is_a_dismissible_overlay_with_close_control():
    # Device evidence (2026-10-09, run e81885): the 秋日美满 modal dimmed
    # the manor (left band gray 34 against a clean home's 172) while the
    # bottom nav stayed readable, so the page kept classifying manor and
    # donate_egg's 家庭 tap was swallowed by the modal's full-screen touch
    # layer across eight refreshes. Its close circle carries no OCR text -
    # the scan must find it dead-centered at .766h.
    obs = screen_observation(
        "manor-costume",
        ["蚂蚁庄园", "秋日美满", "主题装扮来拉", "NBA限定装扮", "活力上线",
         "去抽装扮", "一键连抽", "领红包", "好友", "领饲料", "家庭", "去捐蛋",
         "1560g"],
        "manor_costume_modal.jpg",
    )

    assert obs.page == "manor"
    assert obs.overlays == ["costume_promo"]
    close = [element for element in obs.elements if element.text == "广告关闭"]
    assert len(close) == 1
    assert abs(close[0].point[0] / obs.width - .50) < .03
    assert abs(close[0].point[1] / obs.height - .766) < .03


def test_costume_copy_on_an_undimmed_manor_home_never_fires_the_scan():
    # The campaign copy could outlive the modal as scene decoration after
    # the close; the dim band (34 modal against 172 clean) is the gate that
    # keeps a bright home from ever launching the circle scan.
    obs = screen_observation(
        "manor-costume-clean",
        ["蚂蚁庄园", "秋日美满", "主题装扮来拉", "去抽装扮", "领饲料", "家庭"],
        "manor_home_clean.jpg",
    )

    assert obs.page == "manor"
    assert "costume_promo" not in obs.overlays


def test_farm_fertilize_home_is_never_flagged():
    # The settled fertilize home (施肥 + 主即领肥, run f427d5 frame 0154)
    # carries no 丰收礼包 title; the scan band there produced no circle
    # in any of the run's clean frames, so this state stays overlay-free
    # and the fertilize tap keeps finding its target.
    obs = screen_observation(
        "farm-fertilize-home",
        ["支付宝·芭芭农场", "施肥", "肥料45938", "主即领肥", "明日7点可领"],
        "farm_fertilize_home.jpg",
    )

    assert obs.page == "farm"
    assert obs.overlays == []


def test_alipay_update_prompt_is_dismissible_from_its_title_anchor():
    # Device evidence (2026-10-08, run 1ed031): the native 版本更新 prompt
    # clipped the home quick icons to 庄园/芭芭/市民 (蚂蚁 sat behind the
    # card) and ^蚂蚁庄园$ found 0 while the page still read alipay. The
    # card dims the backdrop, so the home promo scan's text and dim gates
    # pass on this frame too - only its circle hunt misses - and the
    # prompt rule must run first with its own title-anchored control.
    obs = screen_observation(
        "alipay-update-prompt",
        ["广州√", "医保", "搜索", "扫一扫", "收付款", "出行", "卡包",
         "广州生活卡", "领12张红包", "版本更新",
         "支付宝最新尝鲜版来啦，启动更快，", "使用更流畅。马上更新吧!",
         "立即更新", "市民", "庄园", "芭芭", "我的"],
        "alipay_update_prompt.jpg",
    )

    assert obs.page == "alipay"
    assert obs.overlays == ["app_update"]
    close = [element for element in obs.elements if element.text == "广告关闭"]
    assert len(close) == 1
    title = obs.find("版本更新")[0]
    cx = int((title.bounds[0] + title.bounds[2]) / 2 + 465)
    cy = int((title.bounds[1] + title.bounds[3]) / 2 - 463)
    assert close[0].point == (cx, cy)


def test_clean_alipay_home_is_never_flagged_as_update_prompt():
    # The launch frame before the prompt pops reads the full 蚂蚁庄园
    # grid with its banner copy; without the update copy there is nothing
    # to anchor a close on, so the home must stay overlay-free.
    obs = screen_observation(
        "alipay-home-clean",
        ["广州√", "支付宝会员", "搜索", "扫一扫", "收付款", "出行", "卡包",
         "广州生活卡最高领", "蚂蚁庄园", "芭芭农场", "蚂蚁森林", "更多", "我的"],
        "alipay_home_clean.jpg",
    )

    assert obs.page == "alipay"
    assert obs.overlays == []


def test_farm_home_bottom_entry_classifies_as_farm_and_fires_no_reward():
    # Device evidence (2026-10-08, run 95ece9): this week's farm home
    # carries a bottom entry bar reading 做任务集肥料 (index-placed at
    # .96h by this helper, mirroring the device's [535,3053,908,3117]);
    # the bare-text rule took it for the drawer (header at .34h) so
    # drawer-close's page=="farm" postcondition could never hold, and its
    # wait then let the CTA-less reward fallback Back the container out to
    # feed. The challenge card's 参与施肥挑战赢大额奖励 also matches reward's
    # 施肥挑战 arm - neither may classify here.
    obs = screen_observation(
        "farm-home-bottom-entry",
        ["支付宝·芭芭农场", "合种>", "种摇钱树", "施肥赢3000肥料", "开始",
         "参与施肥挑战赢大额奖励", "限时挑战", "04:33", "还差了次领肥",
         "14级", "苹果2箱", "一键施肥5次", "领600肥", "施肥",
         "农场乐园", "肥料33410", "领肥料", "做任务集肥料"],
        "farm_home_bottom_entry.jpg",
    )

    assert obs.page == "farm"
    assert obs.overlays == []


def test_drawer_header_at_the_top_stays_farm_tasks():
    # The fixup only fires for markers living along the bottom edge: the
    # drawer's header rides the top of the viewport and its list content
    # scrolls only upward, so a top-anchored marker stays the drawer.
    obs = screen_observation(
        "drawer-header-top",
        ["做任务集肥料", "支付宝·芭芭农场", "每日签到", "蚂蚁庄园小鸡肥料",
         "领取"],
        "farm_home_bottom_entry.jpg",
    )

    assert obs.page == "farm_tasks"


def test_farm_claim_toast_is_not_a_reward_overlay():
    # The 肥料+2100 claim toast OCRs beside a 获得奖励 label (run 95ece9,
    # frame 0011) - content, not a popup; the fallback Back for it would
    # walk the container out to feed.
    obs = screen_observation(
        "farm-claim-toast",
        ["支付宝·芭芭农场", "施肥", "肥料", "获得奖励", "肥料+2100"],
        "farm_fertilize_home.jpg",
    )

    assert obs.page == "farm"
    assert "reward" not in obs.overlays


def test_farm_reward_popups_with_a_close_path_stay_classified():
    # The spec L67 forest cross-promo (直接关闭 through the fallback Back
    # on its modal) and CTA result popups keep their reward branches.
    for texts in (["支付宝·芭芭农场", "施肥", "肥料", "去蚂蚁森林收能量"],
                  ["支付宝·芭芭农场", "施肥", "肥料", "开心收下"]):
        obs = screen_observation("farm-reward-popup", texts,
                                 "farm_fertilize_home.jpg")

        assert obs.page == "farm"
        assert "reward" in obs.overlays


def test_kitchen_result_modal_classifies_from_the_event_header():
    # Device evidence (2026-09-27, run a520fb): the cook-result modal hides
    # the store button and the claim row reads plain 领食材 (no 今日) while
    # the new pity banner displaces 普通美食 - only the event header remains,
    # page=UNKNOWN made back() refuse with "Cannot act on unknown page" and
    # the finished cook could not close. Group two keeps the rule tied to
    # kitchen content (做美食 button + 食材 texts both show through).
    obs = classify(observation(
        "秋食风味录", "5次内必解锁一道新的美食哦", "食材",
        "橄榄烤彩椒制作成功", "喂食小鸡立产0.15颗爱心蛋", "新解锁+1",
        "查看图鉴", "厨余生成了58肥料", "领食材", "做美食",
    ))

    assert obs.page == "kitchen"


def test_member_home_classifies_and_the_feed_row_stays_feed():
    # Device evidence (2026-09-27, run e7673b): the 支付宝会员 home under
    # its widget-promo layer classified UNKNOWN and browse()'s landing wait
    # starved. The feed row copy (去支付宝会员签到 + 签到得积分换好礼) carries
    # both 会员 and 积分, so group one must be promo/structure text the row
    # never has - a misfire there would flip every feed frame.
    member = classify(observation(
        "1356", "领积分兑好礼更方便", "添加会员小组件到桌面",
        "尊敬的铂金会员", "待领积分", "188", "点击添加",
    ))
    feed_row = classify(observation(
        "蚂蚁庄园", "饲料任务", "去支付宝会员签到",
        "和小鸡一起签到得积分换好礼，还可获赠", "去完成",
    ))

    assert member.page == "member"
    assert feed_row.page == "feed"


def test_forest_task_row_browsing_the_member_center_is_not_member():
    # Device evidence (2026-09-24, run 699443): the forest task list's
    # 逛支付宝会员中心 browse row contains 会员中心 as a substring, which
    # satisfied member group one on 10 frames in a replay - the frame must
    # keep its pre-existing non-member outcome.
    obs = classify(observation(
        "蚂蚁森林", "能量", "我的活力值", "森林寻宝",
        "逛支付宝会员中心", "逛一逛", "逛高德地图领红包", "抽/次",
    ))

    assert obs.page != "member"


def test_lottery_panel_after_the_sign_card_leaves_still_classifies():
    # Device evidence (2026-09-28, run 84c8a6): the sign tap removes the
    # 每日签到 card AND its 去逛逛 button from the panel in one refresh
    # (frames 0074-0078 vs 0079+), leaving only the market row title and
    # the flipped chance badge - none of the original group-2 anchors - so
    # the frame fell to UNKNOWN and starved lottery-sign's postcondition
    # on a sign that DID succeed. A 5774-frame replay shows the two added
    # anchors lift exactly the 25 such UNKNOWN frames and steal nothing.
    panel = classify(observation(
        "规则", "仲夏花语装扮", "还有1次机会22天后清零", "立即抽奖",
        "找能量>", "明细>", "去森林市集逛一逛(0/2)",
        "浏览市集15S，可得1次机会", "去寻宝公益林浇水",
        "单次浇水≥15g可得1次抽奖次数",
    ))

    assert panel.page == "lottery"
