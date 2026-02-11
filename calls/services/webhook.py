"""
Vapi webhook event dispatcher and handlers.

Vapi sends all webhook events as POST requests with this shape::

    {
        "message": {
            "type": "<event-type>",
            "call": { ... },
            ...
        }
    }

We care about two event types for call lifecycle tracking:

* ``status-update``       – fired on every status transition
* ``end-of-call-report``  – fired once after the call ends, carrying
                            transcript, recording, summary, analysis, etc.

All other event types are logged and acknowledged with 200 OK.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from django.utils.dateparse import parse_datetime

from calls.constants import STATUS_ORDER, TERMINAL_STATUSES
from calls.models import Call, CallStatus
from calls.services.calls import find_by_vapi_call_id

logger = logging.getLogger(__name__)

# Vapi status → our internal CallStatus mapping.
# Vapi uses "ended" while we track terminal states more granularly.
VAPI_STATUS_MAP: dict[str, str] = {
    "queued": CallStatus.QUEUED,
    "ringing": CallStatus.RINGING,
    "in-progress": CallStatus.IN_PROGRESS,
    "forwarding": CallStatus.IN_PROGRESS,  # treat as still active
    "ended": CallStatus.COMPLETED,
}


# ---------------------------------------------------------------------------
# Public dispatcher
# ---------------------------------------------------------------------------

def handle_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Route an incoming Vapi webhook to the appropriate handler.

    Returns a JSON-serialisable response dict.  Most events only need
    ``{"ok": True}``; tool-calls / assistant-request would need richer
    responses if we ever handle them.
    """
    message: dict[str, Any] = payload.get("message") or {}
    event_type: str = message.get("type", "")

    call_obj: dict[str, Any] = message.get("call") or {}
    vapi_call_id: str = call_obj.get("id", "")

    handler = _HANDLERS.get(event_type, _handle_ignored)
    return handler(event_type=event_type, vapi_call_id=vapi_call_id, message=message)


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------

def _handle_status_update(
    *,
    event_type: str,
    vapi_call_id: str,
    message: dict[str, Any],
) -> dict[str, Any]:
    """
    ``status-update`` – map Vapi status to our model and persist.

    Vapi statuses: scheduled, queued, ringing, in-progress, forwarding, ended.
    """
    vapi_status: str = message.get("status", "")
    new_status = VAPI_STATUS_MAP.get(vapi_status)

    if not new_status:
        logger.debug("Unmapped Vapi status '%s' – skipping.", vapi_status)
        return {"ok": True}

    if not vapi_call_id:
        logger.warning("status-update without call.id – skipping.")
        return {"ok": True}

    call = find_by_vapi_call_id(vapi_call_id)
    if call is None:
        logger.warning("status-update for unknown vapi_call_id: %s", vapi_call_id)
        return {"ok": True}

    if not _is_valid_transition(call.status, new_status):
        logger.debug(
            "Ignoring transition %s → %s for call %s",
            call.status, new_status, call.id,
        )
        return {"ok": True}

    update_fields = ["status", "updated_at"]
    call.status = new_status

    # Capture started_at when moving to in-progress.
    if new_status == CallStatus.IN_PROGRESS and not call.started_at:
        call.started_at = _parse_ts(message.get("timestamp"))
        update_fields.append("started_at")

    call.save(update_fields=update_fields)
    logger.info("Call %s status → %s (via status-update)", call.id, new_status)
    return {"ok": True}


def _handle_end_of_call_report(
    *,
    event_type: str,
    vapi_call_id: str,
    message: dict[str, Any],
) -> dict[str, Any]:
    """
    ``end-of-call-report`` – final report after a call ends.

    Carries transcript, summary, analysis, recording URLs, cost, etc.

    The ``message`` dict has this shape (relevant fields)::

        message.call            – the call object (has startedAt, endedAt, cost …)
        message.artifact        – transcript, messages, structuredOutputs …
        message.endedReason     – why the call ended
        message.transcript      – shortcut to transcript string
        message.summary         – may be empty
        message.recordingUrl    – mono recording
        message.stereoRecordingUrl
        message.messages        – conversation messages array
        message.analysis        – analysis object
    """
    if not vapi_call_id:
        logger.warning("end-of-call-report without call.id – skipping.")
        return {"ok": True}

    call = find_by_vapi_call_id(vapi_call_id)
    if call is None:
        logger.warning("end-of-call-report for unknown vapi_call_id: %s", vapi_call_id)
        return {"ok": True}

    artifact: dict[str, Any] = message.get("artifact") or {}
    call_data: dict[str, Any] = message.get("call") or {}

    update_fields = ["updated_at"]

    # Terminal status -----------------------------------------------------------
    ended_reason = message.get("endedReason", "")
    new_status = _map_ended_reason(ended_reason, call.status)
    if new_status != call.status:
        call.status = new_status
        update_fields.append("status")

    # Transcript ----------------------------------------------------------------
    transcript = (
        message.get("transcript")
        or artifact.get("transcript")
    )
    if transcript and not call.transcript:
        call.transcript = transcript
        update_fields.append("transcript")

    # Summary -------------------------------------------------------------------
    summary = _extract_summary_from_webhook(message, artifact)
    if summary and not call.summary:
        call.summary = summary
        update_fields.append("summary")

    # Analysis (merge top-level + structuredOutputs) ----------------------------
    analysis_obj = message.get("analysis") or call_data.get("analysis") or {}
    structured_outputs = artifact.get("structuredOutputs") or {}
    merged_analysis: dict[str, Any] = {}
    if analysis_obj:
        merged_analysis.update(analysis_obj)
    if structured_outputs:
        merged_analysis["structuredOutputs"] = structured_outputs
    if merged_analysis and not call.analysis:
        call.analysis = merged_analysis
        update_fields.append("analysis")

    # Metadata (enrich with recording, messages, cost) -------------------------
    enriched_meta: dict[str, Any] = {**(call.metadata or {})}
    recording_url = message.get("recordingUrl") or call_data.get("recordingUrl")
    if recording_url:
        enriched_meta["recordingUrl"] = recording_url
    stereo_url = message.get("stereoRecordingUrl") or call_data.get("stereoRecordingUrl")
    if stereo_url:
        enriched_meta["stereoRecordingUrl"] = stereo_url
    msgs = message.get("messages") or call_data.get("messages")
    if msgs:
        enriched_meta["messages"] = msgs
    cost = call_data.get("cost") if call_data.get("cost") is not None else message.get("cost")
    if cost is not None:
        enriched_meta["cost"] = cost
    cost_breakdown = call_data.get("costBreakdown") or message.get("costBreakdown")
    if cost_breakdown:
        enriched_meta["costBreakdown"] = cost_breakdown
    if enriched_meta != (call.metadata or {}):
        call.metadata = enriched_meta
        update_fields.append("metadata")

    # Timestamps ----------------------------------------------------------------
    started_at = _parse_ts(call_data.get("startedAt"))
    if started_at and not call.started_at:
        call.started_at = started_at
        update_fields.append("started_at")

    ended_at = _parse_ts(call_data.get("endedAt"))
    if ended_at and not call.ended_at:
        call.ended_at = ended_at
        update_fields.append("ended_at")

    # Duration ------------------------------------------------------------------
    if call.started_at and call.ended_at and not call.duration_seconds:
        delta = call.ended_at - call.started_at
        call.duration_seconds = max(0, int(delta.total_seconds()))
        update_fields.append("duration_seconds")

    call.save(update_fields=update_fields)
    logger.info(
        "Call %s end-of-call-report processed (status=%s, reason=%s)",
        call.id, call.status, ended_reason,
    )
    return {"ok": True}


def _extract_summary_from_webhook(
    message: dict[str, Any],
    artifact: dict[str, Any],
) -> str:
    """
    Best-effort summary extraction from a webhook end-of-call-report.

    Priority:
    1. ``message.summary`` (if non-empty).
    2. ``message.analysis.summary``.
    3. First ``artifact.structuredOutputs[*].result`` whose name
       contains "summary" (case-insensitive).
    4. First ``artifact.structuredOutputs[*].result``.
    """
    s = (message.get("summary") or "").strip()
    if s:
        return s

    s = ((message.get("analysis") or {}).get("summary") or "").strip()
    if s:
        return s

    outputs = artifact.get("structuredOutputs") or {}
    fallback = ""
    for entry in outputs.values():
        result = (entry.get("result") or "").strip()
        if not result:
            continue
        name = (entry.get("name") or "").lower()
        if "summary" in name:
            return result
        if not fallback:
            fallback = result
    return fallback


def _handle_ignored(
    *,
    event_type: str,
    vapi_call_id: str,
    message: dict[str, Any],
) -> dict[str, Any]:
    """Acknowledge event types we don't act on."""
    logger.debug("Ignoring Vapi event '%s' (call %s)", event_type, vapi_call_id or "n/a")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------

_HANDLERS: dict[str, Any] = {
    "status-update": _handle_status_update,
    "end-of-call-report": _handle_end_of_call_report,
    # Extend here as needed:
    # "transcript": _handle_transcript,
    # "tool-calls": _handle_tool_calls,
}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _is_valid_transition(current: str, new: str) -> bool:
    current_order = STATUS_ORDER.get(current, 0)
    new_order = STATUS_ORDER.get(new, 0)
    if new_order >= 10:
        return True
    return new_order >= current_order


def _map_ended_reason(reason: str, current_status: str) -> str:
    """
    Map Vapi's ``endedReason`` to the best-fitting terminal status.

    Common reasons:
    hangup, assistant-error, phone-call-provider-closed-websocket,
    silence-timed-out, customer-busy, customer-did-not-answer,
    voicemail, customer-ended-call, assistant-ended-call, etc.
    """
    reason_lower = reason.lower().replace("-", "_") if reason else ""

    if "busy" in reason_lower:
        return CallStatus.BUSY
    if "no_answer" in reason_lower or "did_not_answer" in reason_lower:
        return CallStatus.NO_ANSWER
    if "voicemail" in reason_lower:
        return CallStatus.VOICEMAIL
    if "error" in reason_lower:
        return CallStatus.FAILED
    if "silence" in reason_lower:
        return CallStatus.COMPLETED

    # hangup, customer-ended-call, assistant-ended-call → completed
    if current_status in TERMINAL_STATUSES:
        return current_status  # already terminal, don't change
    return CallStatus.COMPLETED


def _parse_ts(value: Any) -> datetime | None:
    """Best-effort parse of an ISO-8601 timestamp string."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return parse_datetime(str(value))
    except (ValueError, TypeError):
        return None
