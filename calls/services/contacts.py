"""
Business-logic service for the Contact model.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db.models import QuerySet

from calls.exceptions import ContactNotFoundError
from calls.models import Contact
from calls.utils import normalize_phone_number

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def create_contact(
    *,
    user,
    name: str,
    phone: str,
    email: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Contact:
    """Create a new contact, normalising the phone number on the way in."""
    return Contact.objects.create(
        user=user,
        name=name,
        phone=normalize_phone_number(phone),
        email=email,
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def list_contacts(user) -> QuerySet[Contact]:
    """Return all contacts for *user*, ordered by creation date."""
    return Contact.objects.filter(user=user).order_by("created_at")


def get_contact(contact_id: str, user) -> Contact:
    """Fetch a single contact owned by *user*."""
    try:
        return Contact.objects.get(id=contact_id, user=user)
    except Contact.DoesNotExist:
        raise ContactNotFoundError(f"Contact {contact_id} not found.")


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

def update_contact(
    contact_id: str,
    user,
    **fields,
) -> Contact:
    """
    Partial-update a contact.

    Only the keys present in *fields* are written.  ``phone`` is
    normalised automatically if provided.
    """
    contact = get_contact(contact_id, user)

    if "phone" in fields and fields["phone"] is not None:
        fields["phone"] = normalize_phone_number(fields["phone"])

    for attr, value in fields.items():
        if hasattr(contact, attr):
            setattr(contact, attr, value)

    contact.save()
    return contact


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def delete_contact(contact_id: str, user) -> None:
    """Delete a contact owned by *user*."""
    contact = get_contact(contact_id, user)
    contact.delete()
