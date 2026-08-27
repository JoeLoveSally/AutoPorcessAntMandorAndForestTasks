from __future__ import annotations

import pytest
from conftest import make_observation

from domain_data import Bounds, DetectedScreen, Element, Page
from runtime.errors import AutomationError
from workflow.manor.daily import ManorWorkflow

# --- scripted session ------------------------------------------------------


def _obs():
    return make_observation("<?xml version='1.0'?><hierarchy rotation='0' />")


def _screen(page: Page, elements: tuple[str, ...] = ()) -> DetectedScreen:
    return DetectedScreen(
        page,
        _obs(),
        {key: Element(key, Bounds(10, 10, 50, 50), "obs-1") for key in elements},
    )


class _Size:
    width = 1440
    height = 3200


class _Device:
    def __init__(self):
        self.backs = 0

    def back(self):
        self.backs += 1

    def size(self):
        return _Size()


class ScriptedSession:
    """Drives a workflow method by replaying a script of expected screens.

    Each `tap`/`swipe`/`back`/`observe`/`wait_for` pops the next scripted
    screen, recording the call so tests can assert the action sequence and the
    expected-page assertions made along the way.
    """

    def __init__(self, script: list[DetectedScreen]):
        self._script = list(script)
        self.taps: list[tuple[str, tuple[Page, ...]]] = []
        self.swipes: list[str] = []
        self.backs: list[str] = []
        self.observes: list[str] = []
        self.waits: list[tuple[Page, tuple[str, ...]]] = []
        self.device = _Device()
        # No pre-fetched current: the screen passed into a workflow method is
        # supplied by the caller; only tap/swipe/back/observe/wait_for consume
        # the script (each returns the *next* screen).
        self.current: DetectedScreen | None = None

    def _next(self) -> DetectedScreen:
        if not self._script:
            raise AssertionError("script exhausted; workflow asked for another screen")
        return self._script.pop(0)

    def tap(self, screen, key, name, expected=(), required_after=()):
        self.taps.append((key, expected))
        self.current = self._next()
        return self.current

    def _tap_raw(self, screen, key, name, *args, **kwargs):
        return self.tap(screen, key, name)

    def swipe(self, screen, name, *coords, **kwargs):
        self.swipes.append(name)
        self.current = self._next()
        return self.current

    def swipe_without_observation(self, screen, name, *coords, **kwargs):
        return self.swipe(screen, name, *coords, **kwargs)

    def back(self, screen, name, expected=()):
        self.backs.append(name)
        self.current = self._next()
        return self.current

    def observe(self, reason):
        self.observes.append(reason)
        self.current = self._next()
        return self.current

    def wait_for(self, pages, reason, required=(), timeout=None):
        expected = (pages,) if isinstance(pages, Page) else pages
        self.waits.append((expected, required))
        self.current = self._next()
        return self.current

    def recover(self, allowed_pages, reenter=None):
        return self.current

    def add_step(self, *args):
        pass


def _workflow(session: ScriptedSession) -> ManorWorkflow:
    workflow = object.__new__(ManorWorkflow)
    workflow.session = session
    return workflow


def _baba_workflow(session):
    """Build a ManorWorkflow with the external/lottery/quiz stubs it builds in __init__."""
    workflow = object.__new__(ManorWorkflow)
    workflow.session = session
    return workflow


# --- baba farm -------------------------------------------------------------


def test_baba_farm_full_flow_matches_spec_sequence():
    feed = _screen(Page.MANOR_FEED_TASKS, ("farm",))
    tasks_page = _screen(Page.BABA_FARM_TASKS, ("daily_sign_claim", "chicken_feed_claim", "close"))
    after_sign = _screen(Page.BABA_FARM_TASKS, ("chicken_feed_claim", "close"))
    after_chicken = _screen(Page.BABA_FARM_TASKS, ("close",))
    farm_main = _screen(Page.BABA_FARM, ("fertilize", "free_fertilizer"))
    farm_after_free = _screen(Page.BABA_FARM, ("fertilize",))
    farm_after_fert1 = _screen(Page.BABA_FARM, ("claim_now",))
    harvest1 = _screen(Page.BABA_FARM_HARVEST, ("claim", "close"))
    harvest1_after_claim = _screen(Page.BABA_FARM_HARVEST, ("close",))
    farm_after_harvest1 = _screen(Page.BABA_FARM, ("fertilize",))
    farm_after_fert2 = _screen(Page.BABA_FARM, ("claim_now",))
    harvest2 = _screen(Page.BABA_FARM_HARVEST, ("claim", "close"))
    harvest2_after_claim = _screen(Page.BABA_FARM_HARVEST, ("close",))
    farm_after_harvest2 = _screen(Page.BABA_FARM, ("fertilize",))
    feed_return = _screen(Page.MANOR_FEED_TASKS)
    session = ScriptedSession([
        tasks_page, after_sign, after_chicken, farm_main, farm_after_free,
        farm_after_fert1, harvest1, harvest1_after_claim, farm_after_harvest1,
        farm_after_fert2, harvest2, harvest2_after_claim, farm_after_harvest2,
        feed_return,
    ])
    workflow = _baba_workflow(session)

    out = workflow._baba_farm(feed)

    assert out.page is Page.MANOR_FEED_TASKS
    keys = [key for key, _ in session.taps]
    assert keys == [
        "farm",                       # open → 做任务集肥料
        "daily_sign_claim",           # sub-task 1
        "chicken_feed_claim",         # sub-task 2
        "close",                      # leave 做任务集肥料
        "free_fertilizer",            # daily free fertilizer
        "fertilize", "claim_now", "claim", "close",   # round 1
        "fertilize", "claim_now", "claim", "close",   # round 2
    ]
    assert session.device.backs == 1
    # 做任务集肥料 close must expect the farm main page, not the feed list.
    assert session.taps[3] == ("close", (Page.BABA_FARM,))
    # Harvest claim may stay on the pack or auto-close to the farm.
    assert session.taps[7] == (
        "claim",
        (Page.BABA_FARM_HARVEST, Page.BABA_FARM),
    )
    assert session.taps[8] == ("close", (Page.BABA_FARM,))


def test_baba_farm_skips_optional_actions_when_elements_absent():
    feed = _screen(Page.MANOR_FEED_TASKS, ("farm",))
    farm = _screen(Page.BABA_FARM, ("fertilize",))   # no free_fertilizer, no claim_now
    farm_after_fert1 = _screen(Page.BABA_FARM, ("fertilize",))
    farm_after_fert2 = _screen(Page.BABA_FARM, ("fertilize",))
    feed_return = _screen(Page.MANOR_FEED_TASKS)
    session = ScriptedSession([farm, farm_after_fert1, farm_after_fert2, feed_return])
    workflow = _baba_workflow(session)

    workflow._baba_farm(feed)

    keys = [key for key, _ in session.taps]
    assert keys == ["farm", "fertilize", "fertilize"]
    assert session.device.backs == 1


def test_baba_farm_claims_ready_harvest_without_extra_fertilize():
    feed = _screen(Page.MANOR_FEED_TASKS, ("farm",))
    farm_ready_1 = _screen(Page.BABA_FARM, ("fertilize", "claim_now"))
    harvest1 = _screen(Page.BABA_FARM_HARVEST, ("claim", "close"))
    harvest1_claimed = _screen(Page.BABA_FARM_HARVEST, ("close",))
    farm_ready_2 = _screen(Page.BABA_FARM, ("fertilize", "claim_now"))
    harvest2 = _screen(Page.BABA_FARM_HARVEST, ("claim", "close"))
    harvest2_claimed = _screen(Page.BABA_FARM_HARVEST, ("close",))
    farm_done = _screen(Page.BABA_FARM, ("fertilize",))
    feed_return = _screen(Page.MANOR_FEED_TASKS)
    session = ScriptedSession([
        farm_ready_1,
        harvest1,
        harvest1_claimed,
        farm_ready_2,
        harvest2,
        harvest2_claimed,
        farm_done,
        feed_return,
    ])
    workflow = _baba_workflow(session)

    workflow._baba_farm(feed)

    keys = [key for key, _ in session.taps]
    assert keys == [
        "farm",
        "claim_now", "claim", "close",
        "claim_now", "claim", "close",
    ]
    assert "fertilize" not in keys


def test_baba_harvest_accepts_claim_that_auto_closes_to_farm():
    harvest = _screen(Page.BABA_FARM_HARVEST, ("claim", "close"))
    farm = _screen(Page.BABA_FARM, ("fertilize",))
    session = ScriptedSession([farm])
    workflow = _baba_workflow(session)

    out = workflow._baba_harvest(harvest)

    assert out.page is Page.BABA_FARM
    assert session.taps == [
        ("claim", (Page.BABA_FARM_HARVEST, Page.BABA_FARM)),
    ]


def test_baba_farm_dismisses_farm_popup_after_fertilize():
    feed = _screen(Page.MANOR_FEED_TASKS, ("farm",))
    farm = _screen(Page.BABA_FARM, ("fertilize",))
    popup = _screen(Page.BABA_FARM, ("fertilize", "close_reward"))
    farm_after_popup = _screen(Page.BABA_FARM, ("fertilize",))
    popup2 = _screen(Page.BABA_FARM, ("close_reward",))
    farm_after_popup2 = _screen(Page.BABA_FARM, ("fertilize",))
    feed_return = _screen(Page.MANOR_FEED_TASKS)
    session = ScriptedSession([farm, popup, farm_after_popup, popup2, farm_after_popup2, feed_return])
    workflow = _baba_workflow(session)

    workflow._baba_farm(feed)

    # No claim_now present, so only fertilise + dismiss-popup per round.
    assert [key for key, _ in session.taps] == [
        "farm",
        "fertilize", "close_reward",
        "fertilize", "close_reward",
    ]
    assert session.taps[2] == ("close_reward", (Page.BABA_FARM,))
    assert session.device.backs == 1


def test_baba_farm_dismisses_entry_popup_before_task_claims():
    feed = _screen(Page.MANOR_FEED_TASKS, ("farm",))
    entry_popup = _screen(
        Page.BABA_FARM_TASKS,
        ("daily_sign_claim", "chicken_feed_claim", "close", "close_reward"),
    )
    tasks_page = _screen(
        Page.BABA_FARM_TASKS,
        ("daily_sign_claim", "chicken_feed_claim", "close"),
    )
    after_sign = _screen(Page.BABA_FARM_TASKS, ("chicken_feed_claim", "close"))
    after_chicken = _screen(Page.BABA_FARM_TASKS, ("close",))
    farm = _screen(Page.BABA_FARM, ("fertilize",))
    after_fert1 = _screen(Page.BABA_FARM, ("fertilize",))
    after_fert2 = _screen(Page.BABA_FARM, ("fertilize",))
    feed_return = _screen(Page.MANOR_FEED_TASKS)
    session = ScriptedSession([
        entry_popup,
        tasks_page,
        after_sign,
        after_chicken,
        farm,
        after_fert1,
        after_fert2,
        feed_return,
    ])
    workflow = _baba_workflow(session)

    workflow._baba_farm(feed)

    assert [key for key, _ in session.taps][:5] == [
        "farm",
        "close_reward",
        "daily_sign_claim",
        "chicken_feed_claim",
        "close",
    ]
    assert session.taps[1] == ("close_reward", (Page.BABA_FARM_TASKS,))


def test_baba_farm_raises_when_fertilize_disappears():
    feed = _screen(Page.MANOR_FEED_TASKS, ("farm",))
    farm = _screen(Page.BABA_FARM, ("fertilize",))
    drained = _screen(Page.BABA_FARM)   # fertilize gone after round 1
    session = ScriptedSession([farm, drained])
    workflow = _baba_workflow(session)

    with pytest.raises(AutomationError, match="fertilise action"):
        workflow._baba_farm(feed)


# --- kitchen ---------------------------------------------------------------


def test_kitchen_donate_path_then_cook_loop():
    feed = _screen(Page.MANOR_FEED_TASKS, ("kitchen",))
    kitchen = _screen(Page.CHICKEN_KITCHEN, ("cook", "daily_ingredient", "claim_ingredient", "donate_shop"))
    after_daily = _screen(Page.CHICKEN_KITCHEN, ("cook", "claim_ingredient", "donate_shop"))
    after_claim = _screen(Page.CHICKEN_KITCHEN, ("cook", "donate_shop"))
    donate = _screen(Page.KITCHEN_DONATE, ("claim",))
    donate_after_claim = _screen(Page.KITCHEN_DONATE, ("claim",))
    kitchen_after_donate = _screen(Page.CHICKEN_KITCHEN, ("cook",))
    recipe1 = _screen(Page.CHICKEN_KITCHEN, ("close",))   # 美食图鉴 after cook
    kitchen_after_book1 = _screen(Page.CHICKEN_KITCHEN, ("cook",))
    recipe2 = _screen(Page.CHICKEN_KITCHEN, ("close",))
    kitchen_after_book2 = _screen(Page.CHICKEN_KITCHEN, ("cook",))
    feed_return = _screen(Page.MANOR_FEED_TASKS)
    session = ScriptedSession([
        kitchen, after_daily, after_claim,
        donate, donate_after_claim, kitchen_after_donate,
        recipe1, kitchen_after_book1, recipe2, kitchen_after_book2, feed_return,
    ])
    workflow = _baba_workflow(session)

    out = workflow._kitchen(feed)

    assert out.page is Page.MANOR_FEED_TASKS
    keys = [key for key, _ in session.taps]
    assert keys == [
        "kitchen",                 # open
        "daily_ingredient",        # claim daily ingredient
        "claim_ingredient",        # claim ingredient bubble
        "donate_shop",             # open 爱心食材店
        "claim",                   # 领10g食材
        "cook", "close",           # meal 1: cook → 美食图鉴 X
        "cook", "close",           # meal 2
    ]
    assert session.taps[3] == ("donate_shop", (Page.KITCHEN_DONATE,))
    assert session.taps[4] == ("claim", (Page.KITCHEN_DONATE,))
    # The donate sub-page returns to the kitchen via device.back + wait_for.
    assert (Page.CHICKEN_KITCHEN,) in {wait[0] for wait in session.waits}
    # Two device.back() calls: one leaving the donate sub-page, one leaving the kitchen.
    assert session.device.backs == 2


def test_kitchen_skips_donate_shop_when_absent():
    feed = _screen(Page.MANOR_FEED_TASKS, ("kitchen",))
    kitchen = _screen(Page.CHICKEN_KITCHEN, ("cook",))
    recipe1 = _screen(Page.CHICKEN_KITCHEN, ("close",))
    kitchen_after_book1 = _screen(Page.CHICKEN_KITCHEN, ("cook",))
    recipe2 = _screen(Page.CHICKEN_KITCHEN, ("close",))
    kitchen_after_book2 = _screen(Page.CHICKEN_KITCHEN, ("cook",))
    feed_return = _screen(Page.MANOR_FEED_TASKS)
    session = ScriptedSession([
        kitchen, recipe1, kitchen_after_book1, recipe2, kitchen_after_book2, feed_return
    ])
    workflow = _baba_workflow(session)

    workflow._kitchen(feed)

    assert "donate_shop" not in [key for key, _ in session.taps]
    assert [key for key, _ in session.taps] == ["kitchen", "cook", "close", "cook", "close"]
    assert session.device.backs == 1
