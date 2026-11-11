class InputError(ValueError):
    """An expected rejection with a message safe to display in the UI."""


class UpdateCancelled(Exception):
    """Cooperative operator cancellation, not a failed verification."""
