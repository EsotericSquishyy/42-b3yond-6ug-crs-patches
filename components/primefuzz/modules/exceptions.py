
class WorkflowError(Exception):
    pass


class MessageAlreadyProcessedError(Exception):
    """Raised when a message has already been processed"""
    pass


class EarlyCancelledTaskError(Exception):
    """Raised when a task is cancelled before completion"""

    def __init__(self, message, errors=None):
        # Call the base class constructor with the parameters it needs
        super().__init__(message)

        # Now for your custom code...
        self.errors = errors or {}
