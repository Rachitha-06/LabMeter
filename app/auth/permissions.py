"""Role-to-permission table. This is the single source of truth; the frontend reads it from /api/auth/me.

Roles:
- admin: everything, including user management
- lab_manager: manages laboratories, schedules, readings, corrections, and imports
- staff: enters readings and imports files, but cannot change laboratories or correct existing readings
- evaluator: read-only access for reviewing results
"""
from __future__ import annotations

ROLES = ("admin", "lab_manager", "staff", "evaluator")

_ALL = set(ROLES)

PERMISSIONS: dict[str, set[str]] = {
    "labs:read": _ALL,
    "labs:write": {"admin", "lab_manager"},
    "readings:read": _ALL,
    "readings:write": {"admin", "lab_manager", "staff"},
    "readings:correct": {"admin", "lab_manager"},
    "imports:read": _ALL,
    "imports:write": {"admin", "lab_manager", "staff"},
    "analytics:read": _ALL,
    "forecasts:read": _ALL,
    "forecasts:create": {"admin", "lab_manager", "staff"},
    "models:read": _ALL,
    "alerts:read": _ALL,
    "energy:read": _ALL,
    "reports:read": _ALL,
    "energy:write": {"admin", "lab_manager"},
    "calendar:write": {"admin", "lab_manager"},
    "alerts:detect": {"admin", "lab_manager"},
    "alerts:review": {"admin", "lab_manager", "staff"},
    "users:manage": {"admin"},
}


def has_permission(role: str, permission: str) -> bool:
    return role in PERMISSIONS.get(permission, set())


def permissions_for(role: str) -> list[str]:
    return sorted(p for p, roles in PERMISSIONS.items() if role in roles)
