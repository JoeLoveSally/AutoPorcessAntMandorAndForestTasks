from pathlib import Path
from types import SimpleNamespace

from conftest import make_observation

from device_bridge.common import Size
from domain_data import Bounds, DetectedScreen, Element, Page, StepStatus
from workflow.forest.daily import ForestWorkflow
from workflow.forest.energy_rain import EnergyRainStats


class StubSession:
    def __init__(self):
        self.tapped: list[str] = []
        self.steps = []
        self.config = SimpleNamespace(
            realtime=SimpleNamespace(dedup_radius_pixels=70)
        )
        self.logger = SimpleNamespace(emit=lambda *_args, **_kwargs: None)

    def tap(self, screen, key, name, expected=()):
        self.tapped.append(key)
        remaining = {
            item_key: item
            for item_key, item in screen.elements.items()
            if item_key != key
        }
        self.current = DetectedScreen(Page.FOREST_HOME, screen.observation, remaining)
        return self.current

    def observe(self, reason):
        return self.current

    def add_step(self, *args):
        self.steps.append(args)


def test_collect_own_energy_never_taps_energy_rain_as_a_bubble():
    observation = make_observation("<?xml version='1.0'?><hierarchy rotation='0' />")
    elements = {
        key: Element(key, Bounds(10, 10, 50, 50), observation.id)
        for key in ("energy_0", "energy_rain")
    }
    screen = DetectedScreen(Page.FOREST_HOME, observation, elements)
    session = StubSession()
    session.current = screen
    workflow = object.__new__(ForestWorkflow)
    workflow.session = session

    workflow._collect_own_energy(screen)

    assert session.tapped == ["energy_0"]


def test_collect_own_energy_does_not_count_or_repeat_static_green_target():
    observation = make_observation("<?xml version='1.0'?><hierarchy rotation='0' />")
    target = Element("energy_0", Bounds(240, 1000, 320, 1080), observation.id)
    screen = DetectedScreen(Page.FOREST_HOME, observation, {"energy_0": target})

    class StaticSession(StubSession):
        def tap(self, _screen, key, _name, expected=()):
            self.tapped.append(key)
            self.current = screen
            return screen

    session = StaticSession()
    session.current = screen
    workflow = object.__new__(ForestWorkflow)
    workflow.session = session

    workflow._collect_own_energy(screen)

    assert session.tapped == ["energy_0"]
    assert session.steps[-1][1] is StepStatus.ALREADY_DONE
    assert session.steps[-1][2] == "collected 0 bubbles"


def test_friend_without_one_click_advances_without_tapping_gift_bubble():
    observation = make_observation("<?xml version='1.0'?><hierarchy rotation='0' />")

    def screen(page, *keys):
        return DetectedScreen(
            page,
            observation,
            {key: Element(key, Bounds(100, 700, 260, 860), observation.id) for key in keys},
        )

    home = screen(Page.FOREST_HOME, "find_energy")
    friend = screen(Page.FOREST_FRIEND)
    treasure = screen(Page.FOREST_TREASURE, "enter_lottery")

    class FriendSession:
        def __init__(self):
            self.config = SimpleNamespace(runtime=SimpleNamespace(max_task_iterations=4))
            self.device = SimpleNamespace(size=lambda: Size(1440, 3200))
            self.tapped = []
            self.swiped = 0
            self.steps = []

        def tap(self, _screen, key, _name, _expected=()):
            self.tapped.append(key)
            return friend

        def swipe(self, *_args, **_kwargs):
            self.swiped += 1
            return treasure

        def wait_for(self, *_args, **_kwargs):
            raise AssertionError("stable friend/treasure pages should not need wait_for")

        def add_step(self, *args):
            self.steps.append(args)

    session = FriendSession()
    workflow = object.__new__(ForestWorkflow)
    workflow.session = session
    workflow._forest_lotteries = lambda current: home

    result = workflow._collect_friend_energy(home)

    assert result is home
    assert session.tapped == ["find_energy"]
    assert session.swiped == 1
    assert "collected from 0 friends" in session.steps[-1][2]


def test_friend_campaign_can_return_home_without_mandatory_lottery():
    observation = make_observation("<?xml version='1.0'?><hierarchy rotation='0' />")
    home = DetectedScreen(Page.FOREST_HOME, observation)
    friend = DetectedScreen(Page.FOREST_FRIEND, observation)

    class HomeSession:
        def __init__(self):
            self.config = SimpleNamespace(runtime=SimpleNamespace(max_task_iterations=3))
            self.device = SimpleNamespace(size=lambda: Size(1440, 3200))
            self.steps = []

        def tap(self, *_args, **_kwargs):
            return friend

        def swipe(self, *_args, **_kwargs):
            return home

        def wait_for(self, *_args, **_kwargs):
            raise AssertionError("forest home is an accepted friend-loop endpoint")

        def add_step(self, *args):
            self.steps.append(args)

    session = HomeSession()
    workflow = object.__new__(ForestWorkflow)
    workflow.session = session
    workflow._forest_lotteries = lambda current: (_ for _ in ()).throw(
        AssertionError("lottery must not run when treasure was unavailable")
    )

    result = workflow._collect_friend_energy(
        DetectedScreen(
            Page.FOREST_HOME,
            observation,
            {"find_energy": Element("find_energy", Bounds(1, 1, 10, 10), observation.id)},
        )
    )

    assert result is home
    assert "treasure unavailable" in session.steps[-1][2]


def test_friend_anniversary_campaign_is_backed_out_without_watering():
    observation = make_observation("<?xml version='1.0'?><hierarchy rotation='0' />")
    home = DetectedScreen(Page.FOREST_HOME, observation)
    friend = DetectedScreen(Page.FOREST_FRIEND, observation)
    campaign = DetectedScreen(Page.FOREST_CAMPAIGN, observation)

    class CampaignSession:
        def __init__(self):
            self.config = SimpleNamespace(runtime=SimpleNamespace(max_task_iterations=3))
            self.device = SimpleNamespace(size=lambda: Size(1440, 3200))
            self.steps = []
            self.back_calls = 0

        def tap(self, *_args, **_kwargs):
            return friend

        def swipe(self, *_args, **_kwargs):
            return campaign

        def wait_for(self, *_args, **_kwargs):
            raise AssertionError("explicit campaign page should not need settling")

        def back(self, _screen, _name, expected):
            assert expected == (Page.FOREST_HOME,)
            self.back_calls += 1
            return home

        def add_step(self, *args):
            self.steps.append(args)

    session = CampaignSession()
    workflow = object.__new__(ForestWorkflow)
    workflow.session = session

    result = workflow._collect_friend_energy(
        DetectedScreen(
            Page.FOREST_HOME,
            observation,
            {"find_energy": Element("find_energy", Bounds(1, 1, 10, 10), observation.id)},
        )
    )

    assert result is home
    assert session.back_calls == 1
    assert "treasure unavailable" in session.steps[-1][2]


def test_find_energy_staying_home_means_no_friends_available():
    observation = make_observation("<?xml version='1.0'?><hierarchy rotation='0' />")
    home = DetectedScreen(
        Page.FOREST_HOME,
        observation,
        {"find_energy": Element("find_energy", Bounds(1, 1, 10, 10), observation.id)},
    )

    class NoFriendsSession:
        def __init__(self):
            self.steps = []

        def tap(self, _screen, _key, _name, expected=()):
            assert Page.FOREST_HOME in expected
            return home

        def add_step(self, *args):
            self.steps.append(args)

    session = NoFriendsSession()
    workflow = object.__new__(ForestWorkflow)
    workflow.session = session

    result = workflow._collect_friend_energy(home)

    assert result is home
    assert session.steps[-1][1] is StepStatus.ALREADY_DONE
    assert "no friends available" in session.steps[-1][2]


def test_love_plant_submit_accepts_automatic_return_home_without_back():
    observation = make_observation("<?xml version='1.0'?><hierarchy rotation='0' />")

    def screen(page, *keys):
        return DetectedScreen(
            page,
            observation,
            {
                key: Element(key, Bounds(100, 700, 260, 860), observation.id)
                for key in keys
            },
        )

    home = screen(Page.FOREST_HOME, "love_plant")
    amount = screen(Page.FOREST_LOVE_PLANT, "plus", "confirm")
    sequence = [screen(Page.FOREST_LOVE_PLANT, "water"), amount]
    sequence.extend([amount] * 8)
    sequence.append(screen(Page.FOREST_HOME))

    class WaterSession:
        def __init__(self):
            self.responses = iter(sequence)
            self.taps = []
            self.backs = 0
            self.steps = []

        def tap(self, _screen, key, _name, expected=(), **kwargs):
            self.taps.append((key, expected, kwargs.get("irreversible", False)))
            return next(self.responses)

        def back(self, *_args, **_kwargs):
            self.backs += 1
            return home

        def begin_step(self, *_args):
            pass

        def add_step(self, *args):
            self.steps.append(args)

    session = WaterSession()
    workflow = object.__new__(ForestWorkflow)
    workflow.session = session
    workflow._locate_carousel = lambda current, _key: current

    result = workflow._water_love_plant(home)

    assert result.page is Page.FOREST_HOME
    assert session.backs == 0
    assert session.taps[-1] == (
        "confirm",
        (Page.FOREST_LOVE_PLANT, Page.FOREST_HOME),
        True,
    )
    assert session.steps[0][0] == "forest.water_love_plant"
    assert session.steps[0][1] is StepStatus.SUCCESS


def test_energy_rain_result_page_is_authoritative_over_estimated_hit_rate():
    observation = make_observation("<?xml version='1.0'?><hierarchy rotation='0' />")
    forest = DetectedScreen(
        Page.FOREST_HOME,
        observation,
        {"energy_rain": Element("energy_rain", Bounds(1, 1, 10, 10), observation.id)},
    )
    gift = DetectedScreen(
        Page.ENERGY_RAIN_GIFT,
        observation,
        {"gift_first": Element("gift_first", Bounds(1, 1, 10, 10), observation.id)},
    )
    rain = DetectedScreen(
        Page.ENERGY_RAIN,
        observation,
        {"start": Element("start", Bounds(1, 1, 10, 10), observation.id)},
    )
    result = DetectedScreen(Page.ENERGY_RAIN_RESULT, observation)

    class RainSession:
        def __init__(self):
            self.config = SimpleNamespace(
                realtime=SimpleNamespace(minimum_hit_rate=0.80),
                runtime=SimpleNamespace(),
            )
            self.device = SimpleNamespace()
            self.run_directory = Path("unused")
            self.logger = SimpleNamespace(emit=lambda *_args, **_kwargs: None)
            self.taps = []
            self.waits = 0

        def tap(self, _screen, key, _name, expected=(), **_kwargs):
            self.taps.append(key)
            return rain if key == "energy_rain" else rain

        def wait_for(self, pages, _reason, **_kwargs):
            self.waits += 1
            return gift if self.waits == 1 else result

        def back(self, _screen, _name, _expected):
            return forest

        def add_step(self, *_args):
            pass

        def begin_step(self, *_args):
            pass

    workflow = object.__new__(ForestWorkflow)
    workflow.session = RainSession()
    workflow._locate_carousel = lambda current, _key: current
    workflow.rain = SimpleNamespace(
        play=lambda *_args: EnergyRainStats(10, 1, 1, 0, 0.10, 1.0, 16.0)
    )

    assert workflow._energy_rain(forest) is forest
