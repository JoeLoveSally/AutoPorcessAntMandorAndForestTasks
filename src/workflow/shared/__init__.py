import re
import time

from domain_data import AutomationError
from state_machine import Budget
from workflow.recovery import dismiss


def browse(s, swipe):
    budget = Budget(55, s.ex.budget)
    while budget.remaining:
        obs = dismiss(s)
        if obs.has("已完成.*可领|浏览完成|已完成", (.45,0,1,.3)):
            return obs
        if obs.page != "ad":
            raise AutomationError("Advertisement timer not identified", "TIMER_MISSING")
        if swipe:
            s.scroll((.5,.73,.5,.55))
        time.sleep(min(1, budget.remaining))
    raise AutomationError("Advertisement completion not verified", "TIMEOUT")


def lottery(s, ads, exchange=False):
    for title in ("每日签到",):
        obs, _, button = s.row(title, page="lottery")
        if button.text in ("领取", "签到"):
            s.tap_element(obs, button, lambda o:o.page == "lottery" and o.has("领取成功|已签到|已领取"),
                          name="lottery-sign", spend=True)
    for index in range(ads):
        obs, title, button = s.row("去杂货铺逛一逛|去森林市集逛一逛", page="lottery")
        if re.search(rf"[（(]{ads}/{ads}[）)]", title.text) and "领取" not in button.text:
            break
        if "领取" not in button.text:
            s.tap_element(obs, button, lambda o:o.page == "ad" or "guess" in o.overlays,
                          name="lottery-ad")
            browse(s, True)
            s.back(("lottery",))
            obs, _, button = s.row("去杂货铺逛一逛|去森林市集逛一逛", page="lottery")
        if button.text != "领取":
            raise AutomationError("Lottery advertisement reward not available")
        previous = title.text
        s.tap_element(obs, button, lambda o:o.page == "lottery" and (o.has("领取成功") or not o.has(re.escape(previous))),
                      name="lottery-ad-claim", spend=True, detail={"ad":index+1})
    if exchange:
        obs, _, button = s.row("消耗饲料换机会", page="lottery")
        if "去完成" in button.text:
            s.tap_element(obs, button, lambda o:o.has("兑换确认|确认兑换"), name="exchange-open")
            s.tap("确认兑换", lambda o:o.page == "lottery" and o.has("领取成功|已兑换"),
                  spend=True, overlay=True)
    obs = s.observe("lottery-ready")
    if not obs.has(r"还剩[1-9]\d*次|剩余[1-9]\d*次"):
        raise AutomationError("Lottery available chances not verified")
    s.tap("^立即抽奖$", lambda o:o.has("获得奖励|开心收下"), spend=True)
    dismiss(s)
