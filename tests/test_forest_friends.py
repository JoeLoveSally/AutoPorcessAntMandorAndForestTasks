"""Friend-traversal guards derived from the 2026-09-23 device failure.

Every captured home frame OCRs the entry button as "找能量>" with a trailing
chevron, so an anchored "^找能量$" pattern found zero targets and the task
aborted before visiting any friend page.
"""

import numpy as np

from domain_data import Element, Observation
from screen_perception import classify
from workflow.forest.daily import FRIEND_ENTRY, Forest


def observation(oid, texts=(), page="forest"):
    elements = [Element(text, bounds, oid) for text, bounds in texts]
    return Observation(oid, 0.0, 1440, 3200, "alipay", elements, page)


def test_friend_entry_button_matches_the_ocr_chevron():
    obs = observation("1", [("找能量>", (1240, 2050, 1400, 2130))])

    assert [e.text for e in obs.find(FRIEND_ENTRY, (0, 0, 1, 1))] == ["找能量>"]


def test_friend_entry_pattern_does_not_match_unrelated_energy_labels():
    obs = observation("1", [
        ("攒能量", (300, 2400, 480, 2480)),
        ("找更多能量", (900, 2900, 1150, 2980)),
    ])

    assert obs.find(FRIEND_ENTRY, (0, 0, 1, 1)) == []


def test_deck_advance_rejects_a_settling_promo_frame_and_accepts_progress():
    # Device evidence (2026-09-23): the deck swallowed a 支付宝会员签到
    # promo card that classified UNKNOWN and held steady for three frames,
    # so swipe progress on such cards can only be a text change.
    promo = observation("1", [
        ("支付宝会员签到", (180, 1400, 700, 1480)),
        ("完成每日签到，可得5g绿色能量", (180, 1500, 900, 1560)),
    ], page="UNKNOWN")
    settled = observation("2", [
        ("支付宝会员签到", (180, 1400, 700, 1480)),
        ("完成每日签到，可得5g绿色能量", (180, 1500, 900, 1560)),
    ], page="UNKNOWN")
    friend = observation("3", [("宝粲的蚂蚁森林", (180, 220, 700, 300))],
                         page="forest_friend")
    treasure = observation("4", [("森林寻宝", (300, 90, 700, 170)),
                                 ("立即抽奖", (600, 1700, 850, 1790))],
                           page="treasure")
    predicate = Forest._deck_advance(Forest._deck_texts(promo))

    assert not predicate(settled)
    assert predicate(friend)
    assert predicate(treasure)
    # Swiping past the last friend overflows onto the energy summary (run
    # 110428, single-friend deck) - it must count as deck progress.
    summary = observation("7", [("找能量共获得", (500, 400, 940, 470)),
                                ("返回森林首页", (400, 3050, 1040, 3140))],
                          page="forest_summary")
    assert predicate(summary)
    # A different unrecognized card passes only when its text is disjoint
    # from the card we swiped away from; a blank transition frame never
    # passes (it would let the loop double-swipe past a friend).
    other_promo = observation("5", [("支付宝花园月卡", (180, 1400, 700, 1480))],
                              page="UNKNOWN")
    assert predicate(other_promo)
    assert not predicate(observation("6", page="UNKNOWN"))


def test_friend_advance_never_reports_progress_on_the_same_card():
    home = observation("1", [("的蚂蚁森林", (180, 220, 700, 300)),
                             ("一键收", (1050, 1800, 1330, 1900))],
                       page="forest_friend")
    next_card = observation("2", [("昂宇的蚂蚁森林", (180, 220, 700, 300))],
                            page="forest_friend")
    identity = tuple(e.text for e in home.find("的蚂蚁森林", (0, 0, 1, .2)))
    texts = Forest._deck_texts(home)
    predicate = Forest._friend_advance(identity, texts)

    # A settling frame of the swiped-away card (same text, UNKNOWN page)
    # must keep waiting - only a wholly different card counts.
    settled = observation("3", [("的蚂蚁森林", (180, 220, 700, 300)),
                                ("一键收", (1050, 1800, 1330, 1900))],
                          page="UNKNOWN")
    assert not predicate(settled)
    assert predicate(next_card)
    promo = observation("4", [("支付宝会员签到", (180, 1400, 700, 1480)),
                              ("完成每日签到，可得5g绿色能量", (180, 1500, 900, 1560))],
                        page="UNKNOWN")
    assert predicate(promo)
    assert not predicate(observation("5", page="UNKNOWN"))  # blank frame
    # Swiping past the last friend lands the energy summary (run 110428,
    # single-friend deck) - a terminal page that must count as advance.
    summary = observation("6", [("找能量共获得", (500, 400, 940, 470)),
                                ("返回森林首页", (400, 3050, 1040, 3140))],
                          page="forest_summary")
    assert predicate(summary)


def test_shared_deck_footer_never_blocks_deck_progress():
    # Device evidence (2026-09-23): every deck card carries the structural
    # 上划找更多能量 footer; the Lam friend card and the 天天能量雨 promo
    # shared it, which made the disjointness check reject real progress
    # until the footer band was filtered out of card texts.
    friend = observation("1", [
        ("Lam的蚂蚁森林", (180, 220, 700, 300)),
        ("上划找更多能量", (400, 3000, 900, 3080)),
    ], page="forest_friend")
    promo = observation("2", [
        ("天天能量雨", (300, 1350, 700, 1450)),
        ("拯救绿色能量", (300, 1580, 700, 1660)),
        ("立即开启", (560, 2660, 800, 2740)),
        ("上划找更多能量", (400, 3000, 900, 3080)),
    ], page="UNKNOWN")
    identity = tuple(e.text for e in friend.find("的蚂蚁森林", (0, 0, 1, .2)))
    predicate = Forest._friend_advance(identity, Forest._deck_texts(friend))

    assert predicate(promo)


def test_energy_summary_gets_its_own_page_id():
    # Device evidence (2026-09-23): the empty deck's summary page shares the
    # forest header, a 找能量 mention (via its title), and even the words
    # 森林寻宝 from the prize strip - only requiring both of its own markers
    # separates it from the forest home and from the treasure ad.
    summary = observation("1", [
        ("蚂蚁森林", (180, 220, 700, 300)),
        ("找能量共获得", (500, 400, 940, 470)),
        ("返回森林首页", (400, 3050, 1040, 3140)),
        ("森林寻宝", (140, 960, 340, 1040)),
        ("去抽奖", (1060, 1230, 1340, 1310)),
    ])
    classify(summary)
    assert summary.page == "forest_summary"

    home = observation("2", [
        ("蚂蚁森林", (180, 220, 700, 300)),
        ("找能量>", (1194, 2061, 1433, 2132)),
    ])
    classify(home)
    assert home.page == "forest"


def test_active_side_reads_the_orange_pill():
    # The active switch label wears an orange pill while the inactive one is
    # neutral gray (demo video f_064/f_093, device 2026-09-23); mean(R-B)
    # over the label box is what separates the sides, because the task list
    # below rotates between periods and cannot.
    orange_left = np.full((3200, 1440, 3), 145, dtype=np.uint8)
    orange_left[300:460, 300:700] = (35, 140, 245)
    labels = [
        Element("仲夏花语装扮", (300, 300, 700, 460), "1"),
        Element("世遗泉州装扮", (760, 300, 1160, 460), "1"),
    ]
    active_left = Observation("1", 0.0, 1440, 3200, "alipay", labels,
                              "lottery", image=orange_left)
    assert Forest._active_side(active_left) == "left"

    orange_right = np.full((3200, 1440, 3), 145, dtype=np.uint8)
    orange_right[300:460, 760:1160] = (35, 140, 245)
    active_right = Observation("2", 0.0, 1440, 3200, "alipay", labels,
                               "lottery", image=orange_right)
    assert Forest._active_side(active_right) == "right"

    neutral = Observation("3", 0.0, 1440, 3200, "alipay", labels,
                          "lottery", image=np.full((3200, 1440, 3), 145,
                                                   dtype=np.uint8))
    assert Forest._active_side(neutral) is None
    one_label = Observation("4", 0.0, 1440, 3200, "alipay", labels[:1],
                            "lottery", image=orange_left)
    assert Forest._active_side(one_label) is None
    no_image = Observation("5", 0.0, 1440, 3200, "alipay", labels, "lottery")
    assert Forest._active_side(no_image) is None
