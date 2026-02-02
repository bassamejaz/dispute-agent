"""Session context management for user identification."""

import contextvars
from typing import Optional

from src.config import settings

# Context variable for the current user ID
_current_user_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_user_id", default=None
)


def get_current_user_id() -> str:
    """Get the current user ID from session context.

    Returns the user ID from the context variable if set,
    otherwise falls back to the default user ID from settings.

    Returns:
        The current user's ID

    Raises:
        RuntimeError: If no user ID is available (context not set and no default)
    """
    user_id = _current_user_id.get()
    if user_id is not None:
        return user_id

    # Fall back to default user for demo/development
    if settings.default_user_id:
        return settings.default_user_id

    raise RuntimeError(
        "No user ID in session context. Ensure set_current_user_id() is called "
        "before accessing user-specific data."
    )


def set_current_user_id(user_id: str) -> contextvars.Token[Optional[str]]:
    """Set the current user ID in session context.

    Args:
        user_id: The user ID to set

    Returns:
        Token that can be used to reset the context
    """
    return _current_user_id.set(user_id)


def reset_current_user_id(token: contextvars.Token[Optional[str]]) -> None:
    """Reset the user ID context to its previous value.

    Args:
        token: Token returned from set_current_user_id()
    """
    _current_user_id.reset(token)
