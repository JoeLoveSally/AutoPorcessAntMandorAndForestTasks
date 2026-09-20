"""Manor homepage task workflows. All clicks require a fresh page observation."""

from __future__ import annotations

from domain_data import AutomationError

REWARD_REGION = (0.0, 0.55, 0.55, 0.9)


class ManorHome:
    def __init__(self, session):
        self.s = session

    def reward_friends(self):
        s = self.s
        obs = s.ensure("manor")
        rewards_given = 0
        for _ in range(s.config.get("max_reward_steps", 30)):
            if obs.page != "manor" or obs.overlays:
                raise AutomationError("Cannot verify unobstructed manor homepage", "UNKNOWN")
            matches = obs.find("^打赏$", REWARD_REGION)
            if len(matches) > 1:
                raise AutomationError("Multiple visible reward controls", "AMBIGUOUS")
            if not matches:
                confirmation = s.observe("reward-absence-confirm")
                if confirmation.page == "manor" and not confirmation.overlays and not confirmation.has(
                    "^打赏$", REWARD_REGION
                ):
                    # Only a genuinely absent optional task is SKIPPED. Once
                    # any friend was rewarded the overall task is SUCCESS.
                    s.done(confirmation, skipped=(rewards_given == 0))
                    return
                obs = confirmation
                continue
            before = tuple(e.text for e in obs.find(".", REWARD_REGION))
            obs = s.tap_element(
                obs, matches[0],
                lambda after: after.page == "manor" and not after.overlays and (
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
        if not obs.has("马上去找|小鸡外出"):
            confirmed = s.observe("chicken-home-confirm")
            if confirmed.page != "manor" or confirmed.overlays or confirmed.has("马上去找|小鸡外出"):
                raise AutomationError("Cannot confirm chicken is at home", "UNKNOWN")
            s.done(confirmed, skipped=True)
            return
        s.tap("马上去找", lambda after: after.page == "manor_friend")
        # The chicken can be on either side. Only proceed if the active page
        # exposes a unique target; never substitute a memorized coordinate.
        s.tap("带小鸡回家", lambda after: after.page == "manor" and not after.has(
            "马上去找|小鸡外出"
        ))
        s.done()

    def diary(self):
        s = self.s
        obs = s.ensure("diary")
        if obs.has("明日再来"):
            s.done(obs, already=True)
        else:
            s.tap("^贴贴小鸡$", lambda after: after.page == "diary" and after.has("明日再来"),
                  spend=True, detail={"task": "chicken_diary"})
            s.done()
        s.back(("manor",))
