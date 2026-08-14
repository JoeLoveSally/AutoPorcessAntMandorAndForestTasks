class AutomationError(RuntimeError):
    """Base error for a safe, user-facing failure."""


class DeviceError(AutomationError):
    pass


class LaunchError(AutomationError):
    pass


class RecognitionError(AutomationError):
    pass


class ActionError(AutomationError):
    pass


class TransitionError(AutomationError):
    pass


class TimeoutError(AutomationError):
    pass


class SafetyStop(AutomationError):
    pass
