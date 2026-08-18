from __future__ import annotations

from ..domain.models import DetectedPage, Observation, PageType
from ..pages.alipay import detect_home
from ..pages.manor import (
    detect_donation,
    detect_donation_confirm,
    detect_donation_project,
    detect_donation_reward,
    detect_family,
    detect_family_walk,
    detect_feed_tasks,
    detect_feed_full,
    detect_feed_video_complete,
    detect_manor_home,
    detect_quiz,
    detect_quiz_result,
    detect_walk_donation,
)
from ..pages.forest import (
    detect_co_plant,
    detect_forest_friend_picker,
    detect_forest_home,
    detect_forest_rain,
    detect_forest_rain_result,
)
from ..pages.lottery import detect_external_browse, detect_lottery, detect_lottery_reward


class PageDetector:
    def detect(self, observation: Observation) -> DetectedPage:
        for detector in (
            detect_home,
            detect_external_browse,
            detect_lottery_reward,
            detect_feed_video_complete,
            detect_feed_full,
            detect_quiz_result,
            detect_quiz,
            detect_feed_tasks,
            detect_donation_reward,
            detect_donation_confirm,
            detect_donation_project,
            detect_donation,
            detect_walk_donation,
            detect_family_walk,
            detect_family,
            detect_manor_home,
            detect_forest_rain_result,
            detect_forest_friend_picker,
            detect_forest_rain,
            detect_co_plant,
            detect_lottery,
            detect_forest_home,
        ):
            page = detector(observation)
            if page is not None:
                return page
        return DetectedPage(
            type=PageType.UNKNOWN,
            observation=observation,
            evidence=tuple(observation.errors) or ("no registered detector matched",),
            confidence=0.0,
        )
