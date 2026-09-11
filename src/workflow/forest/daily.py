from __future__ import annotations

import re

from domain_data import AutomationError


class Forest:
    def __init__(self, session):
        self.s = session

    def collect_self(self):
        s = self.s
        obs = s.ensure("forest")
        for _ in range(40):
            balls = obs.find(r"^\d+g$", (.05,.12,.95,.5))
            if not balls:
                confirmed = s.observe("energy-absence-confirm")
                if confirmed.page != "forest" or confirmed.overlays:
                    raise AutomationError("Cannot verify own energy exhausted")
                if confirmed.find(r"^\d+g$", (.05,.12,.95,.5)):
                    obs = confirmed
                    continue
                break
            ball = balls[0]
            x,y = ball.point
            obs = s.tap_element(obs, ball, lambda o:o.page == "forest" and not any(
                e.text == ball.text and abs(e.point[0]-x) < 25 and abs(e.point[1]-y) < 25
                for e in o.elements), name="collect-energy")
        else:
            raise AutomationError("Own energy loop limit reached")
        # The delayed sign-in bubble must be observed after normal collection too.
        for _ in range(3):
            obs = s.observe("delayed-energy-sign")
            if obs.has("能量签到"):
                s.tap("能量签到", lambda o:o.has("奖励|立即领取"))
                for _ in range(5):
                    obs = s.observe("energy-sign-reward")
                    if obs.has("立即领取"):
                        s.tap("立即领取", lambda o:not o.has("立即领取"), spend=True)
                        break
                    # This target is a known sign-in destination despite having no reusable page title.
                    if obs.page == "UNKNOWN":
                        break
                    s.scroll()
                s.back(("forest",), allow_unknown=True)
                break
        s.done()

    def friends(self):
        from workflow.shared import lottery
        s = self.s
        s.ensure("forest")
        s.tap("^找能量$", lambda o:o.page in ("forest_friend", "treasure"))
        seen = set()
        for _ in range(250):
            obs = s.observe("friend")
            if obs.page == "treasure":
                break
            if obs.page != "forest_friend":
                raise AutomationError("Unknown friend traversal page")
            identity = tuple(e.text for e in obs.find("的蚂蚁森林", (0,0,1,.2)))
            if identity in seen:
                raise AutomationError("Friend traversal made no progress")
            seen.add(identity)
            if obs.has("一键收"):
                s.tap("一键收", lambda o:o.page == "forest_friend" and not o.has("一键收"))
            else:
                raise AutomationError("No friend collection completion evidence")
            # A friend swipe intentionally changes the page identity; validate against the two destinations.
            obs = s.observe("next-friend")
            s.ex.validate(obs)
            s.ex.device.swipe((obs.width//2, int(obs.height*.8)), (obs.width//2, int(obs.height*.35)))
            s.wait(lambda o:o.page == "treasure" or (o.page == "forest_friend" and tuple(
                e.text for e in o.find("的蚂蚁森林", (0,0,1,.2))) != identity), "next-friend")
        else:
            raise AutomationError("Friend traversal exhausted budget before treasure")
        s.tap("立即抽奖", lambda o:o.page == "lottery")
        lottery(s, 2)
        obs = s.observe("forest-lottery-tabs")
        tabs = obs.find("抽抽乐|抽奖|主题", (0,0,1,.25))
        if len(tabs) != 2:
            raise AutomationError("Cannot identify both forest lottery tabs")
        s.tap_element(obs, min(tabs, key=lambda e:e.point[0]),
                      lambda o:o.page == "lottery" and o.has("每日签到"), name="left-lottery")
        lottery(s, 0)
        s.back(("treasure",))
        s.back(("forest",))
        s.done()

    def water(self, love):
        s = self.s
        target = "love" if love else "cooperate"
        amount = 100 if love else 520
        obs = s.ensure("forest")
        pattern = "^真爱合种$" if love else "^合种$"
        for _ in range(5):
            if obs.has(pattern):
                break
            obs = s.scroll((.85,.67,.2,.67))
        s.tap(pattern, lambda o:o.page == target)
        obs = s.observe("water-progress")
        if obs.has(rf"今日.*(?:已浇|已攒|贡献).*{amount}g"):
            s.done(obs, already=True)
            s.back(("forest",))
            return
        if s.ex.store.unresolved(s.task) or s.ex.store.status(s.task) in ("SUCCESS", "ALREADY_DONE"):
            raise AutomationError("Watering progress requires current daily evidence", "RESULT_UNKNOWN")
        s.tap("为爱攒能量" if love else "^浇水$",
              lambda o:o.has("克|g") and o.has("攒能量" if love else "浇水"))
        for _ in range(9):
            obs = s.observe("water-quantity")
            quantities = obs.find(r"^\d+\s*(?:g|克)?$", (.15,.4,.85,.95))
            if len(quantities) != 1:
                raise AutomationError("Water quantity is ambiguous", "QUANTITY")
            value = int(re.search(r"\d+", quantities[0].text)[0])
            if value == amount:
                break
            if not love or value > amount or (amount-value) % 10:
                raise AutomationError(f"Unexpected water quantity {value}", "QUANTITY")
            s.tap(r"^\+$", lambda o,v=value:o.has(rf"^{v+10}\s*(?:g|克)?$", (.15,.4,.85,.95)))
        else:
            raise AutomationError("Unable to set water quantity")
        s.tap("^攒能量$" if love else "^浇水$",
              lambda o:o.has(rf"今日.*(?:已浇|已攒|贡献).*{amount}g|成功.*{amount}g|{amount}g.*成功"),
              region=(0,.6,1,1), spend=True, detail={"grams":amount})
        s.done()
        s.back(("forest",))

    def rain(self):
        from workflow.forest.energy_rain import play
        s = self.s
        obs = s.ensure("forest")
        for _ in range(5):
            if obs.has("天天能量雨"):
                break
            obs = s.scroll((.85,.67,.2,.67))
        s.tap("天天能量雨", lambda o:o.page == "rain")
        if s.ex.store.unresolved(s.task):
            raise AutomationError("Interrupted energy rain needs round evidence", "RESULT_UNKNOWN")
        for index in range(2):
            obs = s.observe("rain-start")
            if not obs.has("立即开始"):
                raise AutomationError("Requested rain round is unavailable")
            play(s, index+1)
            if index == 0:
                obs = s.observe("rain-gift")
                choices = obs.find("送TA机会|送Ta机会|送他机会")
                if not choices:
                    raise AutomationError("No first friend gift opportunity")
                s.tap_element(obs, min(choices,key=lambda e:(e.point[1],e.point[0])),
                              lambda o:o.page == "rain" and o.has("立即开始"), name="rain-gift", spend=True)
        s.done()
        s.back(("forest",))
