from __future__ import annotations

from domain_data import DetectedScreen, Page
from runtime.errors import AutomationError
from workflow.session import WorkflowSession
from workflow.shared.external import ExternalTaskRunner


class LotteryRunner:
    def __init__(self, session: WorkflowSession):
        self.session = session
        self.external = ExternalTaskRunner(session)

    def run(
        self,
        page: DetectedScreen,
        name: str,
        *,
        page_type: Page = Page.LOTTERY,
        store_repetitions: int = 3,
        exchange_feed: bool = True,
    ) -> DetectedScreen:
        current = page
        if current.page is not page_type:
            raise AutomationError(f"{name} started on {current.page.value}")
        current = self._locate(current, ("sign", "draw"), name, required=False)
        if current.element("sign"):
            current = self.session.tap(current, "sign", f"{name}-daily-sign")
            if current.page is not page_type:
                current = self.session.wait_for(page_type, f"{name}-after-sign")
        completed = 0
        while completed < store_repetitions:
            current = self._locate(current, ("store", "claim"), name, required=False)
            if current.element("claim") and not current.element("store"):
                current = self.session.tap(current, "claim", f"{name}-claim-{completed + 1}")
                completed += 1
                continue
            if not current.element("store"):
                break
            current = self.external.run(
                current,
                "store",
                f"{name}-store-{completed + 1}",
                page_type,
                swipe_to_progress=True,
                timeout_seconds=50,
            )
            current = self._locate(current, ("claim",), name)
            current = self.session.tap(current, "claim", f"{name}-claim-{completed + 1}")
            completed += 1
        if exchange_feed:
            current = self._locate(current, ("exchange", "draw"), name, required=False)
            if current.element("exchange"):
                current = self.session.tap(current, "exchange", f"{name}-exchange")
                if current.element("confirm_exchange") or current.element("confirm"):
                    key = "confirm_exchange" if current.element("confirm_exchange") else "confirm"
                    current = self.session.tap(current, key, f"{name}-confirm-exchange")
        current = self._locate(current, ("draw",), name)
        current = self.session.tap(current, "draw", f"{name}-draw")
        if current.element("close_reward"):
            current = self.session.tap(current, "close_reward", f"{name}-close-reward")
        elif current.page is not page_type:
            current = self.session.wait_for(page_type, f"{name}-after-reward")
        return current

    def _locate(
        self,
        current: DetectedScreen,
        keys: tuple[str, ...],
        name: str,
        required: bool = True,
    ) -> DetectedScreen:
        if any(current.element(key) for key in keys):
            return current
        size = self.session.device.size()
        directions = (
            ((size.width // 2, int(size.height * 0.75)), (size.width // 2, int(size.height * 0.35))),
            ((size.width // 2, int(size.height * 0.35)), (size.width // 2, int(size.height * 0.75))),
        )
        for start, end in directions:
            for scan in range(5):
                current = self.session.swipe(current, f"{name}-locate-{scan + 1}", start, end, 400)
                if current.page not in (Page.LOTTERY, Page.FOREST_LOTTERY):
                    raise AutomationError(f"Left lottery while locating {keys}: {current.page.value}")
                if any(current.element(key) for key in keys):
                    return current
        if required:
            raise AutomationError(f"Lottery elements not found: {keys}")
        return current
