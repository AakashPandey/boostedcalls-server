"""
Business-logic service for the CallScript model.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db.models import QuerySet

from calls.exceptions import ScriptNotFoundError
from calls.models import CallScript

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def create_script(
    *,
    user,
    name: str,
    description: str | None = None,
    custom_prompt: str | None = None,
    first_message: str | None = None,
    call_goals: list[dict[str, Any]] | None = None,
) -> CallScript:
    """Create a new call script."""
    return CallScript.objects.create(
        user=user,
        name=name,
        description=description,
        custom_prompt=custom_prompt,
        first_message=first_message,
        call_goals=call_goals,
    )


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def list_scripts(user) -> QuerySet[CallScript]:
    """Return all scripts for *user*."""
    return CallScript.objects.filter(user=user).order_by("-created_at")


def get_script(script_id: str, user) -> CallScript:
    """Fetch a single script owned by *user*."""
    try:
        return CallScript.objects.get(id=script_id, user=user)
    except CallScript.DoesNotExist:
        raise ScriptNotFoundError(f"Call script {script_id} not found.")


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

def update_script(
    script_id: str,
    user,
    **fields,
) -> CallScript:
    """
    Partial-update a call script.

    Only the keys present in *fields* are written.
    """
    script = get_script(script_id, user)

    for attr, value in fields.items():
        if hasattr(script, attr):
            setattr(script, attr, value)

    script.save()
    return script


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def delete_script(script_id: str, user) -> None:
    """Delete a script owned by *user*."""
    script = get_script(script_id, user)
    script.delete()
