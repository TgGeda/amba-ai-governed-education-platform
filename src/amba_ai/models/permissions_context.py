from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


# ---------------------------------------------------------------------
# Permission Model
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class Permission:
    """
    Fine-grained permission flags for library and study operations.

    These flags are enforced by UI logic and service‑layer guards.
    """

    can_view: bool
    can_open: bool
    can_delete: bool
    can_purge: bool
    can_export: bool
    can_tag: bool
    can_sync: bool


# ---------------------------------------------------------------------
# User Context
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class UserContext:
    """
    Immutable user context bound to the current session.

    This object is safe to pass across threads and UI layers.
    """

    user_id: str
    role: str
    permissions: Permission


# ---------------------------------------------------------------------
# Role Definitions (Single Source of Truth)
# ---------------------------------------------------------------------

DEFAULT_ROLES: Dict[str, Permission] = {
    "student": Permission(
        can_view=True,
        can_open=True,
        can_delete=False,
        can_purge=False,
        can_export=True,
        can_tag=False,
        can_sync=False,
    ),
    "teacher": Permission(
        can_view=True,
        can_open=True,
        can_delete=True,
        can_purge=False,
        can_export=True,
        can_tag=True,
        can_sync=True,
    ),
    "admin": Permission(
        can_view=True,
        can_open=True,
        can_delete=True,
        can_purge=True,
        can_export=True,
        can_tag=True,
        can_sync=True,
    ),
}


# ---------------------------------------------------------------------
# Factory Helpers
# ---------------------------------------------------------------------

def create_user_context(
    *,
    user_id: str,
    role: str,
) -> UserContext:
    """
    Create a validated UserContext from a role.

    Raises:
        ValueError: if role is unknown or user_id is invalid.
    """
    if not user_id or not isinstance(user_id, str):
        raise ValueError("user_id must be a non‑empty string")

    normalized_role = role.lower().strip()
    permissions = DEFAULT_ROLES.get(normalized_role)

    if permissions is None:
        raise ValueError(f"Unknown role: {role!r}")

    return UserContext(
        user_id=user_id,
        role=normalized_role,
        permissions=permissions,
    )


def has_permission(context: UserContext, permission_name: str) -> bool:
    """
    Generic permission checker.

    Example:
        has_permission(ctx, "can_delete")
    """
    if not hasattr(context.permissions, permission_name):
        raise ValueError(f"Invalid permission: {permission_name}")

    return bool(getattr(context.permissions, permission_name))