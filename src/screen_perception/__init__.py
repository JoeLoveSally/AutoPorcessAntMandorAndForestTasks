from __future__ import annotations

import json
import re
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import asdict

import cv2
import numpy as np

from domain_data import AutomationError, Element, Observation
from screen_perception.vision import manor_diary_entry

# More specific child pages precede parent pages whose title remains visible.
# Device OCR systematically confuses 立 with 主 ("主即签到" on the family page
# and "主即领取" on the reward destination, observed 2026-09-20..22), so every
# 立即* button matches the [立三主]即* class.
PAGE_RULES = (
    # The home's quick-action row (扫一扫 + 收付款) together with the 我的 tab
    # is a signature no H5 child page carries, so home outranks every child
    # rule: device evidence (2026-09-24, run 386e27) - a transient 领肥料 icon
    # badge beside the home's 芭芭农场 icon satisfied the farm rule mid-run,
    # ensure planned Back from a page that was really the alipay home, the
    # back exited the app to the unrecognized launcher, and the task timed
    # out waiting for page != UNKNOWN. Real-device evidence (2026-09-22):
    # OCR reads the quick-action label as "扫一拉", accepted as a variant.
    # Run 0ce9ab (2026-09-24): the brush-font home read it as "拉一拉"
    # (neither prior variant) while 收付款 and 我的 stayed clean, all three
    # recognises failed and the recovery's backs again walked Alipay out
    # to the launcher - so the always-clean home grid label 市民中心 now
    # anchors group one whatever the brush glyphs OCR into.
    ("alipay", ("扫一扫|扫一拉|拉一拉|市民中心", "收付款|收钱", "我的")),
    ("donate_success", ("捐蛋成功|本次捐了|主人，你已成功向|贡献了.*份爱心",)),
    ("donate_quantity", ("捐爱心蛋|选择捐蛋数量", r"选择捐蛋数量|^[1/]\s*颗$|^5颗$|^自定义$")),
    # Device evidence (2026-09-24, run 17b8ff): the real project detail page
    # carries 活动截止时间 / 筹集中 / 爱心值奖励 and a bottom-center 去捐蛋;
    # none of the demo-era markers exist, so it classified UNKNOWN while the
    # first-project postcondition waited. The project list cannot match this
    # rule (no group-1 marker), and group2 keeps the demo-era labels.
    # The 筹集中 token is deliberately absent (run 866f6a): the manor home's
    # 第2间房 card reads 正在筹集中 and the bottom nav always carries 去捐蛋,
    # so the home classified donate_detail and the ^蚂蚁庄园$ entry
    # postcondition timed out; the detail keeps its five page-specific
    # group-1 markers, every device frame of it carrying at least one.
    ("donate_detail", ("活动截止时间|爱心值奖励|项目介绍|本期目标|我的约定",
                       "[立三主]即捐蛋|捐爱心蛋|去捐蛋")),
    ("family_tasks", ("攒亲密度", "请家人|每日捐蛋|帮家人")),
    ("donate_projects", ("捐爱心蛋", "我已助力|乡村儿童|待帮助", "去捐蛋")),
    ("family", ("欢乐金家桶|家庭", "[立三主]即签到|攒亲密度|我的奖励")),
    ("diary", ("小鸡日记|全部日记", "贴贴小鸡|明日再来")),
    # Parent task-list pages must precede child pages whose names also appear
    # as task-card titles on the parent page.
    ("feed", ("饲料任务",)),
    # The answer-explanation view (run add4f1, 2026-09-24) drops every
    # list/header marker - 庄园小课堂/题目来源/答答星球 are all gone - and
    # carries only the outcome line (回答错误;, parallel 回答正确 for the
    # right pick) plus the result page's 去领取饲料, so it classified
    # UNKNOWN while the quiz-answer postcondition demanded page == quiz.
    ("quiz", ("庄园小课堂|题目来源|答答星球|回答错误|回答正确|去领取饲料",)),
    # Device evidence (2026-09-25, run 697d65): the event period's kitchen
    # page drops the 小鸡厨房 title from OCR - six identical stable captures
    # after kitchen-open, title slot empty while the header shows 秋食风味录
    # - so the entry postcond timed out with page=UNKNOWN even though 做美食
    # / 领今日食材 / the spec L77 fixed 爱心食材店 entrance were all OCR'd.
    # Accept those layout markers as group one. Run d9fb5d then showed the
    # child 献爱心 得食材 page carries its own 爱心食材店 store header, so
    # this rule stole the child whenever it was matched first - the child's
    # 献爱心 group comes ahead of it now, and the kitchen main page itself
    # never carries 献爱心.
    ("ingredient_shop", ("献爱心", "食材")),
    # Device evidence (2026-09-27, run a520fb): the cook-result modal keeps
    # only the event header - the new pity banner (5次内必解锁一道新的美食哦)
    # displaces 普通美食, the claim row OCRs as 领今日-free 领食材 and the
    # store button is covered - so the frame classified UNKNOWN and back()
    # refused with "Cannot act on unknown page" while the modal was up.
    # A scan of 09-24..09-27 frames shows 秋食风味录 only ever on kitchen
    # and kitchen-modal frames (76 kitchen + 36 modal, zero other pages).
    ("kitchen", ("小鸡厨房|爱心食材店|领今日食材|秋食风味录", "做美食|食材")),
    ("farm_tasks", ("做任务集肥料",)),
    ("farm", ("芭芭农场", "施肥|肥料")),
    # Device evidence (2026-09-24, run 9828af): once the sign card was
    # claimed and the finished (3/3) ad row collapsed out of view, the
    # post-claim panel still exposed 装扮抽抽乐 / 还剩N次机会 / the exchange
    # subtask, yet none of the original group-2 markers survived - ensure
    # read UNKNOWN while standing on the page and the recovery started
    # backing out of it (feed -> farm spiral) until the unknown-page guard
    # refused the blind Back. Keep the original markers and add the ones
    # the completed panel still carries.
    # Device evidence (2026-09-28, run 84c8a6): the sign tap removes the
    # 每日签到 card AND its 去逛逛 button from the panel in one refresh
    # (frames 0074-0078 vs 0079+), leaving the market row title and the
    # flipped chance badge as the only surviving panel markers - none of
    # the original group-2 anchors - so the post-sign frames classified
    # UNKNOWN and starved lottery-sign's postcondition on a sign that HAD
    # succeeded. Both additions exist on both sides of the tap
    # (去森林市集逛一逛(0/2); 还有0次机会 -> 还有1次机会22天后清零).
    ("lottery", ("[立三主]即抽奖",
                 ("每日签到|抽奖机会|去逛逛|森林市集|杂货铺|消耗饲料换机会|"
                  "还剩\\d+次机会|还有\\d+次机会|装扮抽抽乐|做任务得机会"))),
    # The forest home carries a floating "森林寻宝" entrance badge that OCR
    # sometimes reads in full, so the badge text alone is not child evidence;
    # the child page itself exposes the lottery entry the workflow taps next.
    ("treasure", ("森林寻宝", "[立三主]即抽奖")),
    # Device evidence (2026-09-24, run fc6273): the freshly opened page OCRs
    # its headline as "拯救绿色能量" and its CTA as "主即开启" (the known 立/主
    # confusion; spec line 103 calls the button 立即开始) while none of the
    # round/result markers exist yet - entry, round start and the gift return
    # must all land on "rain".
    ("rain", ("能量雨", "[立三主]即开[始启]|拯救.*能量|送TA机会|再来一次|今日已|获得|明日")),
    ("forest_friend", ("的蚂蚁森林", "一键收|找能量|找更多能量|收取TA")),
    # Device evidence (2026-09-23): with every friend already harvested, the
    # 找能量 button opens this summary page instead of the deck. It shares
    # the forest's header and a 找能量 mention, so both of its own markers
    # (title and exit button) are required to give it a page id of its own.
    ("forest_summary", ("找能量共获得", "返回森林首页")),
    ("forest", ("蚂蚁森林", "森林广场|找能量")),
    ("love", ("真爱合种", "为爱攒能量|攒能量明细|已为爱攒|累计一起攒")),
    ("cooperate", ("小树苗|合种", "浇水", "证书|今日排行|说点啥")),
    ("manor_friend", ("的蚂蚁庄园", "蹭吃|雇佣|带小鸡")),
    ("manor", ("蚂蚁庄园", "领饲料", "家庭")),
    # Device evidence (2026-09-27, run e7673b): backing out of the member
    # task center lands the 支付宝会员 home under a widget-promo layer
    # (领积分兑好礼更方便 / 添加会员小组件到桌面 / 待领积分) that classified
    # UNKNOWN, so browse()'s landing wait starved on page=UNKNOWN. Group
    # one is promo/structure text the feed row never carries - the row's
    # 去支付宝会员签到 must not flip a feed frame - and group two keeps the
    # rule on the member home even when the promo headline rotates. Bare
    # 会员中心 is banned as an anchor: run 699443's forest task list row
    # 逛支付宝会员中心 contains it as a substring (10 false-positive frames
    # in a HEAD-vs-worktree replay of 09-24..27 evidence).
    ("member", ("待领积分|领积分兑好礼|添加会员小组件", "会员|积分")),
    ("ad", ("可领饲料|可领奖励|浏览完成|任务.*浏览|浏览.*秒|滑动.*浏览|看15s视频",)),
)


def close_circle_element(observation: Observation, circle, crop_origin: tuple[int, int]) -> Element:
    """Convert a detected circle in a cropped image to full-screen coordinates.

    A cropped-image center MUST NOT be sent directly to ADB as a screen tap.
    """
    cx, cy, radius = (int(value) for value in circle)
    left, top = crop_origin
    x, y = left + cx, top + cy
    bounds = (max(0, x - radius), max(0, y - radius),
              min(observation.width, x + radius), min(observation.height, y + radius))
    if not (bounds[0] < bounds[2] and bounds[1] < bounds[3]):
        raise AutomationError("Invalid overlay close target", "BOUNDS")
    return Element("广告关闭", bounds, observation.id, "vision.close_circle", 0.9)


def classify(observation):
    for name, patterns in PAGE_RULES:
        if all(observation.has(p) for p in patterns):
            observation.page = name
            break
    # Device evidence (2026-10-08, run 95ece9): this week's farm home grew
    # a bottom entry bar reading 做任务集肥料 ([535,3053,908,3117], .95h)
    # while the drawer's own header anchors at .34h ([535,1090,908,1154],
    # and list content only scrolls upward from there), so the bare-text
    # farm_tasks rule took the closed-drawer home for the drawer and
    # drawer-close's page=="farm" postcondition could never hold. Only a
    # marker riding the top of the viewport is the drawer; one living
    # exclusively along the bottom edge is the home's entry bar, and the
    # farm rule then decides the frame.
    if observation.page == "farm_tasks":
        markers = observation.find("做任务集肥料")
        if (markers
                and all(marker.point[1] > observation.height * .8
                        for marker in markers)
                and observation.has("芭芭农场")
                and observation.has("施肥|肥料")):
            observation.page = "farm"
    # Both feed-claim blockers count as "overflow": spec L29's discard-confirm
    # (超过上限) and the zero-headroom refusal observed 2026-09-24 (run
    # 0ace75) 饲料袋已满 / 先消耗一些饲料再来领取吧~ - OCR also misreads 已 as 巴.
    # The near-full confirm (2026-09-25, run 7ecb00) 饲料袋快满了 /
    # 只能装下60g，确认领取吗？ is the same bag-capacity family.
    for name, pattern in (("guess", "猜价格|猜价"),
                          ("overflow", ("超过.*上限|超出.*上限|饲料袋[已巴]满|先消耗一些饲料"
                                       "|饲料袋快满|只能装下")),
                          ("reward", "获得奖励|恭喜获得七日礼包|家庭家具上新啦|开心收下|我知道啦|去蚂蚁森林收能量|施肥挑战"),
                          ("confirm", "确认喂食|选择美食|兑换确认")):
        if name == "reward" and observation.has(r"欢迎来到芭芭农场"):
            # Device evidence (2026-09-27, run 80393d): the farm entry
            # welcome card's own label row (明日肥料|获得奖励|每日签到) OCRs
            # joined as 明日肥料获得奖励每日答到 and fired the reward overlay;
            # the reward dismissal's Back fallback left the farm one beat
            # before the countdown-driven auto-jump (09-25, run 9d8f76 shows
            # the drawer landing while the card is still on screen) and the
            # jump wait then starved on page=feed. The card is self-managing
            # state, never a dismissible reward.
            continue
        if (name == "reward"
                and observation.page in ("farm", "farm_tasks")
                and not observation.has("开心收下|我知道啦|去蚂蚁森林收能量")):
            # Device evidence (2026-10-08, run 95ece9): the farm home's
            # persistent 参与施肥挑战赢大额奖励 card (new this week; its line
            # matches the 施肥挑战 arm) and the transient 肥料+2100 claim
            # toast - which OCRs beside a 获得奖励 label row, on drawer
            # frames too - are content or self-managing state, never
            # dismissible popups. Classifying them sent dismiss() down its
            # CTA-less fallback and one Back walked the whole 芭芭农场
            # container out to feed (frame 0037 -> 0038, killing
            # drawer-close's postcondition hunt). Real reward popups inside
            # this container keep their CTA or the spec L67 forest
            # cross-promo line (去蚂蚁森林收能量, closed directly), and the
            # 施肥挑战 popup needs no overlay: daily.py reads it off the
            # text and backs out itself (L352).
            continue
        if observation.has(pattern):
            observation.overlays.append(name)
    # Homepage ads may obscure the content while leaving the bottom navigation
    # text visible. Locate the close circle only within a known modal context.
    if observation.page == "manor" and observation.image is not None:
        image = observation.image
        h, w = image.shape[:2]
        center = image[int(h * .25):int(h * .86), int(w * .08):int(w * .92)]
        if center.size and float(center.mean()) < 160 and observation.has("[立三主]即领现金|玩游戏得现金"):
            # Current Manor campaigns place the close control just below the
            # card (around 76% screen height). Keep this region tight so round
            # artwork inside the campaign cannot be mistaken for the close.
            x0, y0 = int(w * .30), int(h * .70)
            close_region = image[y0:int(h * .84), x0:int(w * .70)]
            if close_region.size:
                gray = cv2.cvtColor(close_region, cv2.COLOR_BGR2GRAY)
                circles = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, 1.2, 80,
                                           param1=100, param2=45,
                                           minRadius=max(20, int(w * .025)),
                                           maxRadius=max(40, int(w * .06)))
                if circles is not None:
                    observation.overlays.append("manor_ad")
                    expected = (close_region.shape[1] / 2, close_region.shape[0] * .47)
                    circle = min(
                        circles[0],
                        key=lambda item: (item[0] - expected[0]) ** 2 + (item[1] - expected[1]) ** 2,
                    )
                    observation.elements.append(close_circle_element(observation, circle, (x0, y0)))
    # Full-screen campaign modals dim the forest scene behind a dark scrim
    # while the artwork in the middle stays bright (real-device evidence
    # 2026-09-21: scrim bands ~88 gray vs ~195 on the normal home), and the
    # close control is a circle just below the bottom center.
    if observation.page == "forest" and observation.image is not None:
        image = observation.image
        h, w = image.shape[:2]
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
        bands = [gray[int(h * a):int(h * b), int(w * c):int(w * d)]
                 for a, b, c, d in ((.30, .70, .02, .16), (.30, .70, .84, .98),
                                    (.12, .18, .02, .98), (.60, .72, .02, .98))]
        ring = float(np.mean([band.mean() for band in bands if band.size]))
        center = gray[int(h * .38):int(h * .62), int(w * .30):int(w * .70)]
        center_mean = float(center.mean()) if center.size else 0.0
        if ring < 115 and center_mean > ring + 25:
            x0, y0 = int(w * .28), int(h * .78)
            crop = gray[y0:int(h * .93), x0:int(w * .72)]
            if crop.size:
                blurred = cv2.GaussianBlur(np.clip(crop, 0, 255).astype(np.uint8), (5, 5), 1.2)
                circles = cv2.HoughCircles(blurred, cv2.HOUGH_GRADIENT, 1.2, 80,
                                            param1=100, param2=45,
                                            minRadius=max(20, int(w * .02)),
                                            maxRadius=max(40, int(w * .05)))
                if circles is not None:
                    expected = (crop.shape[1] / 2, crop.shape[0] * .58)
                    circle = min(
                        circles[0],
                        key=lambda item: (float(item[0]) - expected[0]) ** 2
                        + (float(item[1]) - expected[1]) ** 2,
                    )
                    distance = ((float(circle[0]) - expected[0]) ** 2
                                + (float(circle[1]) - expected[1]) ** 2) ** .5
                    if distance <= w * .07:
                        observation.overlays.append("forest_campaign")
                        observation.elements.append(close_circle_element(observation, circle, (x0, y0)))
    # Device evidence (2026-10-08, run 1ed031): a native 版本更新 prompt
    # (支付宝最新尝鲜版) covers the alipay home center on the first launch
    # after a week idle - its card clips the quick-icon labels to 庄园/
    # 芭芭/市民 (the 蚂蚁 halves sit behind the card), the page still
    # classifies alipay from the exposed header, and ^蚂蚁庄园$ found 0
    # across three frames. The card dims the backdrop (left band 82.5
    # against a clean home's 172) so the home promo scan's gates would
    # pass too - only its circle hunt misses - and this rule therefore
    # runs first: dismissing the prompt undims the band that scan keys
    # on. The prompt's own top-right X carries no ring (HoughCircles
    # returns only the card's corner arcs), so gate on the update copy
    # and anchor the close on the OCR'd title: 版本更新 held
    # [564,1562,872,1640] with the X centered at (1183,1138) - title
    # center + (+465,-463), frame 0003. 立即更新 would start the app
    # update and Back walks Alipay out, so the X is the only safe
    # control; the overlay-removal postcondition guards the offset.
    if observation.page == "alipay" and observation.has("版本更新") \
            and observation.has("支付宝最新尝鲜版"):
        titles = observation.find("版本更新")
        if len(titles) == 1:
            title = titles[0]
            cx = int((title.bounds[0] + title.bounds[2]) / 2 + 465)
            cy = int((title.bounds[1] + title.bounds[3]) / 2 - 463)
            observation.overlays.append("app_update")
            observation.elements.append(Element(
                "广告关闭", (cx - 60, cy - 60, cx + 60, cy + 60),
                observation.id, "vision.ocr_anchor", 0.9))
    # Alipay-home interstitials (real-device evidence 2026-09-25, run
    # 41640d): the 广州生活卡 / 支付打车外卖组合券包 coupon card covered the
    # middle of the常用 icon row - 蚂蚁森林 and 游戏中心 sit behind it -
    # while the bottom nav stayed readable, so the page still classified
    # alipay, overlays stayed empty, and the forest entry tap found 0. The
    # card carries no close text: its floating circle sits below the card.
    # The circle travels with the card template: .687h on 09-25, but the
    # 09-29 re-promotion (领12张, run b8d5e5) renders a taller card whose
    # circle floats at .85h and whose anchor the failed run read as
    # 蚂庄园 - the card's left edge clipped the 蚂. A single Back press
    # exits Alipay outright (09-29, measured on that very frame), so the
    # tap-on-circle stays the only closer: search the whole band below
    # the card and take the lowest centered circle - the CTA button and
    # card art sit above the circle, the bottom nav is past the band, and
    # the notification toast's own close is off-center. The card text
    # gates the scan so the round icons of a clean home can never
    # trigger it.
    if observation.page in ("alipay", "UNKNOWN") \
            and observation.has("广州生活卡|组合券包") \
            and observation.image is not None:
        image = observation.image
        h, w = image.shape[:2]
        # Device evidence (2026-09-29, run 4374cb): the home's own banner
        # repeats 广州生活卡限时放送, so the card text alone no longer
        # separates the modal from the clean home it was just closed to -
        # the second dismissal hunt found a "circle" on the clean page,
        # tapped it, and the chain fell out of the page. The modal's
        # backdrop dims the band left of the card to mean gray ~65 while
        # the clean home's feed reads ~220 (both templates, 09-25 and
        # 09-29) - gate the scan on that physics, not on the copy.
        band = cv2.cvtColor(image[int(h * .62):int(h * .90), 0:int(w * .10)],
                            cv2.COLOR_BGR2GRAY)
        dimmed = band.size and cv2.mean(band)[0] < 140
        if dimmed:
            x0, y0 = int(w * .35), int(h * .62)
            crop = cv2.cvtColor(image[y0:int(h * .90), x0:int(w * .65)], cv2.COLOR_BGR2GRAY)
            if crop.size:
                blurred = cv2.GaussianBlur(crop, (5, 5), 1.2)
                circles = cv2.HoughCircles(blurred, cv2.HOUGH_GRADIENT, 1.2, 80,
                                           param1=100, param2=45,
                                           minRadius=max(20, int(w * .025)),
                                           maxRadius=max(40, int(w * .06)))
                if circles is not None:
                    center = crop.shape[1] / 2
                    centered = [item for item in circles[0]
                                if abs(float(item[0]) - center) <= w * .07]
                    if centered:
                        circle = max(centered, key=lambda item: float(item[1]))
                        # Device evidence (2026-10-09, run 75b3a0): this
                        # period's taller 领12张 card dims the quick-icon row
                        # so hard that OCR dropped 扫一扫 entirely and clipped
                        # the home grid label 市民中心 to 市民中, so the alipay
                        # rule's group one matched nothing and the frame
                        # stayed UNKNOWN - the promo never classified as an
                        # overlay and forest.self's entry starved on ensure's
                        # Back wait (Postcondition failed: return; page=UNKNOWN
                        # across seven frames). The interstitial only ever
                        # sits on the Alipay home, so a verified close circle
                        # (band 66 vs the clean home's ~220, centered r56 at
                        # (721,2736)) restores the page identity the dim
                        # destroyed and the overlay then dismisses normally.
                        observation.page = "alipay"
                        observation.overlays.append("home_promo")
                        observation.elements.append(
                            close_circle_element(observation, circle, (x0, y0)))
    # Device evidence (2026-09-26, run 7d8d95): about two beats after the
    # spec's auto-jump opens the 做任务集肥料 drawer, the timed promo card
    # (领3000肥料 / 玩寻道大千砍树20次即得 / 限时翻倍) pops as a modal whose
    # backdrop blur erases the drawer header from OCR - the frame still
    # classifies farm from the sharp nav title plus the card's 肥料 text,
    # and row()'s ensure("farm_tasks") then spiraled through parents/Back
    # to its budget: the drawer opens only via the auto-jump, so no route
    # leads back. The drawer stays alive under the modal; its close circle
    # floats below the card at ~74% screen height. The card title gates
    # the scan so the entry welcome card's 1100肥料待领取 and the farm
    # home's own labels can never trigger it.
    if observation.page == "farm" and observation.has(r"领\d+肥料") \
            and observation.image is not None:
        image = observation.image
        h, w = image.shape[:2]
        x0, y0 = int(w * .35), int(h * .62)
        crop = cv2.cvtColor(image[y0:int(h * .86), x0:int(w * .65)], cv2.COLOR_BGR2GRAY)
        if crop.size:
            blurred = cv2.GaussianBlur(crop, (5, 5), 1.2)
            circles = cv2.HoughCircles(blurred, cv2.HOUGH_GRADIENT, 1.2, 80,
                                       param1=100, param2=45,
                                       minRadius=max(20, int(w * .025)),
                                       maxRadius=max(40, int(w * .06)))
            if circles is not None:
                expected = (crop.shape[1] / 2, crop.shape[0] * .50)
                circle = min(
                    circles[0],
                    key=lambda item: (float(item[0]) - expected[0]) ** 2
                    + (float(item[1]) - expected[1]) ** 2,
                )
                distance = ((float(circle[0]) - expected[0]) ** 2
                            + (float(circle[1]) - expected[1]) ** 2) ** .5
                if distance <= w * .07:
                    observation.overlays.append("farm_promo")
                    observation.elements.append(
                        close_circle_element(observation, circle, (x0, y0)))
    # Device evidence (2026-09-30, run f427d5): the daily fertilize's
    # 丰收礼包 popup (spec L67: 施肥 -> 立即领肥 -> popup -> 立即领取 ->
    # 点击"X"关闭) is claimed through its own CTA, but the exit that
    # follows - one Android Back - closed the whole 芭芭农场 container
    # onto feed (the drawer's exit, run 5742c4, all over again) and
    # starved back(("farm",)). The close circle floats bottom-center
    # under the CTA at (0.50w, 0.726h) r≈56 full-scale in BOTH claim
    # states (frames 0157/0158 detect identically), and OCR reads the
    # title's 丰 as 半 mid-animation on the same popup (0157 against
    # 0155), so the gate is the [半丰]收礼包 title on the farm page - the
    # same run's 8 clean farm frames carry neither the text nor a circle
    # in the scan band.
    if observation.page == "farm" and observation.has(r"[半丰]收礼包") \
            and observation.image is not None:
        image = observation.image
        h, w = image.shape[:2]
        x0, y0 = int(w * .35), int(h * .66)
        crop = cv2.cvtColor(image[y0:int(h * .80), x0:int(w * .65)], cv2.COLOR_BGR2GRAY)
        if crop.size:
            blurred = cv2.GaussianBlur(crop, (5, 5), 1.2)
            circles = cv2.HoughCircles(blurred, cv2.HOUGH_GRADIENT, 1.2, 80,
                                       param1=100, param2=45,
                                       minRadius=max(20, int(w * .025)),
                                       maxRadius=max(40, int(w * .06)))
            if circles is not None:
                expected = (crop.shape[1] / 2, crop.shape[0] * .50)
                circle = min(
                    circles[0],
                    key=lambda item: (float(item[0]) - expected[0]) ** 2
                    + (float(item[1]) - expected[1]) ** 2,
                )
                distance = ((float(circle[0]) - expected[0]) ** 2
                            + (float(circle[1]) - expected[1]) ** 2) ** .5
                if distance <= w * .07:
                    observation.overlays.append("farm_gift")
                    observation.elements.append(
                        close_circle_element(observation, circle, (x0, y0)))
    # Device evidence (2026-10-09, run e81885): the 秋日美满 主题装扮来拉
    # costume campaign opens as a full-screen modal over the manor home and
    # rode EVERY frame of that run (from the first entry at 13:49) while the
    # page kept classifying manor - the scrim dims the backdrop (left band
    # gray 34 against a clean home's 172) yet the bottom nav stays readable
    # under it, and none of the campaign copy sat in any rule, so overlays
    # stayed empty and donate_egg's 家庭 tap at (627,3037) landed on the
    # modal's full-screen touch layer: eight postcondition refreshes all
    # read manor with zero transition frames (the tap was swallowed). The
    # close circle carries no OCR text - Hough finds it at (720,2450) r47,
    # dead-centered, in the same .62-.86h band the farm promo scan uses
    # (82px from the band center, inside the .07w tolerance). The campaign
    # copy is modal-exclusive and the dim band gates it the way the home
    # promo scan does, so a bright home whose scene might echo the campaign
    # name can never launch the circle scan.
    if observation.page == "manor" and observation.image is not None \
            and observation.has("秋日美满|主题装扮来[拉啦]|去抽装扮"):
        image = observation.image
        h, w = image.shape[:2]
        band = cv2.cvtColor(image[int(h * .62):int(h * .90), 0:int(w * .10)],
                            cv2.COLOR_BGR2GRAY)
        if band.size and cv2.mean(band)[0] < 140:
            x0, y0 = int(w * .35), int(h * .62)
            crop = cv2.cvtColor(image[y0:int(h * .86), x0:int(w * .65)],
                                cv2.COLOR_BGR2GRAY)
            if crop.size:
                blurred = cv2.GaussianBlur(crop, (5, 5), 1.2)
                circles = cv2.HoughCircles(blurred, cv2.HOUGH_GRADIENT, 1.2, 80,
                                           param1=100, param2=45,
                                           minRadius=max(20, int(w * .025)),
                                           maxRadius=max(40, int(w * .06)))
                if circles is not None:
                    expected = (crop.shape[1] / 2, crop.shape[0] * .50)
                    circle = min(
                        circles[0],
                        key=lambda item: (float(item[0]) - expected[0]) ** 2
                        + (float(item[1]) - expected[1]) ** 2,
                    )
                    distance = ((float(circle[0]) - expected[0]) ** 2
                                + (float(circle[1]) - expected[1]) ** 2) ** .5
                    if distance <= w * .07:
                        observation.overlays.append("costume_promo")
                        observation.elements.append(
                            close_circle_element(observation, circle, (x0, y0)))
    # Device evidence (2026-10-09, run d78458): the 小号 unlocked the
    # 初心守护者 achievement right after its donation and the full-screen
    # 恭喜解锁成就 modal dimmed the donate pages into UNKNOWN (left band 53
    # against a clean page's ~170), so no page rule matched, nothing
    # classified as an overlay, and ensure's Back wait starved on the frame
    # (Postcondition failed: return; page=UNKNOWN across eight frames). The
    # modal is page-independent - it can land over any mini-app page - and
    # carries a centered close circle at (720,2661) r54, the same
    # bottom-center slot the other promo scans use. Its own title gates the
    # scan, so the donation copy can never launch the circle hunt.
    if observation.has("恭喜解锁成就") and observation.image is not None:
        image = observation.image
        h, w = image.shape[:2]
        band = cv2.cvtColor(image[int(h * .62):int(h * .90), 0:int(w * .10)],
                            cv2.COLOR_BGR2GRAY)
        if band.size and cv2.mean(band)[0] < 140:
            x0, y0 = int(w * .35), int(h * .72)
            crop = cv2.cvtColor(image[y0:int(h * .93), x0:int(w * .65)],
                                cv2.COLOR_BGR2GRAY)
            if crop.size:
                blurred = cv2.GaussianBlur(crop, (5, 5), 1.2)
                circles = cv2.HoughCircles(blurred, cv2.HOUGH_GRADIENT, 1.2, 80,
                                           param1=100, param2=45,
                                           minRadius=max(20, int(w * .025)),
                                           maxRadius=max(40, int(w * .06)))
                if circles is not None:
                    center = crop.shape[1] / 2
                    centered = [item for item in circles[0]
                                if abs(float(item[0]) - center) <= w * .07]
                    if centered:
                        circle = max(centered, key=lambda item: float(item[1]))
                        observation.overlays.append("achievement_promo")
                        observation.elements.append(
                            close_circle_element(observation, circle, (x0, y0)))
    # Device evidence (2026-10-10, run 16b346, frame 0004): the 七日礼包
    # login-gift modal (恭喜获得七日礼包 + the seven-day reward grid) pops
    # over the manor a beat after the entry ad closes and drops the page to
    # UNKNOWN (frame mean 75, left band 41 against a clean home's 172), so
    # it fires the reward family without any of that family's closing CTAs
    # and recovery fell through to its else-Back - one Back then walked the
    # whole 蚂蚁庄园 container out onto the alipay home (0004 -> 0006), the
    # farm drawer / 丰收礼包 accident all over again. Its close circle is
    # the LOWEST centered circle in the lower band: (719,2463) r60 at
    # .770h dead-centered and stable across frames 0004/0005, while the
    # grid's round prize icons sit higher or off-center. The modal's own
    # 立即领取 CTA is deliberately not taken: claiming the gift is outside
    # the spec's daily list and would open a claim-result state the chain
    # never verified - the X alone ends the interruption.
    if observation.has("恭喜获得七日礼包") and observation.image is not None:
        image = observation.image
        h, w = image.shape[:2]
        band = cv2.cvtColor(image[int(h * .62):int(h * .90), 0:int(w * .10)],
                            cv2.COLOR_BGR2GRAY)
        if band.size and cv2.mean(band)[0] < 140:
            x0, y0 = int(w * .25), int(h * .50)
            crop = cv2.cvtColor(image[y0:int(h * .95), x0:int(w * .75)],
                                cv2.COLOR_BGR2GRAY)
            if crop.size:
                blurred = cv2.GaussianBlur(crop, (5, 5), 1.2)
                circles = cv2.HoughCircles(blurred, cv2.HOUGH_GRADIENT, 1.2, 80,
                                           param1=100, param2=45,
                                           minRadius=max(20, int(w * .02)),
                                           maxRadius=max(40, int(w * .07)))
                if circles is not None:
                    center = crop.shape[1] / 2
                    centered = [item for item in circles[0]
                                if abs(float(item[0]) - center) <= w * .07]
                    if centered:
                        circle = max(centered, key=lambda item: float(item[1]))
                        observation.elements.append(
                            close_circle_element(observation, circle, (x0, y0)))
    return observation


def parse_tree(xml, observation):
    root = ET.fromstring(xml)
    elements = []
    for node in root.iter("node"):
        if node.get("enabled") == "false" or node.get("password") == "true":
            continue
        text = (node.get("text") or node.get("content-desc") or "").strip()
        values = re.findall(r"-?\d+", node.get("bounds", ""))
        if text and len(values) == 4:
            bounds = tuple(map(int, values))
            if bounds[0] < bounds[2] and bounds[1] < bounds[3]:
                elements.append(Element(text, bounds, observation, "ui_tree"))
    return elements


class Observer:
    def __init__(self, device, directory, logger):
        from rapidocr_onnxruntime import RapidOCR
        # Offline replay (2026-09-28): 4 intra-op threads cut RapidOCR from
        # 1.35s to 1.14s per frame with byte-identical results on 40
        # archived frames (2-thread vs 4-thread, scores included).
        self.ocr = RapidOCR(intra_op_num_threads=4, inter_op_num_threads=4)
        self.device, self.directory, self.logger = device, directory, logger
        directory.mkdir(parents=True, exist_ok=True)
        self.sequence = 0

    def capture(self, reason="observe", full=False):
        self.sequence += 1
        oid = f"{self.sequence:04d}-{uuid.uuid4().hex[:6]}"
        package = self.device.foreground()
        xml = None
        if full:
            try:
                xml = self.device.tree()
                (self.directory / (oid + ".xml")).write_bytes(xml)
            except AutomationError as exc:
                self.logger.emit("tree.unavailable", error=str(exc))
        captured = time.monotonic()
        image = self.device.frame()
        h, w = image.shape[:2]
        scale = min(1.0, 1080 / w)
        small = cv2.resize(image, (round(w * scale), round(h * scale)))
        results, _ = self.ocr(small)
        elements = []
        for box, text, score in results or []:
            if score < .72:
                continue
            points = np.array(box) / scale
            bounds = (int(points[:, 0].min()), int(points[:, 1].min()),
                      int(points[:, 0].max()), int(points[:, 1].max()))
            elements.append(Element(text.strip(), bounds, oid, "ocr", float(score)))
        # OCR anchors validate XML coordinates from the separately captured tree.
        # Unmatched tree-only elements remain diagnostic until a page rule supports them.
        if xml:
            for element in parse_tree(xml, oid):
                for index, visual in enumerate(elements):
                    if element.text == visual.text and np.linalg.norm(
                        np.array(element.point) - visual.point
                    ) < 30:
                        elements[index] = Element(visual.text, visual.bounds, oid, "ui_tree+ocr", visual.score)
                        break
        obs = classify(Observation(oid, captured, w, h, package, elements, image=image))
        if obs.page == "manor" and (diary := manor_diary_entry(obs)):
            obs.elements.append(diary)
        # The evidence archive stays PNG (lossless, same pixels) but is
        # encoded locally now that the capture arrives raw.
        ok, encoded = cv2.imencode(".png", image)
        if not ok:
            raise AutomationError("Cannot encode screenshot", "DEVICE")
        (self.directory / (oid + ".png")).write_bytes(encoded.tobytes())
        payload = {"id": oid, "reason": reason, "page": obs.page, "overlays": obs.overlays,
                   "captured": captured, "package": package, "width": w, "height": h,
                   "elements": [asdict(e) for e in obs.elements]}
        (self.directory / (oid + ".json")).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        self.logger.emit("observation", **payload)
        return obs
