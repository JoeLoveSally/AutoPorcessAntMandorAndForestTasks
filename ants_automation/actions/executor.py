from __future__ import annotations

from ..device.adb import AndroidDevice
from ..domain.models import ActionResult, ActionStatus, DetectedPage, PageType, UIElement
from ..runtime.errors import SafetyStop


class ActionExecutor:
    def __init__(self, device: AndroidDevice, allowed_pages: set[PageType] | None = None):
        self.device = device
        self.allowed_pages = allowed_pages or {
            PageType.ALIPAY_HOME,
            PageType.MANOR_HOME,
            PageType.MANOR_FAMILY,
            PageType.MANOR_DONATION,
            PageType.FOREST_HOME,
        }
        self.results: list[ActionResult] = []

    def tap(self, page: DetectedPage, element_key: str, action_name: str | None = None) -> ActionResult:
        name = action_name or f"tap:{element_key}"
        try:
            self._validate(page, element_key)
            element = page.elements[element_key]
            self.device.tap(element.center)
            result = ActionResult(name=name, status=ActionStatus.EXECUTED, point=element.center)
        except SafetyStop as exc:
            result = ActionResult(name=name, status=ActionStatus.REJECTED, error=str(exc))
        except Exception as exc:
            result = ActionResult(name=name, status=ActionStatus.FAILED, error=str(exc))
        self.results.append(result)
        return result

    def back(self, page: DetectedPage) -> ActionResult:
        name = "back"
        try:
            self._validate_page(page)
            self.device.back()
            result = ActionResult(name=name, status=ActionStatus.EXECUTED)
        except SafetyStop as exc:
            result = ActionResult(name=name, status=ActionStatus.REJECTED, error=str(exc))
        except Exception as exc:
            result = ActionResult(name=name, status=ActionStatus.FAILED, error=str(exc))
        self.results.append(result)
        return result

    def _validate(self, page: DetectedPage, element_key: str) -> None:
        self._validate_page(page)
        element = page.elements.get(element_key)
        if element is None:
            raise SafetyStop(f"element not found: {element_key}")
        if element.observation_timestamp != page.observation.timestamp:
            raise SafetyStop("element belongs to an expired observation")
        if not element.enabled or not element.clickable or not element.bounds.valid:
            raise SafetyStop(f"element is not executable: {element_key}")
        width, height = self.device.screen_size()
        x, y = element.center
        if not (0 <= x < width and 0 <= y < height):
            raise SafetyStop(f"element point outside screen: {element.center}")

    def _validate_page(self, page: DetectedPage) -> None:
        if page.type not in self.allowed_pages:
            raise SafetyStop(f"page is not allowed: {page.type.value}")
        if page.type is PageType.UNKNOWN:
            raise SafetyStop("unknown page")
        if page.observation.package != "com.eg.android.AlipayGphone":
            raise SafetyStop("foreground package is not Alipay")
