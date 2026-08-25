class AutomationError(RuntimeError):
    """Base class for expected automation failures."""


class DeviceError(AutomationError):
    pass


class PerceptionError(AutomationError):
    pass


class SafetyStop(AutomationError):
    pass


class StepTimeout(AutomationError):
    pass
