"""Manor homepage tasks. Every action must originate from a fresh observation."""

from __future__ import annotations

import re

from domain_data import AutomationError, Element
from screen_perception.vision import roaming_chicken_target

REWARD_REGION = (0.0, 0.55, 0.55, 0.9)
# The chicken-out sign has two observed boards: the roaming variant
# (小鸡外出探险了 with a 马上去找TA CTA, run 0aa57b on 09-20) and the
# employed variant (a bare 小鸡出去工作啦 board with no CTA, run 6b3fa4
# on 09-26). One pattern gates detection, the CTA preference, and the
# bring-home success check.
CHICKEN_OUT = "马上去找|小鸡外出|小鸡出去工作啦"


def own_chicken_label_target(obs):
    """Locate my chicken through its label at the host manor.

    Device evidence (2026-09-26, run 130950): the employed arrival shows
    every guest chicken's label in a narrow band around y=.58h - the other
    guest reads TA好友的小鸡 while mine reads 不理鸡 (its name; the diary's
    名字 field shows the same on 09-20 and the label rides home with it),
    i.e. mine is the band label that does not end in 的小鸡. The body sits
    under the tag: the proven tap (554,1925) is the label center (530,1850)
    plus 75px. The cx window keeps the 蚂蚁新村 sign (.92w) out.
    """
    for element in obs.find("."):
        left, top, right, bottom = element.bounds
        cx, cy = (left + right) / 2, (top + bottom) / 2
        if not .52 * obs.height < cy < .65 * obs.height:
            continue
        if not .15 * obs.width < cx < .85 * obs.width:
            continue
        if re.search("的小鸡$", element.text):
            continue
        if not re.fullmatch("[\\u4e00-\\u9fff]{2,8}", element.text):
            continue
        tx, ty = int(cx), int(cy + 75)
        return Element("外出小鸡", (tx - 50, ty - 50, tx + 50, ty + 50),
                       obs.id, "label.roaming_chicken", .7)
    return None


class ManorHome:
    def __init__(self, session):
        self.s = session

    def reward_friends(self):
        s = self.s
        obs = s.ensure("manor")
        rewards_given = 0
        for _ in range(s.config.get("max_reward_steps", 30)):
            if obs.overlays:
                from workflow.recovery import dismiss
                obs = dismiss(s, obs)
            if obs.page != "manor":
                raise AutomationError("Cannot verify unobstructed manor homepage", "UNKNOWN")
            matches = obs.find("^打赏$", REWARD_REGION)
            if len(matches) > 1:
                raise AutomationError("Multiple visible reward controls", "AMBIGUOUS")
            if not matches:
                confirmation = s.observe("reward-absence-confirm")
                if confirmation.overlays:
                    from workflow.recovery import dismiss
                    confirmation = dismiss(s, confirmation)
                if confirmation.page == "manor" and not confirmation.overlays and not confirmation.has(
                    "^打赏$", REWARD_REGION
                ):
                    s.done(confirmation, skipped=(rewards_given == 0))
                    return
                obs = confirmation
                continue
            before = tuple(e.text for e in obs.find(".", REWARD_REGION))
            obs = s.tap_element(
                obs, matches[0],
                lambda after, before=before: after.page == "manor" and not after.overlays and (
                    not after.has("^打赏$", REWARD_REGION)
                    or tuple(e.text for e in after.find(".", REWARD_REGION)) != before
                ),
                name="reward-friend", spend=True,
            )
            rewards_given += 1
        raise AutomationError("Reward loop ended without verifying button disappearance", "TIMEOUT")

    def bring_home(self):
        s = self.s
        obs = s.ensure("manor")
        if not obs.has(CHICKEN_OUT):
            confirmed = s.observe("chicken-home-confirm")
            if confirmed.page != "manor" or confirmed.overlays or confirmed.has(CHICKEN_OUT):
                raise AutomationError("Cannot confirm chicken is at home", "UNKNOWN")
            s.done(confirmed, skipped=True)
            return
        # Device evidence (2026-09-26, run 6b3fa4): the employed board
        # carries no CTA - tapping the board text itself ([684,1720,904,1758]
        # -> (794,1739)) jumped straight to the host manor. Prefer the CTA
        # when the roaming variant shows it (device-proven 09-20).
        if obs.has("马上去找"):
            hint = s.tap("马上去找", lambda after: after.page == "manor_friend")
        else:
            hint = s.tap("小鸡出去工作啦|小鸡外出",
                         lambda after: after.page == "manor_friend")
        stable = s.observe("roaming-chicken-stable")
        target = roaming_chicken_target(hint, stable)
        if target is None:
            # Device evidence (2026-09-26, run 130950): the employed
            # arrival carries no pointing hand either, so the vision cue
            # finds nothing - fall back to my chicken's own label.
            target = own_chicken_label_target(stable)
        if target is None:
            raise AutomationError("Cannot locate pointing-hand cue for roaming chicken", "TARGET_UNKNOWN")
        obs = s.tap_element(
            stable,
            target,
            lambda after: after.page == "manor" and not after.has(CHICKEN_OUT),
            name="bring-chicken-home",
            spend=True,
            detail={"side": "left" if target.point[0] < stable.width / 2 else "right"},
        )
        s.done(obs)

    def diary(self):
        s = self.s
        # Device evidence (2026-09-29, runs 5742c4 -> 97e388): the red
        # diary book IS the 贴贴 entry (spec L10) and it vanishes from the
        # manor once the day's diary has been read - the 09:31 read left
        # the 10:06 manor with no 小鸡日记 anchor at all (found 0 across
        # four frames), so the always-reprobe re-run died even though the
        # task had been page-verified hours earlier. Anchor absent plus
        # that verified business-day record is the completion evidence;
        # without the record the missing anchor must still fail the first
        # attempt.
        obs = s.observe("diary-entry")
        if (not obs.find("小鸡日记|^日记$")
                and s.ex.store.verified_status(s.task)
                in ("SUCCESS", "ALREADY_DONE")):
            s.done(obs, already=True)
            return
        obs = s.ensure("diary")
        if obs.has("明日再来"):
            s.done(obs, already=True)
        else:
            s.tap("^贴贴小鸡$", lambda after: after.page == "diary" and after.has("明日再来"),
                  spend=True, detail={"task": "chicken_diary"})
            s.done()
        s.back(("manor",))
