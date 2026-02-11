"""
Vapi telephony API client.

Handles all outbound HTTP communication with the Vapi REST API,
keeping the rest of the Django app decoupled from the provider.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from django.conf import settings

from calls.exceptions import VapiAPIError
from calls.utils import normalize_phone_number

logger = logging.getLogger(__name__)

VAPI_BASE_URL = "https://api.vapi.ai"


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def create_outbound_call(
    *,
    assistant_id: str,
    phone_number_id: str,
    customer_number: str,
    customer_name: str | None = None,
    custom_prompt: str | None = None,
    first_message: str | None = None,
    call_goals: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create an outbound phone call via Vapi and return the raw response."""

    overrides = _build_assistant_overrides(
        custom_prompt=custom_prompt,
        first_message=first_message,
        call_goals=call_goals,
        metadata=metadata,
    )

    payload: dict[str, Any] = {
        "assistantId": assistant_id,
        "phoneNumberId": phone_number_id,
        "customer": {
            "number": normalize_phone_number(customer_number),
        },
    }
    if customer_name:
        payload["customer"]["name"] = customer_name

    if overrides:
        payload["assistantOverrides"] = overrides

    logger.info("Creating outbound call to %s", customer_number)
    logger.debug("Call payload: %s", payload)

    return _post("/call/phone", payload)


def get_call(vapi_call_id: str) -> dict[str, Any]:
    """Fetch call details from Vapi."""
    return _get(f"/call/{vapi_call_id}")


def end_call(vapi_call_id: str) -> dict[str, Any]:
    """Request Vapi to stop an in-progress call."""
    return _post(f"/call/{vapi_call_id}/stop")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _headers() -> dict[str, str]:
    api_key: str = getattr(settings, "VAPI_API_KEY", "") or ""
    if not api_key:
        raise VapiAPIError("VAPI_API_KEY is not configured.")
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _get(path: str) -> dict[str, Any]:
    url = f"{VAPI_BASE_URL}{path}"
    try:
        with httpx.Client(timeout=30) as client:
            response = client.get(url, headers=_headers())
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        body = exc.response.text
        logger.error("Vapi GET %s failed: %s – %s", path, exc.response.status_code, body)
        raise VapiAPIError(f"Vapi error {exc.response.status_code}: {body}") from exc
    except httpx.HTTPError as exc:
        logger.error("Vapi GET %s error: %s", path, exc)
        raise VapiAPIError(str(exc)) from exc


def _post(path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{VAPI_BASE_URL}{path}"
    try:
        with httpx.Client(timeout=30) as client:
            response = client.post(url, headers=_headers(), json=payload or {})
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        body = exc.response.text
        logger.error("Vapi POST %s failed: %s – %s", path, exc.response.status_code, body)
        raise VapiAPIError(f"Vapi error {exc.response.status_code}: {body}") from exc
    except httpx.HTTPError as exc:
        logger.error("Vapi POST %s error: %s", path, exc)
        raise VapiAPIError(str(exc)) from exc


def _build_assistant_overrides(
    *,
    custom_prompt: str | None = None,
    first_message: str | None = None,
    call_goals: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build the ``assistantOverrides`` payload for Vapi.

    Template variables (``customPrompt``, ``callGoals``) are injected via
    ``variableValues`` so the Vapi assistant's system prompt can reference
    them with ``{{customPrompt}}`` / ``{{callGoals}}``.
    """
    overrides: dict[str, Any] = {}

    webhook_url = getattr(settings, "VAPI_WEBHOOK_URL", None)
    if webhook_url:
        overrides["serverUrl"] = webhook_url

    if first_message:
        overrides["firstMessage"] = first_message

    variable_values: dict[str, str] = {}

    if custom_prompt:
        variable_values["customPrompt"] = custom_prompt

    if call_goals:
        lines: list[str] = []
        for idx, goal in enumerate(call_goals, start=1):
            line = f"{idx}. **{goal['name']}**: {goal['description']}"
            if goal.get("successCriteria"):
                line += f" (Success: {goal['successCriteria']})"
            lines.append(line)
        variable_values["callGoals"] = "\n".join(lines)

    if variable_values:
        overrides["variableValues"] = variable_values

    if metadata:
        overrides["metadata"] = metadata

    return overrides
