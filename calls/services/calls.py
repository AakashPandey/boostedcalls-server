"""
Core business-logic service for the Call model.

All view-level code should delegate to these functions rather than
querying or mutating models directly.  This keeps views thin and
makes the logic easy to test in isolation.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.db import models
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from calls.constants import (
    ACTIVE_STATUSES,
    MAX_PENDING_CALLS,
    STALE_CALL_THRESHOLD_SECONDS,
    STALE_ELIGIBLE_STATUSES,
    STALE_QUEUED_SYNC_SECONDS,
    STATUS_ORDER,
    TERMINAL_STATUSES,
)
from calls.exceptions import (
    CallNotCancellableError,
    CallNotFoundError,
    ContactNotFoundError,
    MaxActiveCallsError,
    ScriptNotFoundError,
)
from calls.models import Call, CallScript, CallStatus, Contact
from calls.services import vapi as vapi_service

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def create_call(
    *,
    user,
    contact_id: str,
    assistant_id: str,
    phone_number_id: str,
    script_id: str | None = None,
    custom_prompt: str | None = None,
    first_message: str | None = None,
    call_goals: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Call:
    """
    Create a new outbound call.

    1. Validate rate limit (max active calls per user).
    2. Resolve contact & optional script.
    3. Insert a *pending* ``Call`` row.
    4. Fire the Vapi outbound call.
    5. Promote to *queued* on success or *failed* on error.
    """
    # --- Rate-limit check ---------------------------------------------------
    active_count = _get_active_call_count(user)
    if active_count >= MAX_PENDING_CALLS:
        raise MaxActiveCallsError(
            f"You can only have {MAX_PENDING_CALLS} active calls at a time. "
            "Please wait for existing calls to complete."
        )

    # --- Resolve contact ----------------------------------------------------
    try:
        contact = Contact.objects.get(id=contact_id, user=user)
    except Contact.DoesNotExist:
        raise ContactNotFoundError(f"Contact {contact_id} not found.")

    # --- Resolve script (optional) ------------------------------------------
    if script_id:
        try:
            script = CallScript.objects.get(id=script_id, user=user)
        except CallScript.DoesNotExist:
            raise ScriptNotFoundError(f"Script {script_id} not found.")
        # DTO values take precedence; fall back to script values.
        custom_prompt = custom_prompt or script.custom_prompt
        first_message = first_message or script.first_message
        call_goals = call_goals or script.call_goals

    # --- Persist pending call -----------------------------------------------
    call = Call.objects.create(
        user=user,
        contact=contact,
        script_id=script_id,
        assistant_id=assistant_id,
        phone_number_id=phone_number_id,
        status=CallStatus.PENDING,
        metadata=metadata,
    )

    # --- Trigger Vapi -------------------------------------------------------
    try:
        vapi_response = vapi_service.create_outbound_call(
            assistant_id=assistant_id,
            phone_number_id=phone_number_id,
            customer_number=contact.phone,
            customer_name=contact.name,
            custom_prompt=custom_prompt,
            first_message=first_message,
            call_goals=call_goals,
            metadata={
                **(metadata or {}),
                "internalCallId": str(call.id),
                "contactId": str(contact.id),
                "userId": str(user.id),
            },
        )
        call.vapi_call_id = vapi_response.get("id")
        call.status = CallStatus.QUEUED
        call.save(update_fields=["vapi_call_id", "status", "updated_at"])
    except Exception as exc:
        call.status = CallStatus.FAILED
        call.error_message = str(exc)
        call.save(update_fields=["status", "error_message", "updated_at"])
        raise

    return call


# ---------------------------------------------------------------------------
# Read (list / detail)
# ---------------------------------------------------------------------------

def list_calls(
    user,
    *,
    page: int = 1,
    limit: int = 20,
) -> dict[str, Any]:
    """Return a paginated list of calls for *user*."""
    limit = max(1, min(limit, 100))
    page = max(1, page)
    offset = (page - 1) * limit

    qs = (
        Call.objects
        .filter(user=user)
        .select_related("contact")
        .order_by("-created_at")
    )
    total = qs.count()
    calls = list(qs[offset : offset + limit])

    return {
        "data": calls,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": max(1, -(-total // limit)),  # ceil division
    }


def get_call(call_id: str, user) -> Call:
    """Fetch a single call owned by *user*, with related script eagerly loaded.
    
    If the call is in a queued/active state, sync with Vapi to refresh status.
    """
    try:
        call = (
            Call.objects
            .select_related("contact", "script")
            .get(id=call_id, user=user)
        )
    except Call.DoesNotExist:
        raise CallNotFoundError(f"Call {call_id} not found.")
    
    # Auto-sync if call is in a queued/pending state to keep frontend up-to-date
    if call.status in ACTIVE_STATUSES and call.vapi_call_id:
        try:
            vapi_data = vapi_service.get_call(call.vapi_call_id)
            update_fields = _reconcile_call_from_vapi(call, vapi_data)
            if update_fields:
                call.save(update_fields=update_fields)
                logger.info("Auto-synced call %s on fetch → %s", call.id, call.status)
        except Exception:
            logger.exception("Failed to auto-sync call %s on fetch", call.id)
            # Fall through – return the stale call rather than error
    
    return call


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------

def cancel_call(call_id: str, user) -> Call:
    """Cancel a call that is still active."""
    call = get_call(call_id, user)

    if call.status in TERMINAL_STATUSES:
        raise CallNotCancellableError(
            "Cannot cancel a call that is already completed, failed, or cancelled."
        )
    if not call.vapi_call_id:
        raise CallNotCancellableError("Call has no provider reference to cancel.")

    vapi_service.end_call(call.vapi_call_id)

    call.status = CallStatus.CANCELLED
    call.save(update_fields=["status", "updated_at"])
    return call


def find_by_vapi_call_id(vapi_call_id: str) -> Call | None:
    """Look up a call by its Vapi provider ID."""
    try:
        return Call.objects.get(vapi_call_id=vapi_call_id)
    except Call.DoesNotExist:
        return None


# ---------------------------------------------------------------------------
# Maintenance helpers
# ---------------------------------------------------------------------------

def mark_stale_calls() -> int:
    """
    Fail calls that have been stuck in pending/queued longer than the
    configured threshold.  Intended to be called from a periodic task.
    """
    cutoff = timezone.now() - timedelta(seconds=STALE_CALL_THRESHOLD_SECONDS)

    stale_qs = Call.objects.filter(
        status__in=STALE_ELIGIBLE_STATUSES,
        created_at__lt=cutoff,
    )
    count = stale_qs.count()
    if count == 0:
        return 0

    logger.warning("Marking %d stale call(s) as failed", count)
    stale_qs.update(
        status=CallStatus.FAILED,
        error_message="Call timed out – no response from provider",
    )
    return count


def sync_stale_queued_calls() -> int:
    """
    One-shot Vapi sync for calls stuck in ``queued`` for longer than
    ``STALE_QUEUED_SYNC_SECONDS``.

    For each matching call we poll Vapi, reconcile the local record,
    and move it to whatever status Vapi reports.  This is a safety net
    for when webhooks fail or arrive out-of-order.

    Intended to be called from a periodic task (management command,
    cron, Celery beat, etc.).
    """
    cutoff = timezone.now() - timedelta(seconds=STALE_QUEUED_SYNC_SECONDS)

    stale_calls = list(
        Call.objects.filter(
            status=CallStatus.QUEUED,
            created_at__lt=cutoff,
            vapi_call_id__isnull=False,
        ).exclude(vapi_call_id="")
    )

    if not stale_calls:
        return 0

    synced = 0
    for call in stale_calls:
        try:
            vapi_data = vapi_service.get_call(call.vapi_call_id)
        except Exception:
            logger.exception(
                "Failed to fetch Vapi data for stale-queued call %s", call.id,
            )
            continue

        update_fields = _reconcile_call_from_vapi(call, vapi_data)
        if not update_fields:
            continue

        call.save(update_fields=update_fields)
        synced += 1
        logger.info(
            "Auto-synced stale-queued call %s → %s (via Vapi poll)",
            call.id, call.status,
        )

    logger.info("sync_stale_queued_calls: %d/%d calls synced", synced, len(stale_calls))
    return synced


def get_active_call_count(user) -> int:
    """Return the number of active (non-terminal) calls for a user."""
    return _get_active_call_count(user)


def get_dashboard_stats(user) -> dict[str, Any]:
    calls_qs = Call.objects.filter(user=user)

    total_spent = 0.0
    for meta in calls_qs.values_list("metadata", flat=True):
        total_spent += _extract_cost(meta)

    total_calls = calls_qs.count()
    failed_calls = calls_qs.filter(status=CallStatus.FAILED).count()
    contacts = Contact.objects.filter(user=user).count()

    today = timezone.localdate()
    start = today - timedelta(days=13)

    completed_qs = calls_qs.filter(
        status=CallStatus.COMPLETED,
        created_at__date__gte=start,
        created_at__date__lte=today,
    )

    counts = {
        row["day"]: row["count"]
        for row in completed_qs.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(count=Count("id"))
    }

    points = []
    for i in range(14):
        day = start + timedelta(days=i)
        points.append(
            {
                "x": i,
                "y": counts.get(day, 0),
                "label": day.strftime("%a"),
            }
        )

    current_total = sum(p["y"] for p in points)
    prev_start = start - timedelta(days=14)
    prev_end = start - timedelta(days=1)
    prev_total = (
        calls_qs.filter(
            status=CallStatus.COMPLETED,
            created_at__date__gte=prev_start,
            created_at__date__lte=prev_end,
        ).count()
    )

    if prev_total > 0:
        change = round(((current_total - prev_total) / prev_total) * 100)
        subtitle = f"{change:+d}% vs previous 14 days"
    else:
        subtitle = "No prior data"

    return {
        "cards": [
            {
                "title": "Total Spent on Calls",
                "value": f"${total_spent:,.2f}",
            },
            {
                "title": "Calls made",
                "value": str(total_calls),
            },
            {
                "title": "Failed calls",
                "value": str(failed_calls),
            },
            {
                "title": "Contacts",
                "value": str(contacts),
            },
        ],
        "lineChart": {
            "title": "Successful calls",
            "subtitle": subtitle,
            "badge": "Last 14 days",
            "points": points,
        },
    }


# ---------------------------------------------------------------------------
# Sync with Vapi (recover from missed webhooks)
# ---------------------------------------------------------------------------

def sync_call_status(call_id: str, user) -> Call:
    """
    Poll Vapi for the latest call state and reconcile our local record.
    Useful when webhooks were missed or delayed.
    """
    call = get_call(call_id, user)

    if not call.vapi_call_id:
        raise CallNotCancellableError("Call has no provider reference to sync.")

    vapi_data = vapi_service.get_call(call.vapi_call_id)

    update_fields = _reconcile_call_from_vapi(call, vapi_data)
    if update_fields:
        call.save(update_fields=update_fields)
        logger.info("Synced call %s with Vapi → %s", call.id, call.status)

    return call


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _reconcile_call_from_vapi(call: Call, vapi_data: dict[str, Any]) -> list[str]:
    """
    Reconcile a local Call record with the raw Vapi GET /call response.

    Mutates ``call`` in place and returns the list of ``update_fields``
    to pass to ``.save()``.  Returns an empty list when nothing changed.

    Vapi GET /call response field locations (verified from real payload)::

        transcript        → top-level string
        summary           → top-level string (often empty)
        analysis          → top-level object  (may be empty {})
        artifact          → top-level object containing:
            .transcript               – same as top-level
            .structuredOutputs        – dict of {id: {name, result}}
            .recording                – recording URLs
        recordingUrl      → top-level
        stereoRecordingUrl→ top-level
        messages          → top-level array
        cost              → top-level number
        costBreakdown     → top-level object
        endedReason       → top-level string
        startedAt / endedAt → top-level ISO-8601
        metadata          → top-level (may be absent)
    """
    artifact = vapi_data.get("artifact") or {}
    analysis_obj = vapi_data.get("analysis") or {}

    # ── Status ─────────────────────────────────────────────────────────────
    vapi_status = vapi_data.get("status", "")

    if vapi_status == "ended":
        ended_reason = vapi_data.get("endedReason", "")
        new_status = _map_ended_reason(ended_reason, call.status)
    else:
        new_status = vapi_status or call.status

    if not _is_valid_status_transition(call.status, new_status):
        return []

    update_fields: list[str] = ["status", "updated_at"]
    call.status = new_status

    # ── Timestamps ─────────────────────────────────────────────────────────
    started = parse_datetime(vapi_data["startedAt"]) if vapi_data.get("startedAt") else None
    if started and not call.started_at:
        call.started_at = started
        update_fields.append("started_at")

    ended = parse_datetime(vapi_data["endedAt"]) if vapi_data.get("endedAt") else None
    if ended and not call.ended_at:
        call.ended_at = ended
        update_fields.append("ended_at")

    # ── Transcript (top-level, fallback to artifact) ───────────────────────
    transcript = vapi_data.get("transcript") or artifact.get("transcript")
    if transcript and not call.transcript:
        call.transcript = transcript
        update_fields.append("transcript")

    # ── Summary (top-level, fallback to structuredOutputs first result) ────
    summary = _extract_summary(vapi_data, artifact)
    if summary and not call.summary:
        call.summary = summary
        update_fields.append("summary")

    # ── Analysis (merge top-level analysis + structuredOutputs) ────────────
    structured_outputs = artifact.get("structuredOutputs") or {}
    merged_analysis: dict[str, Any] = {}
    if analysis_obj:
        merged_analysis.update(analysis_obj)
    if structured_outputs:
        merged_analysis["structuredOutputs"] = structured_outputs
    if merged_analysis and not call.analysis:
        call.analysis = merged_analysis
        update_fields.append("analysis")

    # ── Metadata (enrich with recording, messages, cost) ───────────────────
    enriched_meta: dict[str, Any] = {**(call.metadata or {})}
    if vapi_data.get("recordingUrl"):
        enriched_meta["recordingUrl"] = vapi_data["recordingUrl"]
    if vapi_data.get("stereoRecordingUrl"):
        enriched_meta["stereoRecordingUrl"] = vapi_data["stereoRecordingUrl"]
    if vapi_data.get("messages"):
        enriched_meta["messages"] = vapi_data["messages"]
    if vapi_data.get("cost") is not None:
        enriched_meta["cost"] = vapi_data["cost"]
    if vapi_data.get("costBreakdown"):
        enriched_meta["costBreakdown"] = vapi_data["costBreakdown"]
    if enriched_meta != (call.metadata or {}):
        call.metadata = enriched_meta
        update_fields.append("metadata")

    # ── Duration ───────────────────────────────────────────────────────────
    if call.started_at and call.ended_at and not call.duration_seconds:
        delta = call.ended_at - call.started_at
        call.duration_seconds = max(0, int(delta.total_seconds()))
        update_fields.append("duration_seconds")

    return update_fields


def _extract_summary(vapi_data: dict[str, Any], artifact: dict[str, Any]) -> str:
    """
    Pull the best available summary from a Vapi response.

    Priority:
    1. Top-level ``summary`` (if non-empty).
    2. ``analysis.summary`` (if non-empty).
    3. First ``artifact.structuredOutputs[*].result`` whose name
       contains "summary" (case-insensitive).
    4. First ``artifact.structuredOutputs[*].result`` regardless of name.
    """
    # 1. top-level
    s = (vapi_data.get("summary") or "").strip()
    if s:
        return s

    # 2. analysis.summary
    s = ((vapi_data.get("analysis") or {}).get("summary") or "").strip()
    if s:
        return s

    # 3 & 4. structuredOutputs
    outputs = artifact.get("structuredOutputs") or {}
    fallback = ""
    for entry in outputs.values():
        result = (entry.get("result") or "").strip()
        if not result:
            continue
        name = (entry.get("name") or "").lower()
        if "summary" in name:
            return result  # exact match on name
        if not fallback:
            fallback = result
    return fallback


def _get_active_call_count(user) -> int:
    return Call.objects.filter(user=user, status__in=ACTIVE_STATUSES).count()


def _is_valid_status_transition(current: str, new: str) -> bool:
    """
    Prevent backward status transitions.  Terminal states (order ≥ 10)
    can always be reached.
    """
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


def _extract_cost(metadata: dict[str, Any] | None) -> float:
    if not isinstance(metadata, dict):
        return 0.0

    cost = metadata.get("cost")
    if isinstance(cost, (int, float)):
        return float(cost)

    if isinstance(cost, dict):
        for key in ("total", "amount", "value", "cost"):
            value = cost.get(key)
            if isinstance(value, (int, float)):
                return float(value)

    return 0.0
