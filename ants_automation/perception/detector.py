from __future__ import annotations

from ..domain.models import DetectedPage, Observation, PageType
from ..pages.alipay import detect_home
from ..pages.manor import detect_family, detect_manor_home


class PageDetector:
    def detect(self, observation: Observation) -> DetectedPage:
        for detector in (detect_home, detect_family, detect_manor_home):
            page = detector(observation)
            if page is not None:
                return page
        return DetectedPage(
            type=PageType.UNKNOWN,
            observation=observation,
            evidence=tuple(observation.errors) or ("no registered detector matched",),
            confidence=0.0,
        )
