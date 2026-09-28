from __future__ import annotations

import hashlib
import re
import time

from domain_data import AutomationError

# Real-device evidence (2026-09-23): every captured frame OCRs the friend
# entry button as "找能量>" with a trailing chevron, so the anchored
# "^找能量$" found zero targets and the friends task aborted before tapping.
FRIEND_ENTRY = "^找能量>?$"

# Real-device evidence (2026-09-24, run 085605): with the confirm panel
# open the love page renders its month calendar below y=.765, and the day
# number "12" (center y=.909) matched the bare-number pattern inside the
# old .95 upper bound - the quantity "20" (y=.549) then read as two
# matches and the task died as ambiguous; the previous day's layout merely
# happened to park the day numbers outside the region. The quantity, its
# "+" control (y=.550) and the confirm button (y=.667) all sit under .72,
# and the same band keeps a calendar day "30" from satisfying the "+"
# tap's next-value check before the value actually moves.
WATER_DIALOG = (.15, .4, .85, .72)

# The 森林广场 card bar sits at y=.81 (section label y=.734, card labels
# y=.829); the old .67 band is the fixed 乐园/背包/领奖励 icon row where
# five drags moved nothing. Device evidence (2026-09-24, run 090814): the
# 合种 card is clipped at the right edge behind 真爱合种 and never revealed
# until the drag targeted the card row; the 天天能量雨 entry lives in the
# same bar (spec line 103), so rain() drags the same band.
PLAZA_SCROLL = (.85, .81, .2, .81)

# Real-device evidence (2026-09-24, run 092325): the plaza card label
# reads "能量雨" (verified on the card art itself), while spec line 103
# calls the entry 天天能量雨 - the old anchored pattern found 0 after five
# drags. Accept both spellings.
RAIN_ENTRY = "^(?:天天)?能量雨$"

# Entry taps bind the card label row only. Device evidence (2026-09-25,
# run d04112): the 合种 card repeats its name as a mini-badge on the art
# (合种 [882,2569], y=.808) directly above its label ([917,2625], y=.829),
# so ^合种$ matched twice over the SAME card and the entry tap died
# "found 2". Badges sit at y=.808, labels at y=.829 per the 09-24 plaza
# measurements, so the band separates them with room to spare.
PLAZA_ENTRY = (0, .816, 1, .845)


class Forest:
    def __init__(self, session):
        self.s = session

    @staticmethod
    def _bubbles(obs):
        """Own collectible energy bubbles on the tree crown.

        Real-device evidence (2026-09-21): the top-right total badge reads
        "21563g" inside the bubble band and a naive tap on it never changes,
        the plaza entry cards below the crown carry "260g"/"150g" badges, and
        the delayed sign-in bubble must go through its own reward flow.
        Real-device evidence (2026-09-22): a "25g" reward ball sits ~150px
        above the 乐园 entrance label and tapping it opens the park task
        panel instead of collecting energy, and the card badges drift into
        the band whenever the home renders in a scrolled state. Later that
        day OCR read the sign label as "能量答到" (答 for 签), so the anchor
        tolerates that variant; the separate "5g能量" text below the crown
        belongs to the 神奇海洋 reminder pill and never anchors the sign,
        and the friend-energy floater ("215g" over the name "吴国昊") cannot
        be told apart from OCR fragments under real bubbles, so it stays in
        and its mis-tap recovers through _claim_sign_reward().
        """
        sign = [e.point for e in obs.find("能量[签答]到", (0, .08, .6, .45))]
        labels = [
            e.point for e in obs.find(
                "能量雨|神奇鱼塘|真爱合种|^合种$|^背包$|最近在玩|森林动态|"
                "得能量|收好友|^乐园$",
                (0, .1, 1, 1),
            )
        ]
        bubbles = []
        for element in obs.find(r"^\d{1,4}g$", (.05, .14, .95, .52)):
            x, y = element.point
            if x / obs.width > .68 and y / obs.height < .17:
                continue
            if any(abs(x - sx) < 240 and abs(y - sy) < 240 for sx, sy in sign):
                continue
            # Badges anchored to plaza cards, the park entrance or the stats
            # strip sit next to their labels; crown bubbles never do.
            if any(abs(x - lx) <= 150 and -30 <= ly - y <= 260 for lx, ly in labels):
                continue
            bubbles.append(element)
        return bubbles

    def _settle_top(self, obs):
        """Force the default top layout before judging bubble absence.

        Real-device evidence (2026-09-22): the entry frame restored the home
        scrolled down ~.25, hiding the crown bubbles off-screen while the
        park reward ball drifted into the bubble band; proving absence on
        that layout would skip the collection entirely.
        """
        plaza = obs.find("^森林广场$", (0, .3, 1, 1))
        # Swipe only on positive evidence of the scrolled layout: an unreadable
        # anchor must never trigger a blind swipe.
        if not plaza or plaza[0].point[1] / obs.height >= .68:
            return obs

        def at_top(o):
            return any(e.point[1] / o.height >= .68
                       for e in o.find("^森林广场$", (0, .3, 1, 1)))

        for _ in range(3):
            try:
                return self.s.scroll((.5, .3, .5, .72), target=at_top)
            except AutomationError as exc:
                if exc.code != "TIMEOUT":
                    raise
        return self.s.observe("forest-top-unsettled")

    def collect_self(self):
        s = self.s
        obs = s.ensure("forest")
        stalls = 0
        for _ in range(40):
            if obs.overlays:
                from workflow.recovery import dismiss

                obs = dismiss(s, obs)
            if obs.page != "forest":
                # Any foreign page during collection - the park panel a stray
                # tap opens, the sign reward destination, an OCR gap - resolves
                # the same way: claim 立即领取 when exposed, otherwise back out
                # and normalize, tolerating an Alipay-home overshoot. The crown
                # band is recognized first, and a friend landing is harvested
                # before leaving.
                if obs.page == "treasure" and obs.find("^森林广场$", (0, .3, 1, 1)):
                    # Real-device evidence (2026-09-23): the home strip exposes
                    # a persistent "立即抽奖" card while the floating
                    # 森林寻宝 badge flickers into OCR, so the band classified
                    # as treasure and the recovery overshot to the Alipay home;
                    # the plaza anchor is only ever visible on the forest home.
                    obs.page = "forest"
                elif obs.page == "forest_friend":
                    obs = self._harvest_friend_detour(obs)
                    continue
                else:
                    obs = self._claim_sign_reward()
                    continue
            obs = self._settle_top(obs)
            balls = self._bubbles(obs)
            if not balls:
                # Absence needs two consecutive bubble-free observations on a
                # verified forest page; an overlay or navigation in between
                # resets the proof.
                confirmed = s.observe("energy-absence-confirm")
                if confirmed.overlays or confirmed.page != "forest":
                    obs = confirmed
                    continue
                if self._bubbles(confirmed):
                    obs = confirmed
                    continue
                obs = confirmed
                break
            ball = balls[0]
            x, y = ball.point
            try:
                obs = s.tap_element(
                    obs, ball,
                    lambda o, text=ball.text, x=x, y=y: not any(
                        e.text == text and abs(e.point[0] - x) < 25
                        and abs(e.point[1] - y) < 25 for e in o.elements),
                    name="collect-energy")
                stalls = 0
            except AutomationError as exc:
                # A tap with no observable effect must be proven stale by a
                # fresh observation, and only a bounded number of times.
                if exc.code not in ("TIMEOUT", "STALE", "OVERLAY") or stalls >= 2:
                    raise
                stalls += 1
                obs = s.observe("collect-energy-retry")
        else:
            raise AutomationError("Own energy loop limit reached")
        if obs.page == "forest":
            obs = self._wait_delayed_sign(obs)
        s.done(obs)

    def _harvest_friend_detour(self, obs):
        """Harvest a friend page met during own collection, then leave it.

        Real-device evidence (2026-09-23): the crown floater opened
        小布的蚂蚁森林 with "一键收" exposed and 119g pending; the previous
        recovery only backed out, so the run harvested no friend energy at
        all. One page per detour - the multi-page traversal, its swipes and
        the lottery belong to forest.friends.
        """
        s = self.s
        if obs.has("一键收"):
            s.tap("一键收",
                  lambda o: o.page == "forest_friend" and not o.has("一键收"))
            obs = s.obs
        if obs.overlays:
            from workflow.recovery import dismiss

            obs = dismiss(s, obs)
        obs = s.back(lambda o: o.page in ("forest", "alipay"), allow_unknown=True)
        if obs.page != "forest":
            obs = s.ensure("forest")
        return obs

    def _claim_sign_reward(self):
        """Claim the sign reward if exposed, then normalize back to the forest.

        The destination of the energy sign-in bubble has no stable title, so
        this doubles as the recovery for any foreign page met during
        collection: one bounded scroll (skipped when the control is already
        exposed) looks for "立即领取", its absence must
        not fail the task, and Back may overshoot to the Alipay home, which
        ensure() can route back from.
        """
        s = self.s
        obs = s.observe("energy-sign-reward")
        if obs.page == "forest":
            return obs
        if obs.page == "alipay":
            return s.ensure("forest")
        if obs.has("(?<!领)奖励|签到"):
            # "领奖励" on the forest home must not pass this gate, but the park
            # panel's "完成任务得奖励" heading and the reward destination do.
            try:
                # OCR reads 立 as 主 ("主即领取"), so the claim control matches
                # the tolerant class; the destination usually exposes it right
                # away and only a hidden one needs the bounded scroll.
                if not obs.has("[立三主]即领取"):
                    obs = s.scroll(allow_unknown=True,
                                   target=lambda o: o.has("[立三主]即领取"))
            except AutomationError as exc:
                if exc.code != "TIMEOUT":
                    raise
                obs = s.observe("energy-sign-reward-absent")
        if obs.has("[立三主]即领取"):
            s.tap("[立三主]即领取", lambda o: not o.has("[立三主]即领取"),
                  spend=True, allow_unknown=True)
            obs = s.obs
        if obs.page == "forest":
            return obs
        obs = s.back(lambda o: o.page in ("forest", "alipay"), allow_unknown=True)
        if obs.page != "forest":
            obs = s.ensure("forest")
        return obs

    def _wait_delayed_sign(self, obs):
        """The delayed sign-in bubble must be observed after collection too.

        Real-device evidence (2026-09-22): the widget is a ball plus the
        "能量签到" label underneath (OCR once read the label as "能量答到"),
        while the separate "5g能量" text below the crown is the 神奇海洋
        reminder pill; tapping the ball above the label is the proven path
        into the reward destination, and a sign never seen is not a failure.
        """
        s = self.s
        deadline = time.monotonic() + s.config.get("energy_sign_wait", 6)
        while time.monotonic() < deadline:
            obs = s.observe("delayed-energy-sign")
            labels = obs.find("能量[签答]到", (0, .08, .6, .45))
            if labels:
                x, y = labels[0].point
                balls = [
                    e for e in obs.find(r"^\d{1,4}g$", (.05, .14, .95, .52))
                    if ((e.point[0] - x) ** 2 + (e.point[1] - y) ** 2) ** .5 <= 240
                ]
                if balls:
                    ball = min(
                        balls,
                        key=lambda e: (e.point[0] - x) ** 2 + (e.point[1] - y) ** 2,
                    )
                    s.tap_element(obs, ball,
                                  lambda o: o.has("[立三主]即领取|(?<!领)奖励"),
                                  name="energy-sign")
                    return self._claim_sign_reward()
            time.sleep(min(.6, max(0, deadline - time.monotonic())))
        return obs

    def friends(self):
        from workflow.shared import lottery
        s = self.s
        s.ensure("forest")
        # Device evidence (2026-09-23): when every friend has already been
        # harvested the entry opens forest_summary instead of the deck, and
        # the traversal below treats reaching it as "deck exhausted".
        s.tap(FRIEND_ENTRY, lambda o:o.page in ("forest_friend", "treasure",
                                                "forest_summary"))
        seen = set()
        for _ in range(250):
            obs = s.observe("friend")
            if obs.page in ("treasure", "forest_summary"):
                break
            if obs.page != "forest_friend":
                if obs.page == "UNKNOWN":
                    # Device evidence (2026-09-23): promo cards are
                    # interleaved into the deck with no page rule of their
                    # own - the 支付宝会员签到 card classified UNKNOWN and
                    # held steady for three frames. One more swipe is how the
                    # deck advances past them; every recognized wrong page
                    # stays a hard failure below.
                    s.scroll((.5,.8,.5,.35), target=self._deck_advance(
                        self._deck_texts(obs)), allow_unknown=True)
                    continue
                raise AutomationError("Unknown friend traversal page")
            identity = tuple(e.text for e in obs.find("的蚂蚁森林", (0,0,1,.2)))
            if not identity and obs.image is not None:
                top = obs.image[:max(1, int(obs.height * .25))]
                identity = ("visual:" + hashlib.blake2b(top.tobytes(), digest_size=8).hexdigest(),)
            if identity in seen:
                raise AutomationError("Friend traversal made no progress")
            seen.add(identity)
            if obs.has("一键收"):
                s.tap("一键收", lambda o:o.page == "forest_friend" and not o.has("一键收"))
            else:
                confirmation = s.observe("friend-without-one-click-confirm")
                if confirmation.page != "forest_friend" or confirmation.has("一键收"):
                    obs = confirmation
                    continue
            # Some eligible friend pages contain only a gift bubble and no
            # one-click control. Moving to the next friend is the completion
            # action for that page.
            s.scroll(
                (.5,.8,.5,.35),
                target=self._friend_advance(identity, self._deck_texts(obs)),
            )
        else:
            raise AutomationError("Friend traversal exhausted budget before treasure")
        if obs.page == "forest_summary":
            # Device evidence (2026-09-23): with every friend already
            # harvested, 找能量 opens this summary page instead of the deck,
            # and its 去抽奖 goes straight to the lottery (landing on the
            # left side), skipping the treasure step entirely.
            s.tap("^去抽奖>?$", lambda o:o.page == "lottery")
        else:
            s.tap("[立三主]即抽奖", lambda o:o.page == "lottery")

        # Spec lines 93/96: finish the right lottery first, then the left
        # one through the two-label switch at the top (both labels are the
        # per-period theme names ending in 装扮 - demo video 01:08/02:06).
        # Which side the entry lands on depends on the path (treasure's
        # 立即抽奖 opens the right side, the summary's 去抽奖 the left -
        # device 2026-09-23), and the task list rotates between periods (the
        # left side carried 去森林市集逛一逛 today although only the right
        # side had it in the spec's era), so the active side is detected by
        # its orange pill instead of by task text.
        def switch(want):
            current = s.observe("forest-lottery-switch")
            for _ in range(6):
                tabs = current.find("装扮", (0, .07, 1, .16))
                if len(tabs) == 2:
                    break
                # Device evidence (2026-09-23): after drawing, the task
                # list sits scrolled down under the sticky draw header and
                # the top labels are off-screen; swipe toward the top
                # (finger down) until both show - the entry path already
                # starts with them visible, so this loop is a no-op there.
                current = s.scroll((.5,.4,.5,.82), obs=current)
            if len(tabs) != 2:
                raise AutomationError("Cannot identify both forest lottery labels")
            if self._active_side(current) == want:
                return
            target = (min(tabs, key=lambda e: e.point[0]) if want == "left"
                      else max(tabs, key=lambda e: e.point[0]))
            s.tap_element(current, target,
                          lambda o: o.page == "lottery"
                          and self._active_side(o) == want,
                          name=f"{want}-lottery")

        switch("right")
        lottery(s, 2)
        switch("left")
        lottery(s, 0)
        # Spec line 97 ends back on the forest home. Both entry paths need
        # two backs (lottery -> treasure -> forest; lottery -> summary ->
        # forest - device probe 2026-09-23), and ensure() navigates by the
        # observed page, so a skipped or extra intermediate page cannot
        # strand the run.
        s.ensure("forest")
        s.done()

    @staticmethod
    def _active_side(obs):
        """Which side of the forest lottery switch is showing.

        The two labels are fixed left/right and the active one wears an
        orange pill while the inactive one is a neutral dark gray (demo
        video f_064 right-active/f_093 left-active and device 2026-09-23),
        so mean(R-B) over each label's box separates them regardless of how
        the period rotates the task list below - which it does: the left
        side carried 去森林市集逛一逛 today although only the right side had
        it in the spec's era. None means neither label reads as the orange
        one (or fewer than two labels were recognized).
        """
        tabs = obs.find("装扮", (0, .07, 1, .16))
        if len(tabs) != 2 or obs.image is None:
            return None
        heats = []
        for element in sorted(tabs, key=lambda e: e.point[0]):
            x1, y1, x2, y2 = element.bounds
            crop = obs.image[y1:y2, x1:x2].astype(int)
            heats.append(0.0 if crop.size == 0
                         else float((crop[:, :, 2] - crop[:, :, 0]).mean()))
        if max(heats) < 40:
            return None
        return "left" if heats[0] >= heats[1] else "right"

    @staticmethod
    def _deck_texts(obs):
        """Card-specific recognized texts of a deck card.

        The status bar (minute clock, signal icons) is excluded so two
        different cards never share a merely volatile string, and so is
        the structural footer 上划找更多能量 that every deck card carries
        (friend, promo, and treasure alike - device evidence 2026-09-23:
        that shared hint alone kept progress from being recognized).
        """
        return tuple(e.text for e in obs.elements
                     if obs.height * .05 <= e.point[1] < obs.height * .93)

    @staticmethod
    def _deck_advance(before):
        """Postcondition for a deck swipe that must leave the current card.

        Device evidence (2026-09-23): promo cards (支付宝会员签到) classify
        as UNKNOWN and hold steady across frames, so a wholly different
        card is the only proof that the deck moved: a settling frame of the
        old card, a new floating toast, or a minute tick still shares text
        with it and keeps waiting, as does a blank transition frame. And
        swiping past the last card lands the energy summary (device
        2026-09-23, run 110428: a single-friend deck overflowed onto
        forest_summary), which is terminal for the deck too.
        """
        base = set(before)
        return lambda o: (
            o.page in ("forest_friend", "treasure", "forest_summary")
            or (o.page == "UNKNOWN" and bool(Forest._deck_texts(o))
                and set(Forest._deck_texts(o)).isdisjoint(base))
        )

    @staticmethod
    def _friend_advance(identity, before):
        """Postcondition for a friend-to-friend swipe.

        Treasure ends the traversal, a friend page counts only when its
        title identity differs, and an UNKNOWN frame (promo card or the
        transition itself) counts only when its main-area text is disjoint
        from the card we swiped away from - anything less would report
        false progress and let the loop double-swipe past a friend. The
        energy summary is terminal too: swiping past the last friend lands
        it (device 2026-09-23, run 110428, single-friend deck).
        """
        base = set(before)
        return lambda o: (
            o.page in ("treasure", "forest_summary")
            or (o.page == "forest_friend"
                and Forest._friend_identity(o) != identity)
            or (o.page == "UNKNOWN" and bool(Forest._deck_texts(o))
                and set(Forest._deck_texts(o)).isdisjoint(base))
        )

    @staticmethod
    def _friend_identity(obs):
        identity = tuple(e.text for e in obs.find("的蚂蚁森林", (0,0,1,.2)))
        if identity or obs.image is None:
            return identity
        top = obs.image[:max(1, int(obs.height * .25))]
        return ("visual:" + hashlib.blake2b(top.tobytes(), digest_size=8).hexdigest(),)

    def water(self, love):
        s = self.s
        target = "love" if love else "cooperate"
        amount = 100 if love else 520
        obs = s.ensure("forest")
        pattern = "^真爱合种$" if love else "^合种$"
        for _ in range(5):
            if obs.has(pattern, PLAZA_ENTRY):
                break
            obs = s.scroll(PLAZA_SCROLL)
        s.tap(pattern, lambda o: o.page == target, region=PLAZA_ENTRY)
        obs = s.observe("water-progress")
        if self._water_completed(obs, love, amount):
            s.done(obs, already=True)
            s.back(("forest",))
            return
        if s.ex.store.unresolved(s.task) or s.ex.store.verified_status(s.task) in (
            "SUCCESS", "ALREADY_DONE"
        ):
            raise AutomationError("Watering progress requires current daily evidence", "RESULT_UNKNOWN")
        s.tap("为爱攒能量" if love else "^浇水$",
              lambda o:o.has("克|g") and o.has("攒能量" if love else "浇水"))
        for _ in range(9):
            obs = s.observe("water-quantity")
            quantities = obs.find(r"^\d+\s*(?:g|克)?$", WATER_DIALOG)
            if len(quantities) != 1:
                raise AutomationError("Water quantity is ambiguous", "QUANTITY")
            value = int(re.search(r"\d+", quantities[0].text)[0])
            if value == amount:
                break
            if not love or value > amount or (amount-value) % 10:
                raise AutomationError(f"Unexpected water quantity {value}", "QUANTITY")
            s.tap(r"^\+$", lambda o,v=value:o.has(rf"^{v+10}\s*(?:g|克)?$", WATER_DIALOG))
        else:
            raise AutomationError("Unable to set water quantity")
        base = max(self._g_values(obs), default=0)
        if base <= amount:
            # The returned-state check below must compare against the real
            # team total, not against a flaked quantity or bubble reading -
            # on both paths an unreadable baseline must fail closed, or any
            # total >= amount would verify a tap that never landed.
            raise AutomationError("Water base total not read", "QUANTITY")
        # Device evidence (2026-09-24, run 093245): with the dialog open the
        # cooperate page still shows its own bottom-right 浇水 (0.865,0.969)
        # beside the dialog's 浇水 (0.691,0.621), so the old (0,.6,1,1)
        # region found 2. The dialog band holds the dialog button on both
        # paths (the love confirm 攒能量 sits at (0.499,0.667)).
        s.tap("^攒能量$" if love else "^浇水$",
              lambda o:self._water_completed(o, love, amount) or
              o.has(rf"成功.*{amount}g|{amount}g.*成功") or
              self._water_submitted(o, love, amount, base),
              region=WATER_DIALOG, spend=True, detail={"grams":amount})
        s.done()
        s.back(("forest",))

    def _water_completed(self, obs, love, amount):
        if love:
            return obs.has(rf"已为爱攒\s*{amount}g|今日.*(?:已攒|贡献).*{amount}g")
        owner = str(self.s.config.get("forest_owner", "")).strip()
        if not owner:
            return False
        escaped = re.escape(owner)
        fresh = re.compile("刚刚|分钟前|今天|今日")
        # Device evidence (2026-09-24, run 091908): feed text and timestamp
        # are separate elements on one row - the frame-wide freshness check
        # matched the page's fixed "今日排行）" header while the newest feed
        # row read "昨天12:19", so an unwatered day recorded ALREADY_DONE.
        # Freshness must come from the feed's own row: a row sits within
        # .04 of the screen height, the next feed row ~.046 away.
        for feed in obs.find(rf"{escaped}.*浇了\s*{amount}g"):
            if any(abs(e.point[1] - feed.point[1]) <= obs.height * .04
                   and fresh.search(e.text)
                   for e in obs.elements):
                return True
        return False

    @staticmethod
    def _g_values(obs):
        """Standalone `<digits>g` values of a frame, tolerating the OCR
        trailing parenthesis (the forest-home total reads "260g)" sometimes).

        The balance line "你当前有 22789 g" carries a prefix and never
        matches, so only the bare total and quantity texts count.
        """
        return [int(m.group(1)) for e in obs.elements
                for m in [re.fullmatch(r"\s*(\d+)\s*g\s*\)?", e.text)] if m]

    @staticmethod
    def _water_submitted(obs, love, amount, base):
        """Returned-state postcondition for the water submit tap.

        Device evidence (2026-09-23, run 121403): the love submit closed the
        panel back to the main page (为爱攒能量 readable, 你当前有 gone) with
        the team total 42700 -> 42800 (+100) and no era toast at all. Device
        evidence (2026-09-24, run 9002e4): the cooperate feed is a two-row
        cycling ticker whose new owner row never showed during the wait (all
        visible stamps were 昨天/09-xx) and the toast reads +520g, not
        成功...520g - only the total 101870 -> 102390 (+520) proves the
        spend. Require the returned page (love: 为爱攒能量 back and 你当前有
        gone; cooperate: the dialog's 暂不 gone) plus total >= base+amount;
        water() fails closed when the baseline never read.
        """
        if love:
            if not obs.has("为爱攒能量") or obs.has("你当前有"):
                return False
        elif obs.has("暂不"):
            return False
        return max(Forest._g_values(obs), default=0) >= base + amount

    def rain(self):
        from workflow.forest.energy_rain import play
        s = self.s
        obs = s.ensure("forest")
        for _ in range(5):
            if obs.has(RAIN_ENTRY):
                break
            obs = s.scroll(PLAZA_SCROLL)
        s.tap(RAIN_ENTRY, lambda o:o.page == "rain")
        if s.ex.store.unresolved(s.task):
            raise AutomationError("Interrupted energy rain needs round evidence", "RESULT_UNKNOWN")
        for index in range(2):
            obs = s.observe("rain-start")
            if not obs.has("[立三主]即开[始启]"):
                raise AutomationError("Requested rain round is unavailable")
            play(s, index+1)
            if index == 0:
                obs = s.observe("rain-gift")
                choices = obs.find("送TA机会|送Ta机会|送他机会")
                if not choices:
                    raise AutomationError("No first friend gift opportunity")
                # Device evidence (2026-09-27, run c59b7f): the panel carries
                # three same-text 送TA机会 buttons (the tutorial hand covers
                # the leftmost) and min-by-(y,x) tapped the middle one, which
                # sat dead for 40s while the identical right button had
                # answered the day before (run 06fb5b, point (936,1807)); the
                # friend row rotates daily, so any button can be the dead
                # one. Walk candidates rightmost first: an attempt that times
                # out with the panel still offering the affordance proves the
                # submission never took effect - cancel it and try the next
                # button; a panel that closed after the wait was a slow
                # success instead.
                sent = False
                tried = []
                last = None
                pending = sorted(choices, key=lambda e: -e.point[0])
                while pending:
                    choice = pending.pop(0)
                    if any(abs(choice.point[0] - x) < 40 and abs(choice.point[1] - y) < 40
                           for x, y in tried):
                        continue
                    tried.append(choice.point)
                    try:
                        s.tap_element(obs, choice,
                                      lambda o:o.page == "rain"
                                      and o.has("[立三主]即开[始启]"),
                                      name="rain-gift", spend=True)
                        sent = True
                        break
                    except AutomationError as exc:
                        if exc.code != "TIMEOUT":
                            raise
                        last = exc
                        obs = s.observe("rain-gift-retry")
                        if obs.page == "rain" and obs.has("[立三主]即开[始启]"):
                            sent = True
                            break
                        if s.ex.store.unresolved(s.task):
                            for action_id, name, _, _ in s.ex.store.pending_frames(s.task):
                                if name == "rain-gift":
                                    s.ex.store.action(action_id, "CANCELLED", obs.id)
                        pending = [
                            element for element
                            in obs.find("送TA机会|送Ta机会|送他机会")
                            if not any(abs(element.point[0] - x) < 40
                                       and abs(element.point[1] - y) < 40
                                       for x, y in tried)
                        ]
                        pending.sort(key=lambda e: -e.point[0])
                if not sent:
                    raise last or AutomationError("No first friend gift opportunity")
        s.done()
        s.back(("forest",))
