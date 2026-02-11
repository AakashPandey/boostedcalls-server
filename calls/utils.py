"""
Utility helpers for the calls app.
"""

import re


def normalize_phone_number(phone: str) -> str:
    """
    Normalise a phone string to E.164 format.

    Heuristics when no country-code prefix is present:

    * 10 digits starting with 6-9 → India (+91)
    * 10 digits otherwise          → US (+1)
    * 9 digits                     → UAE (+971)
    * 11 digits starting with 0   → UK national (strip trunk-0, +44)
    * 11-15 digits                → assume country code included, prefix ``+``
    * Fallback                    → prefix ``+91``
    """
    if not phone:
        return phone

    raw = phone.strip()

    # Already has an explicit '+'  →  just strip non-digit chars after it.
    if raw.startswith("+"):
        return "+" + re.sub(r"\D", "", raw[1:])

    digits = re.sub(r"\D", "", raw)

    # International 00-prefix  →  replace with '+'
    if digits.startswith("00"):
        return f"+{digits[2:]}"

    if len(digits) == 10:
        if digits[0] in "6789":
            return f"+91{digits}"  # India mobile
        return f"+1{digits}"  # US / Canada

    if len(digits) == 9:
        return f"+971{digits}"  # UAE

    if len(digits) == 11 and digits.startswith("0"):
        return f"+44{digits[1:]}"  # UK national → strip trunk-0

    if 11 <= len(digits) <= 15:
        return f"+{digits}"

    # Fallback
    return f"+91{digits}"
